"""Live recorder for Kalshi's 15-minute Bitcoin markets (read-only, no account needed).

Every second: the current market's order book (top 10 levels each side) and Bitcoin spot
from Coinbase, Kraken and Bitstamp, fetched in parallel. Settled outcomes are stored as each
window closes. Writes data/pm/live-YYYY-MM.db. Runs forever under launchd.

    python -m pm.record
"""
import json
import signal
import time
from concurrent.futures import ThreadPoolExecutor

import alerts
from pm import store
from pm.sources import Http, Kalshi, Spot, best_quotes, parse_ts

INTERVAL = 1.0
STALL_ALERT_S = 120


class Recorder:
    def __init__(self):
        self.kalshi = Kalshi(Http(min_interval=0.05))
        self.spots = {name: Spot(Http(min_interval=0.0)) for name in ("coinbase", "kraken", "bitstamp")}
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.market = None            # current open market dict
        self.pending_settle = {}      # ticker -> close_ts
        self.last_book_ok = time.time()
        self.stalled = False
        self.running = True
        self.month = None
        self.conn = None

    def db(self):
        month = time.strftime("%Y-%m", time.gmtime())
        if month != self.month:
            if self.conn:
                self.conn.commit()
                self.conn.close()
            self.conn, self.month = store.connect(f"live-{month}"), month
        return self.conn

    def current_market(self, now):
        if self.market is None or now >= parse_ts(self.market["close_time"]):
            if self.market is not None:
                self.pending_settle[self.market["ticker"]] = parse_ts(self.market["close_time"])
            opens = list(self.kalshi.markets("open", limit=5, max_pages=1))
            live = [m for m in opens if parse_ts(m["open_time"]) <= now < parse_ts(m["close_time"])]
            self.market = min(live, key=lambda m: parse_ts(m["close_time"])) if live else None
            if self.market:
                store.upsert_market(self.db(), self.market, parse_ts)
        return self.market

    def settle(self, now):
        for ticker, close_ts in list(self.pending_settle.items()):
            if now < close_ts + 15:
                continue
            m = self.kalshi.market(ticker)
            if m.get("result") in ("yes", "no"):
                store.upsert_market(self.db(), m, parse_ts)
                del self.pending_settle[ticker]
            elif now > close_ts + 3600:
                del self.pending_settle[ticker]   # give up after an hour; backfill can fill it

    @staticmethod
    def timed(fn, *args):
        t0 = time.time()
        out = fn(*args)
        return out, t0, (time.time() - t0) * 1000

    def tick(self):
        now = time.time()
        conn = self.db()
        m = self.current_market(now)
        futures = {name: self.pool.submit(self.timed, getattr(s, name)) for name, s in self.spots.items()}
        book_f = self.pool.submit(self.timed, self.kalshi.orderbook, m["ticker"]) if m else None

        for name, f in futures.items():
            try:
                q, t0, ms = f.result(timeout=8)
                conn.execute("INSERT INTO spot_ticks VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (t0 + ms / 2000, name, q["price"], q["bid"], q["ask"], q["ts_exchange"], ms))
            except Exception as e:
                print(f"{time.strftime('%H:%M:%S')} {name} error: {e}", flush=True)
        if book_f:
            try:
                (yes_bids, no_bids), t0, ms = book_f.result(timeout=8)
                q = best_quotes(yes_bids, no_bids)
                conn.execute("INSERT INTO book VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (t0 + ms / 2000, m["ticker"], q["yes_bid"], q["yes_bid_size"], q["yes_ask"],
                              q["yes_ask_size"], json.dumps({"yes": yes_bids, "no": no_bids}), ms))
                self.last_book_ok = time.time()
            except Exception as e:
                print(f"{time.strftime('%H:%M:%S')} orderbook error: {e}", flush=True)
        try:
            self.settle(now)
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')} settle error: {e}", flush=True)

    def health(self):
        gap = time.time() - self.last_book_ok
        if gap > STALL_ALERT_S and not self.stalled:
            self.stalled = True
            alerts.send("Kalshi recorder stalled", f"No order book saved for {gap:.0f}s. Check logs/pm_record.log.",
                        "high", ["warning"])
        elif gap <= STALL_ALERT_S and self.stalled:
            self.stalled = False
            alerts.send("Kalshi recorder recovered", "Order books are being saved again.", "default",
                        ["white_check_mark"])

    def stop(self, *_):
        self.running = False

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} recorder started", flush=True)
        last_commit = time.time()
        while self.running:
            started = time.time()
            try:
                self.tick()
            except Exception as e:
                print(f"{time.strftime('%H:%M:%S')} tick error: {type(e).__name__}: {e}", flush=True)
            self.health()
            if time.time() - last_commit > 10:
                self.db().commit()
                last_commit = time.time()
            time.sleep(max(0.0, INTERVAL - (time.time() - started)))
        self.db().commit()
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} recorder stopped", flush=True)


if __name__ == "__main__":
    Recorder().run()
