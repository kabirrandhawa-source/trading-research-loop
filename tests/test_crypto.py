from crypto import data


def test_coinbase_daily_pages_backwards_and_dedupes(monkeypatch):
    calls = []
    def fake_get(url, **p):
        calls.append(p["start"][:10])
        if len(calls) > 2:
            return []
        t = 1_700_000_000 - 86400 * 300 * (len(calls) - 1)
        return [[t, 1, 3, 2, 2.5, 10], [t - 86400, 1, 3, 2, 2.4, 11]]
    monkeypatch.setattr(data, "get", fake_get)
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    rows = data.coinbase_daily("BTC", since="2022-01-01")
    assert [r[1] for r in rows] == sorted(r[1] for r in rows) and len(rows) == len({r[1] for r in rows})
    assert rows[0][0] == "BTC" and rows[0][5] in (2.4, 2.5)          # close column, not open/high


def test_funding_stops_at_known_timestamp(monkeypatch):
    pages = [[{"event_time": "2026-10-02T00:00:00Z", "funding_rate": "0.0001"},
              {"event_time": "2026-10-01T23:00:00Z", "funding_rate": "-0.0002"}],
             [{"event_time": "2026-10-01T22:00:00Z", "funding_rate": "0.0003"}]]
    monkeypatch.setattr(data, "get", lambda url, **p: {"results": pages[p["result_offset"] // 2] if p["result_offset"] < 4 else []})
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    out = data.coinbase_intl_funding("BTC", known="2026-10-01T23:00:00Z")
    assert out == [("coinbase_intl", "BTC", "2026-10-02T00:00:00Z", 0.0001), ("coinbase_intl", "BTC", "2026-10-01T23:00:00Z", -0.0002)]
