"""Intraday index CFD bars from Dukascopy's free public datafeed (read-only, no account).

DAX (DEU.IDX/EUR) and UK100 (GBR.IDX/GBP) CFDs quote nearly around the clock, so the Asian session
exists in the data (the cash indices only trade in European hours). Minute bars, bid and ask, are
decoded and stored as 5-minute bars in data/intraday/bars.db, timestamps in UTC.

Only days before backtest.SEALED_START are ever downloaded: the sealed period stays unseen.

    .venv/bin/python -m intraday.data build            # download / top up, 2013 to the sealed date
"""
import argparse
import lzma
import sqlite3
import struct
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "intraday" / "bars.db"
SYMBOLS = {"DAX": "DEUIDXEUR", "UK100": "GBRIDXGBP"}
SCALE = 1000.0           # Dukascopy index prices are integers x 1000
FIRST_DAY = date(2013, 1, 1)
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/{side}_candles_min_1.bi5"
PAUSE = 1.0             # seconds between requests; the feed throttles bursts
UA = {"User-Agent": "trading-research-loop (personal research; read-only)"}


def sealed_start():
    import backtest
    return date.fromisoformat(backtest.SEALED_START)


def connect(db=None):
    db = Path(db or DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS bars (symbol TEXT, ts TEXT, bid_open REAL, bid_high REAL, bid_low REAL,
            bid_close REAL, ask_open REAL, ask_high REAL, ask_low REAL, ask_close REAL, volume REAL,
            PRIMARY KEY (symbol, ts));
        CREATE TABLE IF NOT EXISTS days_done (symbol TEXT, day TEXT, n_bars INTEGER, PRIMARY KEY (symbol, day));
    """)
    return c


def decode(raw, day):
    """bi5 minute candles -> list of (ts_utc, open, high, low, close, volume); empty minutes dropped."""
    if not raw:
        return []
    b = lzma.decompress(raw)
    base = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    out = []
    for i in range(len(b) // 24):
        secs, o, c, lo, hi, v = struct.unpack(">5If", b[i * 24:(i + 1) * 24])
        if v <= 0:
            continue
        out.append((base + timedelta(seconds=secs), o / SCALE, hi / SCALE, lo / SCALE, c / SCALE, v))
    return out


def to_5min(bid, ask):
    """Join bid and ask minutes and aggregate to 5-minute bars labelled by their start time."""
    ask_by_ts = {r[0]: r for r in ask}
    buckets = {}
    for ts, o, h, l, c, v in bid:
        a = ask_by_ts.get(ts)
        if a is None:
            continue
        key = ts.replace(minute=ts.minute - ts.minute % 5, second=0)
        cur = buckets.get(key)
        if cur is None:
            buckets[key] = [o, h, l, c, a[1], a[2], a[3], a[4], v]
        else:
            cur[1], cur[2], cur[3] = max(cur[1], h), min(cur[2], l), c
            cur[5], cur[6], cur[7] = max(cur[5], a[2]), min(cur[6], a[3]), a[4]
            cur[8] += v
    return [(k.strftime("%Y-%m-%dT%H:%M:%SZ"), *v) for k, v in sorted(buckets.items())]


def fetch_side(session, sym, day, side):
    url = URL.format(sym=sym, y=day.year, m=day.month - 1, d=day.day, side=side)   # month is 0-based
    for attempt in range(12):
        time.sleep(PAUSE)
        try:
            r = session.get(url, headers=UA, timeout=30)
        except requests.RequestException:     # the feed throttles: drops connections for minutes at a time
            time.sleep(min(30 * 2 ** attempt, 600))
            continue
        if r.status_code == 404:
            return b""
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(30 * 2 ** attempt, 600))
            continue
        r.raise_for_status()
        return r.content
    raise RuntimeError(f"{url}: still failing after 12 tries")


def fetch_day(session, name, day):
    if day >= sealed_start():
        raise ValueError(f"{day} is sealed (on/after {sealed_start()}); refusing to download")
    sym = SYMBOLS[name]
    bid = decode(fetch_side(session, sym, day, "BID"), day)
    ask = decode(fetch_side(session, sym, day, "ASK"), day)
    return name, day, to_5min(bid, ask)


def build(start=FIRST_DAY, end=None):
    end = min(end or sealed_start(), sealed_start())
    conn = connect()
    done = set(conn.execute("SELECT symbol, day FROM days_done"))
    todo = []
    d = start
    while d < end:
        if d.weekday() < 5:
            todo += [(n, d) for n in SYMBOLS if (n, d.isoformat()) not in done]
        d += timedelta(days=1)
    print(f"{len(todo)} symbol-days to fetch ({start} to {end - timedelta(days=1)})", flush=True)
    session = requests.Session()
    for i, (name, day) in enumerate(todo):
        _, _, rows = fetch_day(session, name, day)
        conn.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         [(name, *r) for r in rows])
        conn.execute("INSERT OR REPLACE INTO days_done VALUES (?,?,?)", (name, day.isoformat(), len(rows)))
        conn.commit()
        if i % 50 == 0:
            print(f"  {i}/{len(todo)} {name} {day} {len(rows)} bars", flush=True)
    return conn


def load(name, conn=None):
    """5-minute bars for one symbol as a DataFrame indexed by UTC time, with mid prices and spread."""
    import pandas as pd
    conn = conn or connect()
    df = pd.read_sql("SELECT * FROM bars WHERE symbol = ? ORDER BY ts", conn, params=(name,))
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts")
    df = df[df.index < pd.Timestamp(sealed_start().isoformat(), tz="UTC")]
    for k in ("open", "high", "low", "close"):
        df[k] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2
    df["spread"] = df["ask_close"] - df["bid_close"]
    return df


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build"])
    p.add_argument("--start", default=FIRST_DAY.isoformat())
    a = p.parse_args()
    build(date.fromisoformat(a.start))
