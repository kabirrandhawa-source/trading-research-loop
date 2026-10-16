"""latest_annual(): newest fiscal year from 10-Ks, not newest filed row (latest() can return a stale year)."""
import pytest

from stocks import fundamentals as f


def _db(tmp_path, rows):
    c = f.connect(tmp_path / "f.db")
    c.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    return c


# One 10-K filed 2021-02-20 holds three fiscal years of OCF; inserted newest-first, like SEC's JSON often is.
TENK = [("AAA", 1, "op_cash_flow", "NetCashProvidedByUsedInOperatingActivities", s, e, v, "2021-02-20", "10-K", 2020, "FY", "k20")
        for s, e, v in [("2020-01-01", "2020-12-31", 30.0), ("2019-01-01", "2019-12-31", 20.0),
                        ("2018-01-01", "2018-12-31", 10.0)]]


def test_stale_year_case_latest_vs_latest_annual(tmp_path):
    c = _db(tmp_path, TENK)
    old = f.latest(c, ["AAA"], "op_cash_flow", "2021-03-01")
    new = f.latest_annual(c, ["AAA"], "op_cash_flow", "2021-03-01")
    assert old.loc["AAA", "end"] != "2020-12-31"          # the bug: ties on filed -> last inserted = 2018
    assert new.loc["AAA", "end"] == "2020-12-31" and new.loc["AAA", "val"] == 30.0


def test_not_visible_before_filing_and_10q_ytd_ignored(tmp_path):
    rows = TENK + [
        # 9-month YTD OCF in a 10-Q, filed later: must not be used as an annual figure
        ("AAA", 1, "op_cash_flow", "NetCashProvidedByUsedInOperatingActivities", "2021-01-01", "2021-09-30", 99.0, "2021-11-01", "10-Q", 2021, "Q3", "q21"),
        # a full-year number repeated in an 8-K: wrong form
        ("AAA", 1, "op_cash_flow", "NetCashProvidedByUsedInOperatingActivities", "2021-01-01", "2021-12-31", 77.0, "2022-01-25", "8-K", 2021, "FY", "e21"),
    ]
    c = _db(tmp_path, rows)
    assert len(f.latest_annual(c, ["AAA"], "op_cash_flow", "2021-02-19")) == 0
    assert f.latest_annual(c, ["AAA"], "op_cash_flow", "2022-01-31").loc["AAA", "val"] == 30.0


def test_quarter_durations_inside_a_10k_are_skipped(tmp_path):
    rows = TENK + [("AAA", 1, "op_cash_flow", "NetCashProvidedByUsedInOperatingActivities", "2020-10-01", "2020-12-31", 8.0, "2021-02-20", "10-K", 2020, "FY", "k20")]
    c = _db(tmp_path, rows)
    assert f.latest_annual(c, ["AAA"], "op_cash_flow", "2021-03-01").loc["AAA", "val"] == 30.0


def test_53_week_year_and_restatement_and_max_age(tmp_path):
    rows = [
        ("BBB", 2, "op_cash_flow", "NetCashProvidedByUsedInOperatingActivities", "2019-12-29", "2021-01-02", 5.0, "2021-03-01", "10-K", 2020, "FY", "b20"),
        # next 10-K repeats FY2020 with a restated value and adds FY2021
        ("BBB", 2, "op_cash_flow", "NetCashProvidedByUsedInOperatingActivities", "2019-12-29", "2021-01-02", 6.0, "2022-03-01", "10-K", 2021, "FY", "b21"),
    ]
    c = _db(tmp_path, rows)
    got = f.latest_annual(c, ["BBB"], "op_cash_flow", "2022-06-01")
    assert got.loc["BBB", "val"] == 6.0 and got.loc["BBB", "accn"] == "b21"     # 371-day year accepted, restated wins
    assert f.latest_annual(c, ["BBB"], "op_cash_flow", "2021-06-01").loc["BBB", "val"] == 5.0
    assert len(f.latest_annual(c, ["BBB"], "op_cash_flow", "2022-02-01", max_age_months=10)) == 0


def test_instant_metric_takes_newest_year_end(tmp_path):
    rows = [("AAA", 1, "assets", "Assets", None, e, v, "2021-02-20", "10-K", 2020, "FY", "k20")
            for e, v in [("2020-12-31", 300.0), ("2019-12-31", 200.0)]]
    c = _db(tmp_path, rows)
    got = f.latest_annual(c, ["AAA", "ZZZ"], "assets", "2021-03-01")
    assert list(got.index) == ["AAA"] and got.loc["AAA", "val"] == pytest.approx(300.0)


def test_latest_behavior_unchanged_for_quarters(tmp_path):
    rows = [("AAA", 1, "eps_diluted", "EarningsPerShareDiluted", "2020-01-01", "2020-03-31", 1.0, "2020-05-01", "10-Q", 2020, "Q1", "a1"),
            ("AAA", 1, "eps_diluted", "EarningsPerShareDiluted", "2020-04-01", "2020-06-30", 2.0, "2020-08-01", "10-Q", 2020, "Q2", "a2")]
    c = _db(tmp_path, rows)
    assert f.latest(c, ["AAA"], "eps_diluted", "2020-08-01").loc["AAA", "val"] == 2.0
