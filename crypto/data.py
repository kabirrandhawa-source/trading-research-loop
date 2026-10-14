"""Crypto research data from US-based exchanges' free public APIs (read-only, no account).

- Daily prices: Coinbase (api.exchange.coinbase.com), each coin from its first Coinbase listing.
- Perpetual-futures funding rates, hourly: Coinbase International (history since its 2023 launch)
  and Kraken Futures (last 12 months only; a cross-check).

Not used, by decision: Binance.com, Bybit (block US users), OKX and Deribit (their terms exclude US
residents), even where the public endpoint answers.

    .venv/bin/python -m crypto.data build      # download / top up data/crypto/crypto.db
"""
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "crypto" / "crypto.db"
COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
KRAKEN = {"BTC": "PF_XBTUSD", "ETH": "PF_ETHUSD", "SOL": "PF_SOLUSD", "XRP": "PF_XRPUSD", "DOGE": "PF_DOGEUSD"}
UA = {"User-Agent": "trading-research-loop (personal research; read-only)"}


def connect(db=None):
    db = Path(db or DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS candles (coin TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL,
                                            volume REAL, PRIMARY KEY (coin, day));
        CREATE TABLE IF NOT EXISTS funding (source TEXT, coin TEXT, ts TEXT, rate REAL,
                                            PRIMARY KEY (source, coin, ts));
    """)
    return c


def get(url, **params):
    for attempt in range(5):
        r = requests.get(url, params=params or None, headers=UA, timeout=20)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def coinbase_daily(coin, since=None):
    """All daily candles for COIN-USD, oldest first. Coinbase returns at most 300 per request."""
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    stop = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else datetime(2015, 1, 1, tzinfo=timezone.utc)
    rows = []
    while end > stop:
        start = max(stop, end - timedelta(days=300))
        batch = get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles", granularity=86400,
                    start=start.isoformat(), end=end.isoformat())
        if not batch and rows:
            break
        rows += [(coin, datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), o, h, l, c, v)
                 for t, l, h, o, c, v in batch]
        end = start
        time.sleep(0.15)
    return sorted(set(rows), key=lambda r: r[1])


def coinbase_intl_funding(coin, known=None):
    """Hourly funding rates for COIN-PERP on Coinbase International, newest pages first until a
    timestamp we already have (or the start of history)."""
    out, off = [], 0
    while True:
        page = get(f"https://api.international.coinbase.com/api/v1/instruments/{coin}-PERP/funding",
                   result_limit=100, result_offset=off).get("results", [])
        if not page:
            break
        out += [("coinbase_intl", coin, r["event_time"], float(r["funding_rate"])) for r in page]
        if known and page[-1]["event_time"] <= known:
            break
        off += len(page)
        time.sleep(0.12)
    return out


def kraken_funding(coin):
    d = get("https://futures.kraken.com/derivatives/api/v4/historicalfundingrates", symbol=KRAKEN[coin])
    return [("kraken", coin, r["timestamp"], float(r["relativeFundingRate"])) for r in d.get("rates", [])]


def build():
    c = connect()
    for coin in COINS:
        last = c.execute("SELECT MAX(day) FROM candles WHERE coin = ?", (coin,)).fetchone()[0]
        rows = coinbase_daily(coin, since=last)
        c.executemany("INSERT OR REPLACE INTO candles VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        known = c.execute("SELECT MAX(ts) FROM funding WHERE source='coinbase_intl' AND coin = ?", (coin,)).fetchone()[0]
        f = coinbase_intl_funding(coin, known)
        f += kraken_funding(coin)
        c.executemany("INSERT OR REPLACE INTO funding VALUES (?, ?, ?, ?)", f)
        c.commit()
        span = c.execute("SELECT MIN(day), MAX(day), COUNT(*) FROM candles WHERE coin = ?", (coin,)).fetchone()
        fs = c.execute("SELECT MIN(ts), COUNT(*) FROM funding WHERE source='coinbase_intl' AND coin = ?", (coin,)).fetchone()
        print(f"{coin}: daily {span[0]} -> {span[1]} ({span[2]} days); Coinbase Intl funding since {fs[0]} ({fs[1]} hours)", flush=True)


if __name__ == "__main__":
    build()
