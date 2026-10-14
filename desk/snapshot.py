"""Desk snapshot for the Friday dashboard: desk.status flattened into rows. No keys or credentials.

    .venv/bin/python -m desk.snapshot      # writes data/desk/snapshot.json and prints its path

Every row has the same columns: section, key (unique), label, status, value, detail.
Sections: kpi, health, meta, equity, position, trade, hypothesis, alert.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from desk import status as desk_status

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "desk" / "snapshot.json"


def row(section, key, label, status=None, value=None, detail=None):
    return {"section": section, "key": f"{section}-{key}", "label": label, "status": status,
            "value": value, "detail": detail}


def lessons():
    import ledger
    conn = ledger.connect()
    out = {}
    for hid, text in conn.execute("SELECT id, lessons FROM hypotheses"):
        last = (text or "").strip().splitlines()[-1:] or [""]
        out[hid] = last[0].split("] ", 1)[-1][:220]
    return out


START_EQUITY = 100_000.0


def account_rows():
    """Equity history, open positions and P&L figures from the Alpaca paper account."""
    import broker
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    c = broker.paper_client()
    rows = []
    h = c.get_portfolio_history(GetPortfolioHistoryRequest(period="3M", timeframe="1D"))
    for t, eq in zip(h.timestamp, h.equity):
        if eq and eq > 0:
            day = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
            rows.append(row("equity", day, day, None, round(float(eq), 2), None))
    a = c.get_account()
    eq, last = float(a.equity), float(a.last_equity)
    rows += [row("kpi", "pl_total", "P&L since start", "up" if eq >= START_EQUITY else "down",
                 round(eq - START_EQUITY, 2), f"{(eq / START_EQUITY - 1):+.2%} on ${START_EQUITY:,.0f}"),
             row("kpi", "pl_today", "P&L today", "up" if eq >= last else "down", round(eq - last, 2),
                 f"{(eq / last - 1) if last else 0:+.2%} since yesterday's close"),
             row("kpi", "cash", "Cash", None, round(float(a.cash), 2), "Uninvested paper cash")]
    pos = c.get_all_positions()
    rows.append(row("kpi", "positions", "Open positions", None, len(pos), ", ".join(p.symbol for p in pos) or "None"))
    for p in pos:
        pl, plpc = float(p.unrealized_pl), float(p.unrealized_plpc)
        rows.append(row("position", p.symbol, p.symbol, "up" if pl >= 0 else "down", round(pl, 2),
                        f"{float(p.qty):g} sh @ ${float(p.avg_entry_price):,.2f} · now ${float(p.market_value):,.2f} · {plpc:+.2%}"))
    return rows


def trade_rows(limit=40):
    """Every order the desk sent or the kill switch blocked, newest first, from journal/*.jsonl."""
    out = []
    for f in sorted((ROOT / "journal").glob("*.jsonl")):
        for line in f.read_text().splitlines():
            e = json.loads(line)
            if e.get("decision") in ("submitted", "blocked", "broker_error") and e.get("symbol"):
                out.append(e)
    rows = [row("kpi", "orders", "Orders sent", None, sum(e["decision"] == "submitted" for e in out), "All time, paper"),
            row("kpi", "blocked", "Blocked by kill switch", "attention" if any(e["decision"] == "blocked" for e in out) else "ok",
                sum(e["decision"] == "blocked" for e in out), "Orders the risk check stopped")]
    for i, e in enumerate(reversed(out[-limit:])):
        value = (e.get("order") or {}).get("value")
        rows.append(row("trade", i, f"{e['side'].upper()} {e['qty']:g} {e['symbol']}", e["decision"],
                        round(value, 2) if value else None,
                        f"{e['timestamp'][:16].replace('T', ' ')} UTC · {e.get('strategy')} · {e.get('risk_check') or e.get('error') or ''}"))
    return rows


def safe(fn):
    try:
        return fn()
    except Exception as e:
        return [row("health", f"error-{fn.__name__}", f"Snapshot part failed: {fn.__name__}", "bad", None,
                    f"{type(e).__name__}: {str(e)[:150]}")]


def build(s=None):
    s = s or desk_status.status()
    rows = []
    led = s.get("ledger", {})
    by = led.get("by_status", {}) if "error" not in led else {}
    tested = sum(v for k, v in by.items() if k != "untested")
    edges = by.get("passed_backtest", 0) + by.get("passed_paper", 0)
    waiting = led.get("waiting_for_your_sealed_test_decision", []) if "error" not in led else []
    pa = s.get("paper_account", {})
    rows += [
        row("kpi", "tested", "Ideas tested", value=tested, detail="Failed, dropped, or passed"),
        row("kpi", "edges", "Edges found", value=edges, detail="Passed a backtest or paper trading"),
        row("kpi", "waiting", "Decisions waiting", "attention" if waiting else "ok", len(waiting),
            ", ".join(f"#{i}" for i in waiting) or "None"),
        row("kpi", "equity", "Paper equity", value=pa.get("equity"),
            detail=f"{pa.get('day_change', 0):+,.2f} today, {len(pa.get('positions', []))} positions"
            if "error" not in pa else pa["error"]),
    ]

    jobs = s.get("jobs", {})
    if "error" not in jobs:
        down = [j for j in ("pm-stream", "pm-recorder") if not str(jobs.get(j, "")).startswith("running")]
        unloaded = [j for j, v in jobs.items() if v == "NOT LOADED"]
        rows.append(row("health", "jobs", "Background jobs", "bad" if down or unloaded else "ok",
                        detail="All running or scheduled" if not (down or unloaded)
                        else "Not running: " + ", ".join(down + unloaded)))
    rec = s.get("recorders", {})
    if "error" not in rec:
        hour = rec.get("stream_last_hour") or {}
        ago = rec.get("stream_last_write_s_ago")
        rows.append(row("health", "stream", "Kalshi stream", "ok" if ago is not None and ago < 120 else "bad",
                        hour.get("ws_tob"), f"price changes in the last hour; last write {ago}s ago, "
                        f"{rec.get('stream_reconnects_today', 0)} connects today"))
        rows.append(row("health", "data", "Recorded data", "ok", rec.get("data_pm_gb"),
                        f"GB on disk, {rec.get('archived_days', 0)} days compressed"))
    free = s.get("free_disk_gb")
    rows.append(row("health", "disk", "Free disk", "ok" if free and free > 25 else ("attention" if free and free > 15 else "bad"),
                    free, "GB free; recording pauses below 15"))
    g = s.get("git", {})
    if "error" not in g:
        synced = g.get("sync", "").endswith("origin/main") and "ahead" not in g.get("sync", "")
        rows.append(row("health", "git", "GitHub backup", "ok" if synced else "attention",
                        g.get("uncommitted_files"), f"uncommitted files; last commit {g.get('last_commit', '')[:60]}"))
    latest = s.get("latest", {})
    if "error" not in latest:
        rows.append(row("health", "summary", "Latest daily summary",
                        "ok" if latest.get("daily_summary") else "attention", None, latest.get("daily_summary") or "None yet"))

    rows.append(row("meta", "asof", "Snapshot taken", detail=s.get("as_of")))
    rows += safe(account_rows) + safe(trade_rows)

    les = lessons()
    for h in led.get("hypotheses", []) if "error" not in led else []:
        rows.append(row("hypothesis", h["id"], h["idea"], h["status"], h.get("variations"),
                        f"{h['market']}: {les.get(h['id'], '')}"))

    for i, a in enumerate(reversed(s.get("alerts_last_24h") or [])):
        time_, rest = a.split(" UTC ", 1) if " UTC " in a else ("", a)
        prio = rest[1:rest.index("]")] if rest.startswith("[") else None
        rows.append(row("alert", i, rest.split("] ", 1)[-1], prio, None, f"{time_} UTC"))
    return rows


def main():
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, default=str))
    print(OUT)
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
