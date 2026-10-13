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
    ts REAL, source TEXT, price REAL, bid REAL, ask REAL, ts_exchange REAL, fetch_ms REAL);
CREATE INDEX IF NOT EXISTS ticks_ts ON spot_ticks (source, ts);
CREATE TABLE IF NOT EXISTS progress (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(name, data_dir=None):
    d = Path(data_dir or DATA)
    d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(d / f"{name}.db", timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
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
