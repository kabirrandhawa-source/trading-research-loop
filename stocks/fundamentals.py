"""Company fundamentals from SEC EDGAR (free), keyed to the date each number was FILED.

A backtest may only use a number on or after its `filed` date: that is what stops a strategy from
"knowing" earnings before they were public. Values are as originally reported in each filing
(restatements arrive later as new rows with their own filed date).

Coverage: index tickers are matched to SEC CIK numbers through SEC's current ticker list, plus
verified renames from stocks.universe (same company, same CIK). Companies that died or changed
ticker without a verified link stay UNMATCHED: SEC's name search gives wrong matches for old tickers
(e.g. "FRC" returns an unrelated "FRC, Inc."), and a wrong match would silently poison a backtest.
Tests that use fundamentals must report how many members lacked data.

Requests send the contact in config/.env SEC_CONTACT (required by SEC's fair-access policy) and stay
under SEC's 10 requests/second limit.

    .venv/bin/python -m stocks.fundamentals build      # download into data/stocks/fundamentals.db
    .venv/bin/python -m stocks.fundamentals report     # coverage by quarter
"""
import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "stocks" / "fundamentals.db"
load_dotenv(ROOT / "config" / ".env")

# metric -> XBRL tags in order of preference (companies use different tags for the same thing)
CONCEPTS = {
    "revenue": [("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("us-gaap", "SalesRevenueNet"), ("us-gaap", "RevenuesNetOfInterestExpense")],
    "net_income": [("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss")],
    "eps_diluted": [("us-gaap", "EarningsPerShareDiluted"), ("us-gaap", "EarningsPerShareBasicAndDiluted")],
    "assets": [("us-gaap", "Assets")],
    "equity": [("us-gaap", "StockholdersEquity"),
               ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")],
    "op_cash_flow": [("us-gaap", "NetCashProvidedByUsedInOperatingActivities")],
    "shares_outstanding": [("dei", "EntityCommonStockSharesOutstanding")],
}


def headers():
    contact = os.getenv("SEC_CONTACT", "").strip()
    if not contact:
        raise RuntimeError("Set SEC_CONTACT in config/.env (SEC requires a contact in the User-Agent).")
    return {"User-Agent": f"trading-research-loop {contact}", "Accept-Encoding": "gzip, deflate"}


class Sec:
    def __init__(self, min_interval=0.15):
        self.s, self.min_interval, self.last = requests.Session(), min_interval, 0.0
        self.s.headers.update(headers())

    def get(self, url):
        for attempt in range(5):
            wait = self.last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            r = self.s.get(url, timeout=60)
            if r.status_code == 404:
                return None
            if r.status_code in (403, 429) or r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()


def connect(db=None):
    db = Path(db or DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS ciks (ticker TEXT PRIMARY KEY, cik INTEGER, how TEXT);
        CREATE TABLE IF NOT EXISTS facts (ticker TEXT, cik INTEGER, metric TEXT, tag TEXT, start TEXT, end TEXT,
            val REAL, filed TEXT, form TEXT, fy INTEGER, fp TEXT, accn TEXT,
            PRIMARY KEY (cik, tag, start, end, accn));
        CREATE INDEX IF NOT EXISTS facts_t ON facts (ticker, metric, filed);
    """)
    return c


def map_ciks(sec, conn):
    sys.path.insert(0, str(ROOT))
    from stocks import universe
    m = universe.membership()
    cur = sec.get("https://www.sec.gov/files/company_tickers.json")
    t2c = {v["ticker"].upper(): int(v["cik_str"]) for v in cur.values()}
    norm = lambda t: t.upper().replace(".", "-")
    alias = dict(universe.connect().execute("SELECT ticker, alpaca_symbol FROM aliases").fetchall())
    rows = []
    for t in sorted(set(m.ticker)):
        if norm(t) in t2c:
            rows.append((t, t2c[norm(t)], "SEC current ticker list"))
        elif t in alias and norm(alias[t]) in t2c:
            rows.append((t, t2c[norm(alias[t])], f"verified rename to {alias[t]}"))
    conn.execute("DELETE FROM ciks")
    conn.executemany("INSERT INTO ciks VALUES (?, ?, ?)", rows)
    conn.commit()
    return len(rows), len(set(m.ticker))


def extract(ticker, cik, facts):
    out = []
    for metric, tags in CONCEPTS.items():
        for ns, tag in tags:
            units = facts.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {})
            for unit, items in units.items():
                for f in items:
                    if f.get("filed") and f.get("val") is not None:
                        out.append((ticker, cik, metric, tag, f.get("start"), f.get("end"), float(f["val"]),
                                    f["filed"], f.get("form"), f.get("fy"), f.get("fp"), f.get("accn")))
    return out


def build():
    sec, conn = Sec(), connect()
    n, total = map_ciks(sec, conn)
    print(f"matched {n} of {total} index tickers to SEC CIKs", flush=True)
    ciks = conn.execute("SELECT ticker, cik FROM ciks").fetchall()
    done = {c for (c,) in conn.execute("SELECT DISTINCT cik FROM facts")}
    for i, (t, cik) in enumerate(ciks):
        if cik in done:
            continue
        data = sec.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        if data:
            conn.executemany("INSERT OR IGNORE INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", extract(t, cik, data))
            done.add(cik)
        if i % 25 == 0:
            conn.commit()
            print(f"  {i + 1}/{len(ciks)}", flush=True)
    conn.commit()
    print(f"facts stored: {conn.execute('SELECT COUNT(*) FROM facts').fetchone()[0]:,}")


def latest(conn, tickers, metric, as_of):
    """The most recent value of `metric` for each ticker that had been FILED by `as_of` (YYYY-MM-DD)."""
    q = (f"SELECT ticker, end, val, filed FROM facts WHERE metric = ? AND filed <= ? AND ticker IN "
         f"({','.join('?' * len(tickers))}) ORDER BY filed")
    df = pd.read_sql(q, conn, params=(metric, as_of, *tickers))
    return df.groupby("ticker").tail(1).set_index("ticker") if len(df) else df


def covered(conn, tickers, as_of, metric="net_income", months=15):
    """Tickers with a `metric` figure filed in the `months` before `as_of`: usable on that date."""
    lo = (pd.Timestamp(as_of) - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    q = (f"SELECT DISTINCT ticker FROM facts WHERE metric = ? AND filed <= ? AND filed > ? AND ticker IN "
         f"({','.join('?' * len(tickers))})")
    return {t for (t,) in conn.execute(q, (metric, str(pd.Timestamp(as_of).date()), lo, *tickers))}


def report():
    """Honest coverage: a member counts only if it had earnings FILED in the 15 months before each date.
    Companies that re-registered under a new SEC ID (e.g. ExxonMobil in 2026) show up as gaps."""
    sys.path.insert(0, str(ROOT))
    from stocks import universe
    conn, m = connect(), universe.membership()
    print("quarter | members | usable fundamentals (earnings filed in prior 15 months)")
    gaps = {}
    for day in pd.date_range("2016-04-01", pd.Timestamp.today(), freq="QS"):
        mem = universe.members_on(day, m)
        ok = covered(conn, sorted(mem), day)
        for t in mem - ok:
            gaps[t] = gaps.get(t, 0) + 1
        print(f"  {day.date()}  {len(mem)}  {len(ok)}  ({len(ok) / len(mem):.0%})")
    mapped = {t for (t,) in conn.execute("SELECT ticker FROM ciks")}
    partial = sorted(t for t in gaps if t in mapped)
    print(f"matched to SEC but with history gaps: {len(partial)} (e.g. {', '.join(partial[:12])})")
    print(f"never matched to SEC: {len(set(gaps) - mapped)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["build", "report"])
    p.add_argument("--refresh", action="store_true", help="re-download every company (after adding tags)")
    a = p.parse_args()
    if a.cmd == "build" and a.refresh:
        connect().execute("DELETE FROM facts").connection.commit()
    build() if a.cmd == "build" else report()
