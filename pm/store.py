"""SQLite storage for prediction-market research data (data/pm/, gitignored)."""
import json
import sqlite3
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "pm"

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    ticker TEXT PRIMARY KEY, open_ts REAL, close_ts REAL, floor_strike REAL,
    expiration_value REAL, result TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS candles (
    ticker TEXT, ts REAL, yes_bid REAL, yes_ask REAL, price REAL, volume REAL,
    PRIMARY KEY (ticker, ts));
CREATE TABLE IF NOT EXISTS kalshi_trades (
    trade_id TEXT PRIMARY KEY, ticker TEXT, ts REAL, yes_price REAL, count REAL, taker_side TEXT);
CREATE INDEX IF NOT EXISTS kt_ticker_ts ON kalshi_trades (ticker, ts);
CREATE TABLE IF NOT EXISTS spot_trades (
    source TEXT, trade_id INTEGER, ts REAL, price REAL, volume REAL,
    PRIMARY KEY (source, trade_id));
CREATE INDEX IF NOT EXISTS st_ts ON spot_trades (source, ts);
CREATE TABLE IF NOT EXISTS book (
    ts REAL, ticker TEXT, yes_bid REAL, yes_bid_size REAL, yes_ask REAL, yes_ask_size REAL,
    levels TEXT, fetch_ms REAL);
CREATE INDEX IF NOT EXISTS book_ts ON book (ticker, ts);
CREATE TABLE IF NOT EXISTS spot_ticks (
    ts REAL, source TEXT, price REAL, bid REAL, ask REAL, ts_exchange REAL, fetch_ms REAL,
    symbol TEXT);                                    -- asset, e.g. BTC; NULL in early rows = BTC
CREATE INDEX IF NOT EXISTS ticks_ts ON spot_ticks (source, ts);
CREATE TABLE IF NOT EXISTS progress (key TEXT PRIMARY KEY, value TEXT);
-- Live stream (pm/stream.py, authenticated Kalshi websocket)
CREATE TABLE IF NOT EXISTS ws_tob (                 -- every change to the best bid/ask
    ts REAL, ticker TEXT, yes_bid REAL, yes_bid_size REAL, yes_ask REAL, yes_ask_size REAL, seq INTEGER);
CREATE INDEX IF NOT EXISTS ws_tob_ts ON ws_tob (ticker, ts);
CREATE TABLE IF NOT EXISTS ws_book (ts REAL, ticker TEXT, levels TEXT);   -- top 10 each side, once a second
CREATE INDEX IF NOT EXISTS ws_book_ts ON ws_book (ticker, ts);
CREATE TABLE IF NOT EXISTS ws_trades (            -- no unique index on trade_id: it doubled the size
    ts REAL, ts_ms INTEGER, ticker TEXT, yes_price REAL, count REAL, taker_side TEXT, trade_id TEXT);
CREATE INDEX IF NOT EXISTS ws_trades_ts ON ws_trades (ticker, ts_ms);
CREATE TABLE IF NOT EXISTS index_values (           -- settlement indexes streamed by Kalshi
    ts REAL, channel TEXT, index_id TEXT, value REAL, source_ts_ms INTEGER, received_at_ms INTEGER,
    avg_60s REAL,                                   -- rolling 60-second average (avg_60s_data)
    settle_avg REAL);                               -- current window's settlement average, when sent
CREATE INDEX IF NOT EXISTS index_values_ts ON index_values (index_id, ts);
CREATE TABLE IF NOT EXISTS ws_raw (ts REAL, type TEXT, json TEXT);       -- first messages of unknown types
"""


def day_name(prefix, ts=None):
    """Daily file name (UTC), e.g. stream-2026-10-13. Finished days are compressed by pm/archive.py."""
    import time
    return f"{prefix}-{time.strftime('%Y-%m-%d', time.gmtime(ts))}"


def connect(name, data_dir=None):
    d = Path(data_dir or DATA)
    d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(d / f"{name}.db", timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(spot_ticks)")}
    if "symbol" not in cols:                         # databases created before multi-asset support
        conn.execute("ALTER TABLE spot_ticks ADD COLUMN symbol TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS ticks_sym_ts ON spot_ticks (symbol, ts)")
    if "settle_avg" not in {r[1] for r in conn.execute("PRAGMA table_info(index_values)")}:
        conn.execute("ALTER TABLE index_values ADD COLUMN settle_avg REAL")
    return conn


def upsert_market(conn, m, parse_ts):
    conn.execute(
        "INSERT OR REPLACE INTO markets VALUES (?, ?, ?, ?, ?, ?, ?)",
        (m["ticker"], parse_ts(m["open_time"]), parse_ts(m["close_time"]),
         float(m["floor_strike"]) if m.get("floor_strike") is not None else None,
         float(m["expiration_value"]) if m.get("expiration_value") not in (None, "") else None,
         m.get("result") or None, json.dumps(m)))


def get_progress(conn, key, default=None):
    row = conn.execute("SELECT value FROM progress WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_progress(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO progress VALUES (?, ?)", (key, str(value)))
    conn.commit()
