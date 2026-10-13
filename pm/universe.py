"""Which Kalshi 15-minute markets to track, and the free price sources for each.

settle_window_s: how the market settles.
  60 -> average of the index over the last 60 seconds (CF Benchmarks crypto indexes)
   0 -> a single price at the close (Pyth 1-minute candle or Pyth rate)
every_s: how often to save the order book (keeps us inside Kalshi's free read limits).

Exchange symbols: Coinbase product, Kraken pair, Binance.US symbol, Bitstamp pair.
Pyth symbols resolve to feed IDs in PYTH_IDS (from hermes.pyth.network/v2/price_feeds).
Binance.com is not used: it blocks US users (HTTP 451). Binance.US is used instead.
"""

PYTH_IDS = {
    "Crypto.BTC/USD": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "Crypto.ETH/USD": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "Crypto.SOL/USD": "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "Crypto.XRP/USD": "ec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8",
    "Crypto.DOGE/USD": "dcef50dd0a4cd2dcc17e45df1676dcb336a11a61c69df7a0299b0150c672d25c",
    "Metal.XAU/USD": "765d2ba906dbc32ca17cc11f5310a89e9ee1f6420508c63861f2f8ba4ee34bb2",
    "Metal.XAG/USD": "f2fb02c32b055c805e7238d628e5e9dadef274376114eb1f012337cabe93871e",
    "Commodities.Index.PYTHOIL/USD": "67784f72e95ac01337edb7d7bd5bbd1c03669101b7068a620df228ed4e52ef14",
    "FX.EUR/USD": "a995d00bb36a63cef7fd2c287dc105fc8f3d93779f062f09551b0af3e81ec30b",
    "FX.USD/JPY": "ef2c98c804ba503c6a707e38be4dfbb16683775f195b091252bf24693042fd52",
    "FX.GBP/USD": "84c2dde9633d93d1bcad84e7dc41c9d56578b7ec52fabedc1f335d673df0a7c1",
}

SERIES = {
    # Crypto: settle on the 60-second average of a CF Benchmarks real-time index.
    "KXBTC15M": {"asset": "BTC", "every_s": 1, "settle_window_s": 60, "pyth": "Crypto.BTC/USD",
                 "coinbase": "BTC-USD", "kraken": "XBTUSD", "binanceus": "BTCUSDT", "bitstamp": "btcusd"},
    "KXETH15M": {"asset": "ETH", "every_s": 2, "settle_window_s": 60, "pyth": "Crypto.ETH/USD",
                 "coinbase": "ETH-USD", "kraken": "ETHUSD", "binanceus": "ETHUSDT"},
    "KXSOL15M": {"asset": "SOL", "every_s": 5, "settle_window_s": 60, "pyth": "Crypto.SOL/USD",
                 "coinbase": "SOL-USD", "kraken": "SOLUSD", "binanceus": "SOLUSDT"},
    "KXXRP15M": {"asset": "XRP", "every_s": 5, "settle_window_s": 60, "pyth": "Crypto.XRP/USD",
                 "coinbase": "XRP-USD", "kraken": "XRPUSD", "binanceus": "XRPUSDT"},
    "KXDOGE15M": {"asset": "DOGE", "every_s": 5, "settle_window_s": 60, "pyth": "Crypto.DOGE/USD",
                  "coinbase": "DOGE-USD", "kraken": "XDGUSD", "binanceus": "DOGEUSDT"},
    # Commodities and currencies: settle on a single Pyth price at the close.
    "KXGOLD15M": {"asset": "GOLD", "every_s": 5, "settle_window_s": 0, "pyth": "Metal.XAU/USD"},
    "KXSILVER15M": {"asset": "SILVER", "every_s": 5, "settle_window_s": 0, "pyth": "Metal.XAG/USD"},
    "KXWTI15M": {"asset": "WTI", "every_s": 5, "settle_window_s": 0, "pyth": "Commodities.Index.PYTHOIL/USD"},
    "KXEURUSD15M": {"asset": "EURUSD", "every_s": 5, "settle_window_s": 0, "pyth": "FX.EUR/USD"},
    "KXUSDJPY15M": {"asset": "USDJPY", "every_s": 5, "settle_window_s": 0, "pyth": "FX.USD/JPY"},
    "KXGBPUSD15M": {"asset": "GBPUSD", "every_s": 5, "settle_window_s": 0, "pyth": "FX.GBP/USD"},
    # Stock indexes: order books only for now. Settlement source still to be confirmed from the
    # rules when these markets are open (US market hours).
    "KXINX15M": {"asset": "SPX", "every_s": 5, "settle_window_s": None},
    "KXNDQ15M": {"asset": "NDX", "every_s": 5, "settle_window_s": None},
    "KXDJIA15M": {"asset": "DJI", "every_s": 5, "settle_window_s": None},
}


def due(series_cfg, tick, offset=0):
    """True when this series should be sampled on this 1-second tick. Different offsets spread
    series with the same interval across ticks instead of firing them all at once."""
    every = max(1, int(series_cfg["every_s"]))
    return (tick + offset) % every == 0


def kalshi_reads_per_second():
    return sum(1 / c["every_s"] for c in SERIES.values())
