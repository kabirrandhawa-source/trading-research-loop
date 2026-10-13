"""Public market-data clients: Kalshi (prediction market) and Bitcoin spot exchanges.
Read-only. No account, keys, or orders anywhere in this module."""
import threading
import time
from datetime import datetime, timezone

import requests

KALSHI = "https://external-api.kalshi.com/trade-api/v2"
SERIES = "KXBTC15M"


def parse_ts(s):
    """ISO-8601 (with Z and any number of fraction digits) -> epoch seconds (float)."""
    s = s.replace("Z", "+00:00")
    if "." in s:
        head, rest = s.split(".", 1)
        frac, tz = rest[:-6], rest[-6:]
        s = f"{head}.{(frac + '000000')[:6]}{tz}"
    return datetime.fromisoformat(s).timestamp()


class Http:
    """Keep-alive session with a minimum gap between calls and simple retries."""

    def __init__(self, min_interval=0.15, timeout=10, retries=4):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "trading-research-loop (research; read-only)"
        self.min_interval, self.timeout, self.retries = min_interval, timeout, retries
        self._last = 0.0
        self._lock = threading.Lock()

    def get(self, url, **params):
        for attempt in range(self.retries):
            with self._lock:
                wait = self._last + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
            try:
                r = self.s.get(url, params=params or None, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError):
                if attempt == self.retries - 1:
                    raise
                time.sleep(1.5 * 2 ** attempt)


class Kalshi:
    def __init__(self, http=None):
        self.http = http or Http(min_interval=0.15)

    def markets(self, status, limit=1000, max_pages=None):
        """Yield KXBTC15M markets with this status ('open', 'settled', ...), newest first."""
        cursor, pages = None, 0
        while True:
            params = {"series_ticker": SERIES, "status": status, "limit": limit}
            if cursor:
                params["cursor"] = cursor
            d = self.http.get(f"{KALSHI}/markets", **params)
            yield from d.get("markets", [])
            cursor, pages = d.get("cursor"), pages + 1
            if not cursor or not d.get("markets") or (max_pages and pages >= max_pages):
                return

    def market(self, ticker):
        return self.http.get(f"{KALSHI}/markets/{ticker}")["market"]

    def orderbook(self, ticker, depth=10):
        """Return (yes_bids, no_bids) as lists of (price, size), best first."""
        ob = self.http.get(f"{KALSHI}/markets/{ticker}/orderbook", depth=depth).get("orderbook_fp") or {}
        conv = lambda side: [(float(p), float(q)) for p, q in reversed(ob.get(side) or [])]
        return conv("yes_dollars"), conv("no_dollars")

    def candles(self, ticker, start_ts, end_ts):
        d = self.http.get(f"{KALSHI}/series/{SERIES}/markets/{ticker}/candlesticks",
                          start_ts=int(start_ts), end_ts=int(end_ts), period_interval=1)
        return d.get("candlesticks", [])

    def trades(self, ticker):
        """Every trade in one market, oldest first."""
        out, cursor = [], None
        while True:
            params = {"ticker": ticker, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            d = self.http.get(f"{KALSHI}/markets/trades", **params)
            out += d.get("trades", [])
            cursor = d.get("cursor")
            if not cursor or not d.get("trades"):
                return out[::-1]


def best_quotes(yes_bids, no_bids):
    """Kalshi books hold bids only. YES ask = 1 - best NO bid."""
    yb = yes_bids[0] if yes_bids else (None, 0.0)
    nb = no_bids[0] if no_bids else (None, 0.0)
    ya = (round(1 - nb[0], 4), nb[1]) if nb[0] is not None else (None, 0.0)
    return {"yes_bid": yb[0], "yes_bid_size": yb[1], "yes_ask": ya[0], "yes_ask_size": ya[1]}


class Spot:
    """Bitcoin/USD spot prices from exchanges that feed the CF Benchmarks index."""

    def __init__(self, http=None):
        self.http = http or Http(min_interval=0.0)

    def coinbase(self):
        d = self.http.get("https://api.exchange.coinbase.com/products/BTC-USD/ticker")
        return {"price": float(d["price"]), "bid": float(d["bid"]), "ask": float(d["ask"]),
                "ts_exchange": parse_ts(d["time"])}

    def kraken(self):
        d = self.http.get("https://api.kraken.com/0/public/Ticker", pair="XBTUSD")["result"]
        t = next(iter(d.values()))
        return {"price": float(t["c"][0]), "bid": float(t["b"][0]), "ask": float(t["a"][0]),
                "ts_exchange": None}

    def bitstamp(self):
        d = self.http.get("https://www.bitstamp.net/api/v2/ticker/btcusd/")
        return {"price": float(d["last"]), "bid": float(d["bid"]), "ask": float(d["ask"]),
                "ts_exchange": float(d["timestamp"])}


def kraken_trades(since_ns, http=None):
    """One page (up to 1000) of Kraken BTC/USD trades after since_ns.
    Returns (rows, next_since_ns); rows are (trade_id, ts, price, volume)."""
    http = http or Http(min_interval=1.1)
    d = http.get("https://api.kraken.com/0/public/Trades", pair="XBTUSD", since=str(since_ns), count=1000)
    if d.get("error"):
        raise RuntimeError(f"Kraken error: {d['error']}")
    res = d["result"]
    last = int(res.pop("last"))
    rows = [(int(t[6]) if len(t) > 6 else None, float(t[2]), float(t[0]), float(t[1]))
            for t in next(iter(res.values()))]
    return rows, last
