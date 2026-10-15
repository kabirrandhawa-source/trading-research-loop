"""Everything Claude sees before deciding: recent prices for the sleeve's universe (and SPY for
reference), recent headlines, and the sleeve's current book. Read-only.

    .venv/bin/python -m sleeve.context                 # prints JSON (sleeve v1)
    .venv/bin/python -m sleeve.context --sleeve v2     # same facts for another sleeve's book
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sleeve import book as sleeve_book  # noqa: E402


def bars(symbols, days=90):
    import broker
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = broker.data_client().get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day, adjustment="all",
        start=datetime.now(timezone.utc) - timedelta(days=days))).df.reset_index()
    out = {}
    for s, g in df.groupby("symbol"):
        c = g["close"].astype(float).reset_index(drop=True)
        ret = lambda n: round(float(c.iloc[-1] / c.iloc[-1 - n] - 1) * 100, 2) if len(c) > n else None
        out[s] = {"last_date": g["timestamp"].iloc[-1].tz_convert("America/New_York").strftime("%Y-%m-%d"),
                  "close": round(float(c.iloc[-1]), 2), "ret_1d_pct": ret(1), "ret_5d_pct": ret(5),
                  "ret_20d_pct": ret(20), "ret_60d_pct": ret(60),
                  "above_20d_avg": bool(c.iloc[-1] > c.tail(20).mean()), "above_50d_avg": bool(c.iloc[-1] > c.tail(50).mean()),
                  "vol_20d_ann_pct": round(float(c.pct_change().tail(20).std() * 252 ** .5 * 100), 1)}
    return out


def headlines(hours=24, limit=25):
    import broker
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    res = NewsClient(*broker._keys()).get_news(NewsRequest(start=datetime.now(timezone.utc) - timedelta(hours=hours), limit=50))
    items = res.data["news"] if hasattr(res, "data") else res.news
    keep = [n for n in items if "halt" not in n.headline.lower()]
    return [{"time": n.created_at.strftime("%Y-%m-%d %H:%M UTC"), "headline": n.headline, "symbols": list(n.symbols or [])[:5]}
            for n in keep[:limit]]


def build(sleeve=None):
    cfg = sleeve_book.config(sleeve=sleeve)
    book = sleeve_book.load(cfg=cfg, sleeve=sleeve)
    px = bars(cfg["universe"] + [cfg["benchmark"]])
    prices = {s: v["close"] for s, v in px.items()}
    held_value = sleeve_book.value(book, prices)
    weights = {s: round(q * prices[s] / held_value * 100, 1) for s, q in book["holdings"].items()} if held_value else {}
    out = {"rules": {k: cfg[k] for k in ("budget", "universe", "long_only", "max_positions", "max_position_pct_of_sleeve")},
           "sleeve": {"cash": round(book["cash"], 2), "holdings_shares": book["holdings"], "holdings_pct": weights,
                      "value": held_value, "orders_waiting_to_fill": book["pending"],
                      "recent_values": book["history"][-10:]},
           "prices": px}
    try:
        out["headlines"] = headlines()
    except Exception as e:
        out["headlines"] = {"error": f"{type(e).__name__}: {str(e)[:150]}"}
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--sleeve", default=sleeve_book.DEFAULT, choices=sorted(sleeve_book.SLEEVES))
    print(json.dumps(build(p.parse_args().sleeve), indent=1))
