"""Live recorder for Kalshi's 15-minute markets across asset types (read-only, no account needed).

Tracks every series in pm/universe.py. Each 1-second tick, for the series that are due:
the current market's order book (top 10 levels each side), plus spot prices from that asset's
free sources (Coinbase, Kraken, Binance.US, Bitstamp, and Pyth when PYTH_API_KEY is set in
config/.env). Outcomes are stored as each window settles. Writes data/pm/live-YYYY-MM-DD.db (one file
per UTC day; pm/archive.py compresses finished days).

    python -m pm.record
"""
import json
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

import alerts
from pm import store, universe
from pm.sources import (Http, Kalshi, best_quotes, binanceus_quotes, bitstamp_quote, coinbase_quote,
                        kraken_quotes, parse_ts, pyth_quotes)

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

STALL_ALERT_S = 120
PYTH_EVERY_S = 2          # Pyth's public limit is about 10 requests per 10 seconds


def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


class Recorder:
    def __init__(self, series=None, books=None):
        self.series = series or universe.SERIES
        # Kalshi order books now come from pm/stream.py (live websocket). Polling them is only a
        # fallback: set PM_POLL_BOOKS=1 if the stream is unavailable.
        self.books = (os.getenv("PM_POLL_BOOKS", "0") == "1") if books is None else books
        self.kalshi = Kalshi(Http(min_interval=0.05))
        self.http = {k: Http(min_interval=0.0) for k in ("coinbase", "kraken", "binanceus", "bitstamp", "pyth")}
        self.pyth_key = os.getenv("PYTH_API_KEY", "").strip()
        self.pool = ThreadPoolExecutor(max_workers=12)
        self.markets = {}          # series -> current open market (or None)
        self.next_lookup = {}      # series -> time to look for an open market again
        self.pending_settle = {}   # ticker -> close_ts
        self.last_book_ok = time.time()
        self.last_health = time.time()
        self.stalled = False
        self.running = True
        self.month, self.conn = None, None
        self.tick_n = 0
        self.inflight = []         # (kind, key, future, started)

    def db(self):
        name = store.day_name("live")
        if name != self.month:
            if self.conn:
                self.conn.commit()
                self.conn.close()
            self.conn, self.month = store.connect(name), name
        return self.conn

    # ----- markets -----

    def current_market(self, series, now):
        m = self.markets.get(series)
        if m and now < parse_ts(m["close_time"]):
            return m
        if m:
            self.pending_settle[m["ticker"]] = parse_ts(m["close_time"])
            self.markets[series] = None
        if now < self.next_lookup.get(series, 0):
            return None
        live = [x for x in self.kalshi.markets_for(series, "open", limit=5)
                if parse_ts(x["open_time"]) <= now < parse_ts(x["close_time"])]
        if live:
            m = min(live, key=lambda x: parse_ts(x["close_time"]))
            self.markets[series] = m
            store.upsert_market(self.db(), m, parse_ts)
            return m
        self.next_lookup[series] = now + 60      # closed (e.g. outside trading hours): check each minute
        return None

    def settle(self, now):
        for ticker, close_ts in list(self.pending_settle.items()):
            if now < close_ts + 15:
                continue
            m = self.kalshi.market(ticker)
            if m.get("result") in ("yes", "no"):
                store.upsert_market(self.db(), m, parse_ts)
                del self.pending_settle[ticker]
            elif now > close_ts + 3600:
                del self.pending_settle[ticker]

    # ----- spot -----

    def spot_jobs(self, due):
        """[(source, asset, callable returning {asset: quote})] for the series due this tick."""
        cfgs = [self.series[s] for s in due]
        jobs = []
        for c in cfgs:
            if c.get("coinbase"):
                jobs.append(("coinbase", lambda c=c: {c["asset"]: coinbase_quote(self.http["coinbase"], c["coinbase"])}))
            if c.get("bitstamp"):
                jobs.append(("bitstamp", lambda c=c: {c["asset"]: bitstamp_quote(self.http["bitstamp"], c["bitstamp"])}))
        kr = {c["kraken"]: c["asset"] for c in cfgs if c.get("kraken")}
        if kr:
            jobs.append(("kraken", lambda: {kr[p]: q for p, q in kraken_quotes(self.http["kraken"], list(kr)).items()}))
        bn = {c["binanceus"]: c["asset"] for c in cfgs if c.get("binanceus")}
        if bn:
            jobs.append(("binanceus", lambda: {bn[s]: q for s, q in binanceus_quotes(self.http["binanceus"], list(bn)).items()}))
        if self.pyth_key and self.tick_n % PYTH_EVERY_S == 0:
            py = {universe.PYTH_IDS[c["pyth"]]: c["asset"] for c in cfgs if c.get("pyth")}
            if py:
                jobs.append(("pyth", lambda: {py[i]: q for i, q in pyth_quotes(self.http["pyth"], self.pyth_key, list(py)).items()}))
        return jobs

    @staticmethod
    def timed(fn):
        t0 = time.time()
        out = fn()
        return out, t0, (time.time() - t0) * 1000

    def tick(self):
        """Launch this tick's requests without waiting for them; save whatever has finished."""
        now = time.time()
        self.drain()
        due = [s for i, (s, c) in enumerate(self.series.items()) if universe.due(c, self.tick_n, i)]
        for src, fn in self.spot_jobs(due):
            self.inflight.append(("spot", src, self.pool.submit(self.timed, fn), now))
        for s in due:
            try:
                m = self.current_market(s, now)
            except Exception as e:
                log(f"{s} market lookup error: {e}")
                continue
            if m and self.books:
                fut = self.pool.submit(self.timed, lambda t=m["ticker"]: self.kalshi.orderbook(t))
                self.inflight.append(("book", m["ticker"], fut, now))
        if self.tick_n % 5 == 0:
            try:
                self.settle(now)
            except Exception as e:
                log(f"settle error: {e}")

    def drain(self):
        """Write finished requests to the database; drop any stuck for more than 15 seconds."""
        conn, keep = self.db(), []
        for kind, key, fut, started in self.inflight:
            if not fut.done():
                if time.time() - started > 15:
                    fut.cancel()
                    log(f"{key} request timed out")
                else:
                    keep.append((kind, key, fut, started))
                continue
            try:
                out, t0, ms = fut.result()
                if kind == "spot":
                    conn.executemany("INSERT INTO spot_ticks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                     [(t0 + ms / 2000, key, q["price"], q["bid"], q["ask"], q["ts_exchange"], ms, asset)
                                      for asset, q in out.items()])
                else:
                    yes_bids, no_bids = out
                    q = best_quotes(yes_bids, no_bids)
                    conn.execute("INSERT INTO book VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                 (t0 + ms / 2000, key, q["yes_bid"], q["yes_bid_size"], q["yes_ask"],
                                  q["yes_ask_size"], json.dumps({"yes": yes_bids, "no": no_bids}), ms))
                    if key.startswith("KXBTC15M"):
                        self.last_book_ok = time.time()
            except Exception as e:
                log(f"{key} error: {type(e).__name__}: {e}")
        self.inflight = keep

    def health(self):
        """Alert when Bitcoin (open 24/7, so it should never be quiet) stops recording."""
        if not self.books:
            return                     # the stream has its own health alerts
        now = time.time()
        if now - self.last_health > 30:     # the loop itself was paused: the Mac slept, not a failure
            self.last_book_ok = now
        self.last_health = now
        gap = now - self.last_book_ok
        if gap > STALL_ALERT_S and not self.stalled:
            self.stalled = True
            alerts.send("Kalshi recorder stalled", f"No Bitcoin order book saved for {gap:.0f}s. "
                        "Check logs/pm_record.log.", "high", ["warning"])
        elif gap <= STALL_ALERT_S and self.stalled:
            self.stalled = False
            alerts.send("Kalshi recorder recovered", "Order books are being saved again.", "default",
                        ["white_check_mark"])

    def stop(self, *_):
        self.running = False

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        log(f"recorder started: {len(self.series)} series, Kalshi books {'polled' if self.books else 'off (pm/stream.py records them)'}, "
            f"Pyth {'on' if self.pyth_key else 'off (no PYTH_API_KEY)'}")
        last_commit = time.time()
        next_tick = time.time()
        while self.running:
            try:
                self.tick()
            except Exception as e:
                log(f"tick error: {type(e).__name__}: {e}")
            self.health()
            self.tick_n += 1
            if time.time() - last_commit > 10:
                self.db().commit()
                last_commit = time.time()
            next_tick += 1.0                      # fixed 1-second grid, so slow requests don't drift it
            if next_tick < time.time() - 5:       # fell far behind (e.g. laptop slept): resync
                next_tick = time.time()
            time.sleep(max(0.0, next_tick - time.time()))
        time.sleep(1.0)
        self.drain()
        self.db().commit()
        log("recorder stopped")


if __name__ == "__main__":
    Recorder().run()
