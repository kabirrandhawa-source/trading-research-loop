"""Kalshi live stream recorder (authenticated websocket, read-only: it never places orders).

Subscribes to order books and trades for the current market of every series in pm/universe.py,
plus Kalshi's CF Benchmarks settlement indexes. Writes one file per UTC day, data/pm/stream-YYYY-MM-DD.db, separate from the polling recorder so
the two never wait on each other's database lock. pm/archive.py compresses finished days:
  ws_tob        every change to the best bid/ask
  ws_book       top 10 levels each side, once a second per market
  ws_trades     every trade
  index_values  BRTI and the other CF Benchmarks indexes (5 times a second, plus the 60s average)

Kalshi's pyth_value channel is NOT subscribed: it costs $1,000/month after a 7-day trial.

    python -m pm.stream
"""
import asyncio
import json
import shutil
import signal
import time

import websockets

import alerts
from pm import kalshi_auth, store, universe
from pm.sources import Kalshi, parse_ts

WS_URL = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
WS_PATH = "/trade-api/ws/v2"
CF_INDEXES = ["BRTI", "ETHUSD_RTI", "SOLUSD_RTI", "XRPUSD_RTI", "DOGEUSD_RTI"]
CHANNELS = {"orderbook_delta": True, "trade": True, "cfbenchmarks_value": True, "cfbenchmarks_value_5hz": True}
SILENCE_RECONNECT_S = 30
SIZE_ONLY_MIN_GAP_S = 0.25     # save size-only changes at most 4 times a second per market
BOOK_LEVELS = 5
MIN_FREE_GB = 15
DOWN_ALERT_S = 120


def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


class SeqGap(Exception):
    pass


def nested_value(x):
    """Float from {"value": "..."} (or a bare value); None when absent."""
    v = x.get("value") if isinstance(x, dict) else x
    return float(v) if v not in (None, "") else None


def index_value(m):
    """(value, source_ts_ms) from a CF Benchmarks message. The 5 Hz channel has value_usd and
    source_ts_ms; the 60-second channel keeps them inside the JSON string in 'data'."""
    value, ts = m.get("value_usd") or m.get("value"), m.get("source_ts_ms")
    if value in (None, "") and m.get("data"):
        raw = json.loads(m["data"]) if isinstance(m["data"], str) else m["data"]
        value, ts = raw.get("value"), ts or raw.get("time")
    return (float(value) if value not in (None, "") else None), ts


class Book:
    """One market's order book. Kalshi sends bids only: YES bids and NO bids (YES ask = 1 - NO bid)."""

    def __init__(self):
        self.side = {"yes": {}, "no": {}}

    def snapshot(self, msg):
        for side in ("yes", "no"):
            levels = msg.get(f"{side}_dollars_fp") or msg.get(f"{side}_dollars") or []
            self.side[side] = {float(p): float(q) for p, q in levels if float(q) > 0}

    def delta(self, msg):
        side, price = msg["side"], float(msg["price_dollars"])
        size = self.side[side].get(price, 0.0) + float(msg.get("delta_fp", msg.get("delta", 0)))
        if size > 1e-9:
            self.side[side][price] = size
        else:
            self.side[side].pop(price, None)

    def top(self):
        yb = max(self.side["yes"]) if self.side["yes"] else None
        nb = max(self.side["no"]) if self.side["no"] else None
        return (yb, self.side["yes"].get(yb, 0.0) if yb is not None else 0.0,
                round(1 - nb, 4) if nb is not None else None, self.side["no"].get(nb, 0.0) if nb is not None else 0.0)

    def levels(self, n=10):
        best = lambda side: sorted(self.side[side].items(), reverse=True)[:n]
        return {"yes": best("yes"), "no": best("no")}


class Stream:
    def __init__(self, series=None):
        self.series = series or universe.SERIES
        self.rest = Kalshi()
        self.key_id, self.key = kalshi_auth.load()
        self.books, self.last_tob, self.tickers = {}, {}, set()
        self.sid_seq, self.sid_channel = {}, {}
        self.next_id = 1
        self.month, self.conn = None, None
        self.last_msg = time.time()
        self.down_since, self.alerted_down = None, False
        self.running = True
        self.raw_seen = {}
        self.bad_msgs = 0
        self.disk_ok = True
        self.gaps = {}                 # messages missed per non-book channel

    def db(self):
        name = store.day_name("stream")
        if name != self.month:
            if self.conn:
                self.conn.commit()
                self.conn.close()
            self.conn, self.month = store.connect(name), name
        return self.conn

    def open_tickers(self):
        now, out = time.time(), set()
        for s in self.series:
            try:
                for m in self.rest.markets_for(s, "open", limit=5):
                    if parse_ts(m["open_time"]) <= now < parse_ts(m["close_time"]):
                        out.add(m["ticker"])
            except Exception as e:
                log(f"{s} lookup error: {e}")
        return out

    async def send(self, ws, cmd, params):
        msg = {"id": self.next_id, "cmd": cmd, "params": params}
        self.next_id += 1
        await ws.send(json.dumps(msg))

    async def subscribe_markets(self, ws, tickers):
        tickers = sorted(tickers)
        for ch in ("orderbook_delta", "trade"):
            if CHANNELS[ch] and tickers:
                await self.send(ws, "subscribe", {"channels": [ch], "market_tickers": tickers})

    def check_seq(self, d):
        """A gap in an order-book feed means our book may be wrong, so resync. A gap in trades or
        index values only means a missing row, so just count it."""
        sid, seq = d.get("sid"), d.get("seq")
        if sid is None or seq is None:
            return
        last = self.sid_seq.get(sid)
        self.sid_seq[sid] = seq
        if last is None or seq == last + 1 or d.get("type") == "orderbook_snapshot":
            return
        if d.get("type") == "orderbook_delta":
            raise SeqGap(f"order book sid {sid}: expected seq {last + 1}, got {seq}")
        self.gaps[d.get("type")] = self.gaps.get(d.get("type"), 0) + max(1, seq - last - 1)

    def handle(self, d, now):
        typ = d.get("type")
        m = d.get("msg", d)
        if typ in ("orderbook_snapshot", "orderbook_delta", "trade", "cfbenchmarks_value", "cfbenchmarks_value_5hz"):
            self.check_seq(d)
        conn = self.db()
        if typ == "orderbook_snapshot":
            b = self.books.setdefault(m["market_ticker"], Book())
            b.snapshot(m)
            self.write_tob(conn, m["market_ticker"], now, d.get("seq"))
        elif typ == "orderbook_delta":
            t = m["market_ticker"]
            if t not in self.books:
                return                                   # delta before snapshot: ignore until snapshot
            self.books[t].delta(m)
            self.write_tob(conn, t, now, d.get("seq"))
        elif not self.disk_ok:
            return
        elif typ == "trade":
            conn.execute("INSERT INTO ws_trades VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (now, m.get("ts_ms"), m["market_ticker"], float(m["yes_price_dollars"]),
                          float(m.get("count_fp", 0)), m.get("taker_side"), m.get("trade_id")))
        elif typ in ("cfbenchmarks_value", "cfbenchmarks_value_5hz"):
            value, source_ts = index_value(m)
            conn.execute("INSERT INTO index_values VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (now, "5hz" if typ.endswith("5hz") else "60s", m.get("index_id"), value, source_ts,
                          m.get("received_at"),
                          nested_value(m.get("avg_60s_data")),
                          nested_value(m.get("last_60s_windowed_average_15min"))))
        elif typ == "subscribed":
            self.sid_channel[m.get("sid")] = m.get("channel")
        elif typ == "error":
            log(f"server error: {json.dumps(d)[:300]}")
        else:
            n = self.raw_seen.get(typ, 0)
            if n < 50:
                self.raw_seen[typ] = n + 1
                conn.execute("INSERT INTO ws_raw VALUES (?, ?, ?)", (now, typ, json.dumps(d)[:5000]))

    def write_tob(self, conn, ticker, now, seq):
        """Every price change is saved; changes in size only are thinned to 4 a second."""
        top = self.books[ticker].top()
        last = self.last_tob.get(ticker)
        if last and top == last[0]:
            return
        price_changed = not last or (top[0], top[2]) != (last[0][0], last[0][2])
        if price_changed or now - last[1] >= SIZE_ONLY_MIN_GAP_S:
            self.last_tob[ticker] = (top, now)
            if self.disk_ok:
                conn.execute("INSERT INTO ws_tob VALUES (?, ?, ?, ?, ?, ?, ?)", (now, ticker, *top, seq))

    def snapshot_books(self, now):
        if not self.disk_ok:
            return
        conn = self.db()
        for t in list(self.books):
            if t in self.tickers:
                conn.execute("INSERT INTO ws_book VALUES (?, ?, ?)",
                             (now, t, json.dumps(self.books[t].levels(BOOK_LEVELS), separators=(",", ":"))))

    def check_disk(self):
        """Pause all writes below MIN_FREE_GB free, with one urgent alert; resume when space returns."""
        free_gb = shutil.disk_usage(store.DATA if store.DATA.exists() else ".").free / 1e9
        if free_gb < MIN_FREE_GB and self.disk_ok:
            self.disk_ok = False
            alerts.send("Kalshi stream paused: disk low", f"Only {free_gb:.1f} GB free. Recording paused "
                        f"until more than {MIN_FREE_GB} GB is free.", "urgent", ["floppy_disk"])
        elif free_gb >= MIN_FREE_GB + 1 and not self.disk_ok:
            self.disk_ok = True
            alerts.send("Kalshi stream resumed", f"{free_gb:.1f} GB free; recording again.", "default", ["white_check_mark"])

    async def housekeeping(self, ws):
        """Once a second: book snapshots, commits, new markets, silence detection."""
        last_lookup = 0.0
        while True:
            await asyncio.sleep(1.0)
            now = time.time()
            self.snapshot_books(now)
            self.db().commit()
            if int(now) % 60 == 0:
                self.check_disk()
            if int(now) % 3600 == 0 and self.gaps:
                log(f"missed messages in the last hour (non-book channels): {self.gaps}")
                self.gaps = {}
            if now - last_lookup > 20:
                last_lookup = now
                current = await asyncio.get_running_loop().run_in_executor(None, self.open_tickers)
                new = current - self.tickers
                for gone in self.tickers - current:
                    self.books.pop(gone, None)
                    self.last_tob.pop(gone, None)
                self.tickers = current
                if new:
                    await self.subscribe_markets(ws, new)
                    log(f"subscribed {len(new)} new market(s): {', '.join(sorted(new))}")
            if now - self.last_msg > SILENCE_RECONNECT_S:
                raise ConnectionError(f"no messages for {now - self.last_msg:.0f}s")

    async def session(self):
        hdrs = kalshi_auth.headers(self.key_id, self.key, "GET", WS_PATH)
        async with websockets.connect(WS_URL, additional_headers=hdrs, ping_interval=10,
                                      max_size=2 ** 23, open_timeout=15) as ws:
            self.books, self.last_tob, self.sid_seq, self.sid_channel = {}, {}, {}, {}
            self.tickers = await asyncio.get_running_loop().run_in_executor(None, self.open_tickers)
            await self.subscribe_markets(ws, self.tickers)
            for ch in ("cfbenchmarks_value", "cfbenchmarks_value_5hz"):
                if CHANNELS[ch]:
                    await self.send(ws, "subscribe", {"channels": [ch], "index_ids": CF_INDEXES})
            log(f"connected; {len(self.tickers)} markets")
            self.last_msg = time.time()
            self.on_up()
            hk = asyncio.create_task(self.housekeeping(ws))
            try:
                n = 0
                async for raw in ws:
                    if hk.done():
                        hk.result()                      # surfaces housekeeping errors
                    now = time.time()
                    self.last_msg = now
                    try:
                        self.handle(json.loads(raw), now)
                    except SeqGap:
                        raise
                    except Exception as e:               # one bad message must not drop the connection
                        self.bad_msgs += 1
                        if self.bad_msgs <= 20:
                            log(f"skipped a message ({type(e).__name__}: {e}): {str(raw)[:200]}")
                    n += 1
                    if n % 200 == 0:
                        await asyncio.sleep(0)           # let the once-a-second housekeeping run
            finally:
                hk.cancel()
                self.db().commit()

    def on_up(self):
        if self.alerted_down:
            alerts.send("Kalshi stream recovered", "Live order books are streaming again.", "default",
                        ["white_check_mark"])
        self.down_since, self.alerted_down = None, False

    def on_down(self, why):
        self.down_since = self.down_since or time.time()
        if not self.alerted_down and time.time() - self.down_since > DOWN_ALERT_S:
            self.alerted_down = True
            alerts.send("Kalshi stream down", f"Disconnected for over {DOWN_ALERT_S}s: {why}"[:300], "high",
                        ["warning"])

    async def run(self):
        backoff = 1
        while self.running:
            try:
                await self.session()
                backoff = 1
            except SeqGap as e:
                log(f"sequence gap, resyncing: {e}")
                backoff = 1
            except websockets.InvalidStatus as e:
                code = getattr(e.response, "status_code", "?")
                log(f"handshake rejected (HTTP {code}). Check KALSHI_API_KEY_ID and the key file.")
                self.on_down(f"handshake rejected (HTTP {code})")
                backoff = max(backoff, 60)
            except Exception as e:
                log(f"disconnected: {type(e).__name__}: {e}")
                self.on_down(f"{type(e).__name__}: {e}")
            if self.running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def stop(self):
        self.running = False
        for task in asyncio.all_tasks():
            task.cancel()


def main():
    try:
        s = Stream()
    except kalshi_auth.MissingKey as e:
        log(f"not starting: {e}")
        raise SystemExit(2)
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, s.stop)
    log("stream recorder starting (read-only; pyth_value not subscribed)")
    try:
        loop.run_until_complete(s.run())
    except asyncio.CancelledError:
        pass
    finally:
        if s.conn:
            s.conn.commit()
        log("stream recorder stopped")


if __name__ == "__main__":
    main()
