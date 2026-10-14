"""Point-in-time S&P 500 stock universe, 2016 onward, including companies that later died.

Membership: data/stocks/sp500_ticker_start_end.csv (github.com/fja05680/sp500, MIT; each ticker with
the dates it entered and left the index). Prices: Alpaca daily bars (split- and dividend-adjusted),
which keep delisted tickers (SIVB, FRC, ...) and file renamed companies under their current ticker
(FB -> META), so a renamed ticker is linked to its successor when Alpaca has no bars for the old one.

    .venv/bin/python -m stocks.universe build     # download/refresh prices into data/stocks/bars.db
    .venv/bin/python -m stocks.universe report    # coverage: members per day with prices

In code: members_on(date) -> set of tickers; prices(tickers, start, end) -> DataFrame.
Backtests must still cut at backtest.SEALED_START (2024-01-30).
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "stocks"
MEMBERS = DIR / "sp500_ticker_start_end.csv"
DB = DIR / "bars.db"
START = "2016-01-01"


def membership():
    d = pd.read_csv(MEMBERS, parse_dates=["start_date", "end_date"])
    return d[(d.end_date.isna()) | (d.end_date >= START)].reset_index(drop=True)


def connect():
    DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS bars (symbol TEXT, day TEXT, open REAL, high REAL, low REAL, close REAL,
                                         volume REAL, PRIMARY KEY (symbol, day));
        CREATE TABLE IF NOT EXISTS aliases (ticker TEXT PRIMARY KEY, alpaca_symbol TEXT, reason TEXT);
    """)
    return c


def fetch(symbols, start=START, end=None):
    sys.path.insert(0, str(ROOT))
    import broker
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    client = broker.data_client()
    out = []
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i + 50]
        for attempt in range(4):
            try:
                df = client.get_stock_bars(StockBarsRequest(
                    symbol_or_symbols=chunk, timeframe=TimeFrame.Day, adjustment="all",
                    start=datetime.fromisoformat(start), end=datetime.fromisoformat(end) if end else None)).df
                break
            except Exception as e:
                if attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))
        if len(df):
            df = df.reset_index()
            df["day"] = df["timestamp"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
            out.append(df[["symbol", "day", "open", "high", "low", "close", "volume"]])
        print(f"  prices {min(i + 50, len(symbols))}/{len(symbols)}", flush=True)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _closes(conn, symbol, start, end):
    return pd.read_sql("SELECT day, close FROM bars WHERE symbol = ? AND day >= ? AND day < ?", conn,
                       params=(symbol, start, end)).set_index("day").close


def resolve_aliases(conn, m, min_corr=0.98, min_days=60):
    """Link a renamed ticker to the ticker that replaced it in the index on the same day (FB -> META),
    so the company has one consistently adjusted history.

    A same-day replacement is usually a DIFFERENT company, so a link needs strong evidence that both
    tickers are the same company: on at least `min_days` days that both traded during the old ticker's
    membership, their daily returns must correlate at `min_corr` or more AND their closes must agree
    (median ratio within 10%). Price level alone is not enough: unrelated stocks can sit at similar
    prices for years. Old tickers with no bars of their own are never linked by guesswork."""
    have = {s for (s,) in conn.execute("SELECT DISTINCT symbol FROM bars")}
    rows = []
    for r in m.itertuples():
        if pd.isna(r.end_date) or r.ticker not in have:
            continue
        lo = max(r.start_date, pd.Timestamp(START)).strftime("%Y-%m-%d")
        hi = r.end_date.strftime("%Y-%m-%d")
        for succ in m[(m.start_date == r.end_date) & (m.ticker != r.ticker)].ticker:
            if succ not in have or not m[(m.ticker == succ) & (m.start_date < r.end_date)].empty:
                continue
            old, new = _closes(conn, r.ticker, lo, hi), _closes(conn, succ, lo, hi)
            both = old.index.intersection(new.index)
            if len(both) < min_days:
                continue
            o, n = old[both], new[both]
            corr = float(np.log(o).diff().corr(np.log(n).diff()))
            ratio = float((n / o).median())
            if corr >= min_corr and 0.9 <= ratio <= 1.1:
                rows.append((r.ticker, succ, f"same company: daily returns correlate {corr:.3f}, "
                                             f"price ratio {ratio:.3f}, {len(both)} shared days"))
                break
    conn.execute("DELETE FROM aliases")
    conn.executemany("INSERT OR REPLACE INTO aliases VALUES (?, ?, ?)", rows)
    conn.commit()
    return rows


def fill_missing(conn, m):
    """Batch requests can silently drop tickers; fetch each ticker with no bars on its own."""
    have = {s for (s,) in conn.execute("SELECT DISTINCT symbol FROM bars")}
    missing = sorted(set(m.ticker) - have)
    got = []
    for t in missing:
        df = fetch([t])
        if len(df):
            conn.executemany("INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?)", df.itertuples(index=False, name=None))
            got.append(t)
    conn.commit()
    return missing, got


def build():
    m = membership()
    conn = connect()
    tickers = sorted(set(m.ticker))
    last = conn.execute("SELECT MAX(day) FROM bars").fetchone()[0]
    df = fetch(tickers, start=last or START)
    if len(df):
        conn.executemany("INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?)", df.itertuples(index=False, name=None))
        conn.commit()
    missing, got = fill_missing(conn, m)
    print(f"fetched individually: {len(got)} of {len(missing)} tickers the batches missed")
    aliases = resolve_aliases(conn, m)
    print(f"{len(tickers)} tickers, {conn.execute('SELECT COUNT(DISTINCT symbol) FROM bars').fetchone()[0]} with prices, "
          f"{len(aliases)} renames linked, {conn.execute('SELECT COUNT(*) FROM bars').fetchone()[0]:,} daily bars")


def members_on(day, m=None):
    m = membership() if m is None else m
    t = pd.Timestamp(day)
    return set(m[(m.start_date <= t) & ((m.end_date.isna()) | (m.end_date > t))].ticker)


def alpaca_symbol(ticker, conn=None):
    conn = conn or connect()
    r = conn.execute("SELECT alpaca_symbol FROM aliases WHERE ticker = ?", (ticker,)).fetchone()
    return r[0] if r else ticker


def prices(tickers, start=START, end=None, conn=None, m=None):
    """Daily bars for index tickers (renames resolved), as rows with the index ticker as `ticker`.
    Each ticker's bars stop at the day it LEFT the index: tickers get reused by other companies
    later (POM, FB, BBBY), and those later bars must never be read as the original company.
    Bars before it joined are kept (indicator history for the same company)."""
    conn, m = conn or connect(), membership() if m is None else m
    frames = []
    for t in tickers:
        s = alpaca_symbol(t, conn)
        ends = m[m.ticker == t].end_date
        stop = None if ends.isna().any() or ends.empty else ends.max().strftime("%Y-%m-%d")
        hi = min([x for x in (end, stop) if x], default=None)
        q = "SELECT day, open, high, low, close, volume FROM bars WHERE symbol = ? AND day >= ?" + (" AND day < ?" if hi else "")
        df = pd.read_sql(q, conn, params=(s, start, hi) if hi else (s, start))
        df.insert(0, "ticker", t)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def report():
    m, conn = membership(), connect()
    have = {s for (s,) in conn.execute("SELECT DISTINCT symbol FROM bars")}
    alias = dict(conn.execute("SELECT ticker, alpaca_symbol FROM aliases").fetchall())
    rows = []
    for day in pd.date_range(START, pd.Timestamp.today(), freq="QS"):
        mem = members_on(day, m)
        priced = {t for t in mem if alias.get(t, t) in have}
        rows.append((day.date(), len(mem), len(priced)))
    print("quarter start | index members | with prices")
    for r in rows:
        print(f"  {r[0]}  {r[1]:4d}  {r[2]:4d}  ({r[2] / r[1]:.0%})")
    missing = sorted({t for t in m.ticker if alias.get(t, t) not in have})
    print(f"no prices for {len(missing)} tickers: {', '.join(missing[:40])}{' ...' if len(missing) > 40 else ''}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["build", "report"])
    a = p.parse_args()
    build() if a.cmd == "build" else report()
