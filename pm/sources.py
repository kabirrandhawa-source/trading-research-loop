"""Public market-data clients: Kalshi (prediction market) and Bitcoin spot exchanges.
Read-only. No account, keys, or orders anywhere in this module."""
import os
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

    def markets(self, status, limit=1000, max_pages=None, series=SERIES):
        """Yield a series' markets with this status ('open', 'settled', ...), newest first."""
        cursor, pages = None, 0
        while True:
            params = {"series_ticker": series, "status": status, "limit": limit}
            if cursor:
                params["cursor"] = cursor
            d = self.http.get(f"{KALSHI}/markets", **params)
            yield from d.get("markets", [])
            cursor, pages = d.get("cursor"), pages + 1
            if not cursor or not d.get("markets") or (max_pages and pages >= max_pages):
                return

    def markets_for(self, series, status, limit=5):
        """First page of a series' markets with this status."""
        return list(self.markets(status, limit=limit, max_pages=1, series=series))

    def market(self, ticker):
        return self.http.get(f"{KALSHI}/markets/{ticker}")["market"]

    def orderbook(self, ticker, depth=10):
        """Return (yes_bids, no_bids) as lists of (price, size), best first."""
        ob = self.http.get(f"{KALSHI}/markets/{ticker}/orderbook", depth=depth).get("orderbook_fp") or {}
        conv = lambda side: [(float(p), float(q)) for p, q in reversed(ob.get(side) or [])]
        return conv("yes_dollars"), conv("no_dollars")

    def candles(self, ticker, start_ts, end_ts):
        d = self.http.get(f"{KALSHI}/series/{ticker.split('-')[0]}/markets/{ticker}/candlesticks",
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


# ---------- batched multi-asset quotes (used by the recorder) ----------

def coinbase_quote(http, product):
    d = http.get(f"https://api.exchange.coinbase.com/products/{product}/ticker")
    return {"price": float(d["price"]), "bid": float(d["bid"]), "ask": float(d["ask"]),
            "ts_exchange": parse_ts(d["time"])}


def kraken_quotes(http, pairs):
    """{requested_pair: quote}. Kraken renames some pairs (XBTUSD -> XXBTZUSD), so match by order
    of the 'altname' lookup instead of trusting the response keys."""
    d = http.get("https://api.kraken.com/0/public/Ticker", pair=",".join(pairs))
    if d.get("error"):
        raise RuntimeError(f"Kraken error: {d['error']}")
    res = d["result"]
    norm = lambda s: s.replace("XBT", "BTC").replace("XDG", "DOGE").replace("X", "").replace("Z", "")
    out = {}
    for p in pairs:
        key = next((k for k in res if k == p or norm(k) == norm(p)), None)
        if key:
            t = res[key]
            out[p] = {"price": float(t["c"][0]), "bid": float(t["b"][0]), "ask": float(t["a"][0]),
                      "ts_exchange": None}
    return out


def binanceus_quotes(http, symbols):
    """Best bid/ask from Binance.US (Binance.com blocks US users)."""
    import json as _json
    d = http.get("https://api.binance.us/api/v3/ticker/bookTicker", symbols=_json.dumps(symbols, separators=(",", ":")))
    return {x["symbol"]: {"price": (float(x["bidPrice"]) + float(x["askPrice"])) / 2, "bid": float(x["bidPrice"]),
                          "ask": float(x["askPrice"]), "ts_exchange": None} for x in d}


def bitstamp_quote(http, pair):
    d = http.get(f"https://www.bitstamp.net/api/v2/ticker/{pair}/")
    return {"price": float(d["last"]), "bid": float(d["bid"]), "ask": float(d["ask"]),
            "ts_exchange": float(d["timestamp"])}


def pyth_quotes(http, api_key, ids):
    """{feed_id: quote} from Pyth Hermes. Requires a Pyth API key since the 2026 Core upgrade (free
    trial, then paid; sign up at pythdata.app). Sent as 'Authorization: Bearer <key>'."""
    params = [("ids[]", i) for i in ids] + [("parsed", "true")]
    base = os.getenv("PYTH_HERMES_URL", "https://pyth.dourolabs.app/hermes").rstrip("/")
    r = http.s.get(f"{base}/v2/updates/price/latest", params=params,
                   headers={"Authorization": f"Bearer {api_key}"}, timeout=http.timeout)
    r.raise_for_status()
    out = {}
    for p in r.json().get("parsed", []):
        pr = p["price"]
        scale = 10 ** int(pr["expo"])
        price, conf = int(pr["price"]) * scale, int(pr["conf"]) * scale
        out[p["id"]] = {"price": price, "bid": price - conf, "ask": price + conf,
                        "ts_exchange": float(pr["publish_time"])}
    return out
