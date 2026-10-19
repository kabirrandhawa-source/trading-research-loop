from datetime import datetime, timezone

from crypto import forward

NOW = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)


def fake_fetch(url, **params):
    if "futures.kraken.com" in url:
        return {"tickers": [
            {"symbol": "PF_XBTUSD", "markPrice": 80000.0, "indexPrice": 79990.0, "bid": 79999, "ask": 80001,
             "fundingRate": 2.0, "fundingRatePrediction": 1.9, "lastTime": "2026-10-19T13:59:59Z"},
            {"symbol": "PF_ETHUSD", "markPrice": 2400.0, "indexPrice": 2399.0, "bid": 2399.9, "ask": 2400.1,
             "fundingRate": 0.05, "fundingRatePrediction": 0.04, "lastTime": "2026-10-19T13:59:58Z"}]}
    if "international.coinbase.com" in url:
        raise RuntimeError("feed down")
    coin = url.split("/products/")[1].split("-")[0]
    return {"price": "100", "bid": "99.5", "ask": "100.5"} if coin != "BTC" else {"price": "80005", "bid": "80004", "ask": "80006"}


def test_record_stores_kraken_with_relative_funding_and_survives_a_failed_source(tmp_path):
    db = tmp_path / "f.db"
    assert forward.record(db, fetch=fake_fetch, now=NOW) == 2          # BTC + ETH from Kraken; Intl failed
    c = forward.connect(db)
    btc = c.execute("SELECT mark, funding_raw, funding_rel_hourly, spot FROM snapshots "
                    "WHERE source='kraken' AND coin='BTC'").fetchone()
    assert btc[0] == 80000.0 and btc[1] == 2.0 and abs(btc[2] - 2.0 / 80000.0) < 1e-12 and btc[3] == 80005.0
    assert c.execute("SELECT source FROM errors").fetchall() == [("coinbase_intl",)]


def test_same_hour_twice_does_not_duplicate(tmp_path):
    db = tmp_path / "f.db"
    forward.record(db, fetch=fake_fetch, now=NOW)
    forward.record(db, fetch=fake_fetch, now=NOW)
    assert forward.status(db)["rows"] == 2
