import base64

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

from pm import kalshi_auth, store, stream


def test_book_snapshot_delta_and_top():
    b = stream.Book()
    b.snapshot({"yes_dollars_fp": [["0.0800", "300.00"], ["0.4200", "10.00"]],
                "no_dollars_fp": [["0.5400", "20.00"], ["0.5600", "146.00"]]})
    assert b.top() == (0.42, 10.0, 0.44, 146.0)              # YES ask = 1 - best NO bid
    b.delta({"side": "yes", "price_dollars": "0.4300", "delta_fp": "5.00"})
    b.delta({"side": "no", "price_dollars": "0.5600", "delta_fp": "-146.00"})   # level removed
    assert b.top() == (0.43, 5.0, 0.46, 20.0)
    assert b.levels(1) == {"yes": [(0.43, 5.0)], "no": [(0.54, 20.0)]}


def make_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    s = stream.Stream.__new__(stream.Stream)          # skip key loading and network
    s.books, s.last_tob, s.tickers, s.sid_seq, s.sid_channel = {}, {}, {"M1"}, {}, {}
    s.month, s.conn, s.raw_seen, s.bad_msgs, s.disk_ok, s.gaps = None, None, {}, 0, True, {}
    return s


def test_sequence_gap_raises(tmp_path, monkeypatch):
    s = make_stream(tmp_path, monkeypatch)
    snap = {"type": "orderbook_snapshot", "sid": 1, "seq": 1,
            "msg": {"market_ticker": "M1", "yes_dollars_fp": [["0.40", "1"]], "no_dollars_fp": [["0.50", "1"]]}}
    s.handle(snap, 1.0)
    s.handle({"type": "orderbook_delta", "sid": 1, "seq": 2,
              "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.41", "delta_fp": "2"}}, 2.0)
    with pytest.raises(stream.SeqGap):
        s.handle({"type": "orderbook_delta", "sid": 1, "seq": 4,
                  "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.42", "delta_fp": "2"}}, 3.0)


def test_tob_written_only_on_change_and_trades_indexes_saved(tmp_path, monkeypatch):
    s = make_stream(tmp_path, monkeypatch)
    s.handle({"type": "orderbook_snapshot", "sid": 1, "seq": 1,
              "msg": {"market_ticker": "M1", "yes_dollars_fp": [["0.40", "1"]], "no_dollars_fp": [["0.50", "1"]]}}, 1.0)
    s.handle({"type": "orderbook_delta", "sid": 1, "seq": 2,     # deeper level: top unchanged
              "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.30", "delta_fp": "5"}}, 2.0)
    s.handle({"type": "trade", "sid": 2, "seq": 1,
              "msg": {"market_ticker": "M1", "yes_price_dollars": "0.4000", "count_fp": "3.00", "taker_side": "yes",
                      "trade_id": "t1", "ts_ms": 1000}}, 3.0)
    s.handle({"type": "cfbenchmarks_value_5hz", "sid": 3, "seq": 1,
              "msg": {"index_id": "BRTI", "value_usd": "68000.12", "source_ts_ms": 5, "received_at": 6}}, 4.0)
    s.handle({"type": "something_new", "msg": {"x": 1}}, 5.0)
    c = s.db()
    assert c.execute("select count(*) from ws_tob").fetchone()[0] == 1
    assert c.execute("select yes_price, count from ws_trades").fetchone() == (0.4, 3.0)
    assert c.execute("select channel, index_id, value from index_values").fetchone() == ("5hz", "BRTI", 68000.12)
    assert c.execute("select type from ws_raw").fetchone() == ("something_new",)


@pytest.mark.parametrize("kind", ["rsa", "ed25519"])
def test_signatures_verify(kind):
    key = rsa.generate_private_key(65537, 2048) if kind == "rsa" else ed25519.Ed25519PrivateKey.generate()
    h = kalshi_auth.headers("kid", key, "get", "/trade-api/ws/v2?x=1")
    msg = (h["KALSHI-ACCESS-TIMESTAMP"] + "GET" + "/trade-api/ws/v2").encode()   # query string excluded
    sig = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    if kind == "rsa":
        key.public_key().verify(sig, msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                      salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    else:
        key.public_key().verify(sig, msg)
    assert h["KALSHI-ACCESS-KEY"] == "kid"


def test_missing_key_is_reported_plainly(tmp_path, monkeypatch):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "")
    with pytest.raises(kalshi_auth.MissingKey, match="KALSHI_API_KEY_ID"):
        kalshi_auth.load()
    monkeypatch.setenv("KALSHI_API_KEY_ID", "kid")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_path / "nope.pem"))
    with pytest.raises(kalshi_auth.MissingKey, match="not found"):
        kalshi_auth.load()
    bad = tmp_path / "bad.pem"; bad.write_text("not a key")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(bad))
    with pytest.raises(kalshi_auth.MissingKey, match="Could not read") as e:
        kalshi_auth.load()
    assert "not a key" not in str(e.value)               # never echo key-file contents


def test_index_value_from_both_channel_formats():
    five = {"index_id": "BRTI", "value_usd": "83096.36000000", "source_ts_ms": 1}
    sixty = {"index_id": "BRTI", "received_at": 2,
             "data": "{\"type\":\"value\",\"time\":1791911689000,\"id\":\"BRTI\",\"value\":\"83096.20\"}",
             "last_60s_windowed_average_15min": {"value": "83096.10000000"}}
    assert stream.index_value(five) == (83096.36, 1)
    assert stream.index_value(sixty) == (83096.2, 1791911689000)


def test_sixty_second_channel_saves_value_and_average(tmp_path, monkeypatch):
    s = make_stream(tmp_path, monkeypatch)
    s.handle({"type": "cfbenchmarks_value", "sid": 4, "seq": 1, "msg": {
        "index_id": "BRTI", "received_at": 2,
        "data": "{\"type\":\"value\",\"time\":1000,\"id\":\"BRTI\",\"value\":\"83096.20\"}",
        "avg_60s_data": {"value": "83096.15000000"},
        "last_60s_windowed_average_15min": {"value": "83096.10000000"}}}, 1.0)
    s.handle({"type": "cfbenchmarks_value", "sid": 4, "seq": 2, "msg": {          # no window average yet
        "index_id": "BRTI", "data": "{\"time\":2000,\"value\":\"83097.00\"}",
        "avg_60s_data": {"value": "83096.50000000"}}}, 2.0)
    rows = s.db().execute("select value, source_ts_ms, avg_60s, settle_avg from index_values order by ts").fetchall()
    assert rows == [(83096.2, 1000, 83096.15, 83096.1), (83097.0, 2000, 83096.5, None)]


def test_size_only_changes_are_thinned_but_price_changes_always_saved(tmp_path, monkeypatch):
    s = make_stream(tmp_path, monkeypatch)
    snap = {"type": "orderbook_snapshot", "sid": 1, "seq": 1,
            "msg": {"market_ticker": "M1", "yes_dollars_fp": [["0.40", "10"]], "no_dollars_fp": [["0.50", "10"]]}}
    s.handle(snap, 100.0)
    d = lambda seq, side, price, delta: {"type": "orderbook_delta", "sid": 1, "seq": seq,
        "msg": {"market_ticker": "M1", "side": side, "price_dollars": price, "delta_fp": delta}}
    s.handle(d(2, "yes", "0.40", "1"), 100.05)    # size only, 50 ms later: skipped
    s.handle(d(3, "yes", "0.40", "1"), 100.10)    # size only: skipped
    s.handle(d(4, "yes", "0.41", "1"), 100.12)    # new best price: saved
    s.handle(d(5, "yes", "0.41", "1"), 100.50)    # size only, 380 ms later: saved
    rows = s.db().execute("select ts, yes_bid, yes_bid_size from ws_tob order by ts").fetchall()
    assert rows == [(100.0, 0.4, 10.0), (100.12, 0.41, 1.0), (100.5, 0.41, 2.0)]


def test_low_disk_pauses_writes(tmp_path, monkeypatch):
    s = make_stream(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(stream.alerts, "send", lambda *a, **k: sent.append(a[0]))
    monkeypatch.setattr(stream.shutil, "disk_usage", lambda p: type("U", (), {"free": 5e9})())
    s.check_disk()
    s.handle({"type": "trade", "sid": 2, "seq": 1, "msg": {"market_ticker": "M1", "yes_price_dollars": "0.4",
              "count_fp": "1", "trade_id": "t"}}, 1.0)
    assert not s.disk_ok and sent == ["Kalshi stream paused: disk low"]
    assert s.db().execute("select count(*) from ws_trades").fetchone()[0] == 0


def test_archive_only_finished_quiet_files_and_round_trips(tmp_path):
    import os, sqlite3
    from pm import archive
    now = 1791900000.0                                   # 2026-10-13 (UTC)
    for name in ("stream-2026-10-12.db", "stream-2026-10-13.db", "live-2026-09.db", "history.db"):
        c = sqlite3.connect(tmp_path / name); c.execute("create table t (x)"); c.execute("insert into t values (42)")
        c.commit(); c.close()
        os.utime(tmp_path / name, (now - 7200, now - 7200))
    picked = sorted(p.name for p in tmp_path.glob("*.db") if archive.finished(p, now))
    assert picked == ["live-2026-09.db", "stream-2026-10-12.db"]    # today and non-recorder files skipped
    raw, xz = archive.compress(tmp_path / "stream-2026-10-12.db")
    assert not (tmp_path / "stream-2026-10-12.db").exists() and (tmp_path / "stream-2026-10-12.db.xz").exists()
    back = archive.restore(tmp_path / "stream-2026-10-12.db.xz", tmp_path / "out" if (tmp_path / "out").mkdir() is None else None)
    assert sqlite3.connect(back).execute("select x from t").fetchone() == (42,)


def test_trade_gap_is_counted_not_fatal(tmp_path, monkeypatch):
    s = make_stream(tmp_path, monkeypatch)
    tr = lambda seq, tid: {"type": "trade", "sid": 2, "seq": seq, "msg": {"market_ticker": "M1",
                           "yes_price_dollars": "0.4", "count_fp": "1", "trade_id": tid}}
    s.handle(tr(290, "a"), 1.0)
    s.handle(tr(292, "b"), 2.0)                      # one trade missed: no exception
    assert s.gaps == {"trade": 1}
    assert s.db().execute("select count(*) from ws_trades").fetchone()[0] == 2
