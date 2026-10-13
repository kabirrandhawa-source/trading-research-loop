"""Download history for Kalshi's 15-minute Bitcoin markets into data/pm/history.db.

    python -m pm.backfill --days 14          # outcomes + 1-minute odds + Kraken BTC trades
    python -m pm.backfill --days 3 --trades  # also every Kalshi trade (heavy: many pages per window)

Safe to re-run: it skips what's already stored and resumes where it stopped.
"""
import argparse
import time

from pm import store
from pm.sources import Http, Kalshi, kraken_trades, parse_ts


def backfill_markets(conn, kalshi, since_ts, series=None):
    n = 0
    for m in kalshi.markets("settled", **({"series": series} if series else {})):
        close = parse_ts(m["close_time"])
        if close < since_ts:
            break
        if m.get("result") in ("yes", "no"):
            store.upsert_market(conn, m, parse_ts)
            n += 1
        if n % 200 == 0:
            conn.commit()
    conn.commit()
    return n


def backfill_candles(conn, kalshi, since_ts, series=None):
    todo = conn.execute(
        "SELECT ticker, open_ts, close_ts FROM markets m WHERE close_ts >= ? AND ticker LIKE ? AND NOT EXISTS "
        "(SELECT 1 FROM candles c WHERE c.ticker = m.ticker) ORDER BY close_ts",
        (since_ts, f"{series}-%" if series else "%")).fetchall()
    for i, (ticker, open_ts, close_ts) in enumerate(todo):
        rows = []
        for c in kalshi.candles(ticker, open_ts - 60, close_ts + 60):
            f = lambda k, sub: float(c[k][sub]) if c.get(k) and c[k].get(sub) not in (None, "") else None
            rows.append((ticker, float(c["end_period_ts"]), f("yes_bid", "close_dollars"),
                         f("yes_ask", "close_dollars"), f("price", "close_dollars"),
                         float(c.get("volume_fp") or 0)))
        conn.executemany("INSERT OR IGNORE INTO candles VALUES (?, ?, ?, ?, ?, ?)", rows)
        if i % 20 == 0:
            conn.commit()
            print(f"  candles {i + 1}/{len(todo)}", flush=True)
    conn.commit()
    return len(todo)


def backfill_kalshi_trades(conn, kalshi, since_ts):
    todo = conn.execute(
        "SELECT ticker FROM markets m WHERE close_ts >= ? AND NOT EXISTS "
        "(SELECT 1 FROM kalshi_trades t WHERE t.ticker = m.ticker) ORDER BY close_ts", (since_ts,)).fetchall()
    for i, (ticker,) in enumerate(todo):
        rows = [(t["trade_id"], ticker, parse_ts(t["created_time"]), float(t["yes_price_dollars"]),
                 float(t["count_fp"]), t.get("taker_side")) for t in kalshi.trades(ticker)]
        conn.executemany("INSERT OR IGNORE INTO kalshi_trades VALUES (?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        print(f"  kalshi trades {i + 1}/{len(todo)} ({len(rows)} in {ticker})", flush=True)
    return len(todo)


def backfill_kraken(conn, since_ts, until_ts=None):
    """Kraken BTC/USD trades from since_ts to now (resumable)."""
    http = Http(min_interval=1.1)
    until_ts = until_ts or time.time()
    cursor = int(store.get_progress(conn, "kraken_since_ns", int(since_ts * 1e9)))
    cursor = max(cursor, int(since_ts * 1e9))
    pages = 0
    while cursor / 1e9 < until_ts - 5:
        rows, nxt = kraken_trades(cursor, http)
        conn.executemany("INSERT OR IGNORE INTO spot_trades VALUES ('kraken', ?, ?, ?, ?)",
                         [r for r in rows if r[0] is not None])
        if nxt <= cursor or not rows:
            break
        cursor = nxt
        store.set_progress(conn, "kraken_since_ns", cursor)
        pages += 1
        if pages % 25 == 0:
            print(f"  kraken up to {time.strftime('%Y-%m-%d %H:%M', time.gmtime(cursor / 1e9))} UTC", flush=True)
    conn.commit()
    return pages


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", type=float, default=14)
    p.add_argument("--trades", action="store_true", help="also fetch every Kalshi trade (slow)")
    p.add_argument("--trade-days", type=float, default=None, help="days of Kalshi trades (default --days)")
    p.add_argument("--series", nargs="*", help="other series: outcomes + 1-minute odds only (e.g. KXGOLD15M); "
                   "their settled strike/expiration values give the settlement price every 15 minutes")
    a = p.parse_args()

    conn = store.connect("history")
    kalshi = Kalshi()
    since = time.time() - a.days * 86400
    if a.series:
        for s in a.series:
            print(f"{s}: {backfill_markets(conn, kalshi, since, s)} settled windows, "
                  f"{backfill_candles(conn, kalshi, since, s)} with 1-minute odds", flush=True)
        return
    print(f"markets: {backfill_markets(conn, kalshi, since)} settled windows stored")
    print(f"candles: {backfill_candles(conn, kalshi, since)} windows fetched")
    print(f"kraken: {backfill_kraken(conn, since - 3600)} pages")
    if a.trades:
        tsince = time.time() - (a.trade_days or a.days) * 86400
        print(f"kalshi trades: {backfill_kalshi_trades(conn, kalshi, tsince)} windows fetched")


if __name__ == "__main__":
    main()
