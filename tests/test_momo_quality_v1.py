import numpy as np
import pandas as pd
import pytest

from strategies import momo_quality_v1 as S
from stocks import momo_quality as R


def test_strategy_metadata():
    assert S.MomoQualityV1.HYPOTHESIS_ID == 15 and S.MomoQualityV1.VERSION == "v1"
    with pytest.raises(NotImplementedError):
        S.MomoQualityV1().entry(None)


def test_momentum_skips_latest_month():
    idx = pd.to_datetime(["2016-01-04"] + [f"2016-{m:02d}-28" for m in range(1, 13)])
    a = pd.DataFrame({"A": [100.0] + [100 + 10 * i for i in range(1, 12)] + [10.0],   # crash in the last month
                      "B": [np.nan] + [100.0] * 12}, index=idx)
    mom = S.momentum_12_1(a, 12)
    assert mom["A"] == pytest.approx(210 / 100 - 1)      # close[11] / close[0]; the final month is skipped
    assert np.isnan(mom["B"])                              # no t-12 anchor -> excluded
    with pytest.raises(ValueError):
        S.momentum_12_1(a, 11)


def test_select_top_decile_then_top_half_of_members_by_profitability():
    mom = pd.Series({f"T{i:02d}": float(i) for i in range(20)} | {"NAN": np.nan})
    # members' profitability: T19 high, T18 low, T17 no coverage; median of all covered members = 0.5
    prof = pd.Series({f"T{i:02d}": 0.5 for i in range(17)} | {"T19": 0.9, "T18": 0.1})
    top, screened, uncovered = S.select(mom, prof)
    assert top == ["T19", "T18"]                          # round(20 / 10) = 2, NaN momentum excluded
    assert screened == ["T19"] and uncovered == []
    prof2 = prof.drop("T18")
    _, screened2, unc2 = S.select(mom, prof2)
    assert screened2 == ["T19"] and unc2 == ["T18"]        # uncovered names are dropped, not kept


def test_hold_sells_index_exit_at_last_close_and_drifts_weights():
    days = pd.to_datetime(["2020-01-31", "2020-02-10", "2020-02-20", "2020-02-28"])
    close = pd.DataFrame({"A": [100, 105, 110, 120.0], "B": [50, 40, np.nan, np.nan]}, index=days)
    w = S.equal_weights(["A", "B"])
    h = S.hold(close, days[0], days[-1], w)
    assert h["exited"] == ["B"]
    assert h["rets"]["B"] == pytest.approx(-0.2) and h["rets"]["A"] == pytest.approx(0.2)
    assert h["gross"] == pytest.approx(0.0)
    assert h["exit_value"] == pytest.approx(0.4)
    assert h["end_weights"]["A"] == pytest.approx(0.6) and "B" not in h["end_weights"]


def test_traded_weight_and_costs():
    target = pd.Series({"A": 0.5, "C": 0.5})
    drifted = pd.Series({"A": 0.6})               # 0.4 is cash from an exit
    assert S.traded_weight(target, drifted) == pytest.approx(0.1 + 0.5)


def test_sector_neutral_and_tech_cap_weights():
    sec = {"A": "XLK", "B": "XLK", "C": "XLK", "D": "XLE"}
    universe = ["XLK"] * 2 + ["XLE"] * 2 + ["XLV"] * 4
    w = S.sector_neutral_weights(["A", "B", "C", "D"], sec, universe)
    assert w.sum() == pytest.approx(1.0)
    assert w[["A", "B", "C"]].sum() == pytest.approx(0.5) and w["D"] == pytest.approx(0.5)
    tc = S.tech_capped_weights(["A", "B", "C", "D"], sec, cap=0.25)
    assert tc[["A", "B", "C"]].sum() == pytest.approx(0.25) and tc["D"] == pytest.approx(0.75)


def test_assign_sectors_by_residual_correlation():
    rng = np.random.default_rng(1)
    n = 200
    spy = pd.Series(rng.normal(0, 0.01, n))
    etf = pd.DataFrame({"XLK": spy + rng.normal(0, 0.01, n), "XLE": spy + rng.normal(0, 0.01, n)})
    stocks = pd.DataFrame({"TECH": etf["XLK"] + rng.normal(0, 0.005, n),
                           "OIL": etf["XLE"] + rng.normal(0, 0.005, n),
                           "NOISE": spy + rng.normal(0, 0.02, n),
                           "SHORT": pd.Series([np.nan] * 150 + list(rng.normal(0, 0.01, 50)))})
    sec = S.assign_sectors(stocks, etf, spy, min_days=126, min_corr=0.3)
    assert sec["TECH"] == "XLK" and sec["OIL"] == "XLE" and sec["SHORT"] == "other"


def test_capm_recovers_alpha_and_beta():
    rng = np.random.default_rng(2)
    mkt = rng.normal(0.01, 0.04, 240)
    port = 0.002 + 1.2 * mkt + rng.normal(0, 0.001, 240)
    c = S.capm(port, mkt)
    assert c["beta"] == pytest.approx(1.2, abs=0.01) and c["alpha_monthly"] == pytest.approx(0.002, abs=0.0005)
    assert c["alpha_t"] > 10


def test_max_drawdown_and_t_stat():
    assert S.max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(-0.5)
    assert S.t_stat([0.01, 0.01, 0.01]) == 0.0


def test_formation_calendar_ends_before_sealed():
    days = pd.bdate_range("2016-01-04", "2024-01-29")
    anchors, forms = R.anchors_and_formations(days, "2016-12-30", "2024-01-29")
    assert anchors[0] == pd.Timestamp("2016-01-04")
    assert anchors[forms[0]] == pd.Timestamp("2016-12-30") and forms[0] == 12
    assert anchors[forms[-1] + 1] == pd.Timestamp("2024-01-29")
    assert len(forms) == 85
