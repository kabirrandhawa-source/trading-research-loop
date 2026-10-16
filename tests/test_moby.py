import pytest

from sleeve import picks as moby

CFG = {"budget": 10000, "universe": ["CDE", "AAA", "BBB", "CCC", "DDD", "EEE"], "long_only": True,
       "max_positions": 5, "max_position_pct_of_sleeve": 20, "min_trade_dollars": 200, "benchmark": "SPY"}


def pick(sym, day, **kw):
    return {"symbol": sym, "date": day, "target": None, "note": None, **kw}


def test_active_rules():
    picks = [pick("CDE", "2026-10-15"),
             pick("AAA", "2026-01-01"),                               # older than 26 weeks
             pick("BBB", "2026-10-01", target=20.0),                  # target reached
             pick("CCC", "2026-10-02", closed="2026-10-10"),          # Moby said sell
             pick("DDD", "2026-10-20")]                               # not picked yet on this date
    act = moby.active(picks, "2026-10-15", {"BBB": 21.0})
    assert [k["symbol"] for k in act] == ["CDE"]


def test_newest_five_only_and_twenty_percent_each():
    picks = [pick(s, f"2026-10-0{i + 1}") for i, s in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "CDE"])]
    d = moby.decision_for("2026-10-15", picks, {})
    assert set(d["targets"]) == {"BBB", "CCC", "DDD", "EEE", "CDE"} and set(d["targets"].values()) == {20}


def test_one_decision_per_day_and_rules_validated(tmp_path):
    picks = [pick("CDE", "2026-10-15")]
    first = moby.write_today_decision("2026-10-15", {"CDE": 15.41}, CFG, tmp_path, picks)
    assert first and first.name == "2026-10-15.json"
    assert moby.write_today_decision("2026-10-15", {"CDE": 15.41}, CFG, tmp_path, picks) is None


def test_unknown_symbol_is_rejected(tmp_path):
    from sleeve import decide
    with pytest.raises(decide.Invalid, match="not in the sleeve's universe"):
        moby.write_today_decision("2026-10-15", {}, {**CFG, "universe": []}, tmp_path, [pick("ZZZ", "2026-10-15")])
