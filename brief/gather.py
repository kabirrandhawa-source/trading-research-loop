"""Collect the facts for the morning market brief. Read-only: no orders, nothing written to Alpaca.

    .venv/bin/python -m brief.gather          # writes data/brief/YYYY-MM-DD.json and prints it

Sections: ETF universe moves, top US stock movers (over $5), most active, recent headlines,
crypto 24h moves, the paper account, and the state of the research loop. Each section fails
independently: an error in one is recorded in that section, the rest still run.
"""
import json
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "brief"
MIN_PRICE = 5.0
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]


def section(fn):
    try:
        return fn()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


def etf_moves():
    syms = [s.strip() for s in (ROOT / "universe.txt").read_text().split() if s.strip()]
    rows = []
    for s in syms:
        df = pd.read_csv(ROOT / "data" / f"{s}.csv", parse_dates=["timestamp"])
        c = df["close"]
        rows.append({"symbol": s, "date": str(df["timestamp"].iloc[-1].date()), "close": round(float(c.iloc[-1]), 2),
                     "day_pct": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                     "week_pct": round(float(c.iloc[-1] / c.iloc[-6] - 1) * 100, 2)})
    return sorted(rows, key=lambda r: r["day_pct"], reverse=True)


def _alpaca_keys():
    import broker
    return broker._keys()


def movers():
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.requests import MarketMoversRequest, MostActivesRequest
    sc = ScreenerClient(*_alpaca_keys())
    mv = sc.get_market_movers(MarketMoversRequest(top=50))
    pick = lambda xs: [{"symbol": x.symbol, "pct": round(x.percent_change, 1), "price": round(x.price, 2)}
                       for x in xs if x.price and x.price >= MIN_PRICE][:6]
    actives = sc.get_most_actives(MostActivesRequest(top=10)).most_actives
    return {"gainers": pick(mv.gainers), "losers": pick(mv.losers),
            "most_active": [{"symbol": x.symbol, "volume": int(x.volume)} for x in actives][:6]}


def news(hours=18):
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    res = NewsClient(*_alpaca_keys()).get_news(NewsRequest(
        start=datetime.now(timezone.utc) - timedelta(hours=hours), limit=50))
    items = res.data["news"] if hasattr(res, "data") else res.news
    keep = [n for n in items if "trading halt" not in n.headline.lower() and "halted at" not in n.headline.lower()]
    return [{"time": n.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "headline": n.headline,
             "symbols": list(n.symbols or [])[:6], "source": n.source} for n in keep[:20]]


def crypto():
    out = []
    for p in CRYPTO:
        d = requests.get(f"https://api.exchange.coinbase.com/products/{p}/stats", timeout=10).json()
        o, last = float(d["open"]), float(d["last"])
        out.append({"asset": p.split("-")[0], "price": last, "change_24h_pct": round((last / o - 1) * 100, 2)})
    return out


def paper_account():
    import broker
    c = broker.paper_client()
    a = c.get_account()
    pos = [{"symbol": p.symbol, "qty": float(p.qty), "unrealized_pl": round(float(p.unrealized_pl), 2)}
           for p in c.get_all_positions()]
    return {"equity": round(float(a.equity), 2), "day_change": round(float(a.equity) - float(a.last_equity), 2),
            "positions": pos}


def loop_status():
    import ledger
    conn = ledger.connect()
    counts = dict(conn.execute("SELECT status, COUNT(*) FROM hypotheses GROUP BY status").fetchall())
    waiting = [dict(id=r[0], idea=r[1][:120]) for r in conn.execute(
        "SELECT id, idea FROM hypotheses WHERE status = 'passed_backtest' AND sealed_used_at IS NULL")]
    summaries = sorted((ROOT / "journal").glob("summary-*.md"))
    jobs = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    running = {lbl: any(lbl in l and not l.startswith("-") for l in jobs.splitlines())
               for lbl in ("pm-stream", "pm-recorder")}
    stream_rows = None
    files = sorted((ROOT / "data" / "pm").glob("stream-????-??-??.db"))
    if files:
        s = sqlite3.connect(files[-1])
        stream_rows = s.execute("SELECT COUNT(*) FROM ws_tob WHERE ts > ?", (time.time() - 3600,)).fetchone()[0]
    return {"hypotheses_by_status": counts, "waiting_for_sealed_test_decision": waiting,
            "latest_daily_summary": summaries[-1].name if summaries else None,
            "background_jobs_running": running, "stream_price_changes_last_hour": stream_rows,
            "free_disk_gb": round(shutil.disk_usage(ROOT).free / 1e9, 1)}


def gather():
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "etfs": section(etf_moves), "movers": section(movers), "news": section(news),
            "crypto": section(crypto), "paper_account": section(paper_account), "loop": section(loop_status)}


def main():
    data = gather()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{datetime.now().date().isoformat()}.json"
    out.write_text(json.dumps(data, indent=2, default=str))
    print(json.dumps(data, indent=2, default=str))
    print(out)


if __name__ == "__main__":
    main()
