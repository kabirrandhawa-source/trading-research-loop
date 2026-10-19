"""Forward recorder for crypto funding carry (hypothesis 14): hourly snapshots of perpetual-futures funding,
perp mark/index prices and Coinbase spot, so the carry and its basis risk can be tested on data recorded
from 2026-10-19 on (the history we have is mostly sealed and has no basis). Read-only public APIs, no account.

Sources:
- Kraken Futures tickers (live): mark, index, bid/ask, funding rate. Kraken's `fundingRate` is in USD per
  contract per hour (1 contract = 1 coin), so the relative hourly rate is fundingRate / markPrice.
- Coinbase International quote: recorded as a cross-check, but its feed stopped updating on 2026-10-01;
  `source_ts` shows how stale each row is.
- Coinbase spot ticker (the leg we would actually hold).

    .venv/bin/python -m crypto.forward record     # one snapshot (launchd runs this hourly)
    .venv/bin/python -m crypto.forward status     # rows recorded and the latest snapshot
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crypto.data import COINS, KRAKEN, get  # noqa: E402

DB = ROOT / "data" / "crypto" / "forward.db"
INTL_COINS = ["BTC", "ETH"]


def connect(db=None):
    db = Path(db or DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            ts TEXT, source TEXT, coin TEXT,
            mark REAL, idx REAL, perp_bid REAL, perp_ask REAL,
            funding_raw REAL, funding_rel_hourly REAL, funding_pred_raw REAL,
            spot REAL, spot_bid REAL, spot_ask REAL,
            source_ts TEXT, raw TEXT,
            PRIMARY KEY (ts, source, coin));
        CREATE TABLE IF NOT EXISTS errors (ts TEXT, source TEXT, error TEXT);
    """)
    return c


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kraken_rows(ts, spots, fetch=get):
    by_symbol = {t.get("symbol"): t for t in fetch("https://futures.kraken.com/derivatives/api/v3/tickers")["tickers"]}
    rows = []
    for coin in COINS:
        t = by_symbol.get(KRAKEN[coin])
        if not t:
            continue
        mark, fr = _f(t.get("markPrice")), _f(t.get("fundingRate"))
        rel = fr / mark if fr is not None and mark else None
        s = spots.get(coin, {})
        rows.append((ts, "kraken", coin, mark, _f(t.get("indexPrice")), _f(t.get("bid")), _f(t.get("ask")),
                     fr, rel, _f(t.get("fundingRatePrediction")), s.get("price"), s.get("bid"), s.get("ask"),
                     t.get("lastTime"), json.dumps(t)))
    return rows


def intl_rows(ts, spots, fetch=get):
    rows = []
    for coin in INTL_COINS:
        q = fetch(f"https://api.international.coinbase.com/api/v1/instruments/{coin}-PERP/quote")
        s = spots.get(coin, {})
        pred = _f(q.get("predicted_funding"))              # already a relative rate per funding interval
        rows.append((ts, "coinbase_intl", coin, _f(q.get("mark_price")), _f(q.get("index_price")),
                     _f(q.get("best_bid_price")), _f(q.get("best_ask_price")), pred, pred, pred,
                     s.get("price"), s.get("bid"), s.get("ask"), q.get("timestamp"), json.dumps(q)))
    return rows


def spot_quotes(fetch=get):
    out = {}
    for coin in COINS:
        t = fetch(f"https://api.exchange.coinbase.com/products/{coin}-USD/ticker")
        out[coin] = {"price": _f(t.get("price")), "bid": _f(t.get("bid")), "ask": _f(t.get("ask"))}
    return out


def record(db=None, fetch=get, now=None):
    """Take one snapshot. Each source fails on its own; errors are stored, never raised."""
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    c = connect(db)
    try:
        spots = spot_quotes(fetch)
    except Exception as e:
        spots = {}
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (ts, "coinbase_spot", f"{type(e).__name__}: {e}"[:300]))
    n = 0
    for name, fn in (("kraken", kraken_rows), ("coinbase_intl", intl_rows)):
        try:
            rows = fn(ts, spots, fetch)
            c.executemany("INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            n += len(rows)
        except Exception as e:
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (ts, name, f"{type(e).__name__}: {e}"[:300]))
    c.commit()
    c.close()
    return n


def status(db=None):
    c = connect(db)
    total, first, last = c.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM snapshots").fetchone()
    errs = c.execute("SELECT COUNT(*) FROM errors").fetchone()[0]
    latest = c.execute("SELECT source, coin, mark, spot, funding_rel_hourly, source_ts FROM snapshots "
                       "WHERE ts = ? ORDER BY source, coin", (last,)).fetchall()
    c.close()
    return {"rows": total, "first": first, "last": last, "errors": errs, "latest": latest}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "record":
        print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} recorded {record()} rows")
    elif cmd == "status":
        print(json.dumps(status(), indent=1, default=str))
    else:
        print(__doc__)
