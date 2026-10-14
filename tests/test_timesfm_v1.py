import math

import pandas as pd

from strategies.timesfm_v1 import TimesFMLongFlat


def bars(ts, close):
    ts = pd.Timestamp(ts)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    return pd.DataFrame({"timestamp": [ts], "open": [close], "close": [close]})


def test_long_when_forecast_up_flat_when_down(monkeypatch):
    t1, t2 = pd.Timestamp("2020-01-02", tz="UTC"), pd.Timestamp("2020-01-03", tz="UTC")
    monkeypatch.setattr(TimesFMLongFlat, "_signal", {t1: math.log(101) - math.log(100), t2: -0.002})
    s = TimesFMLongFlat()
    assert s.entry(bars(t1, 100)) == 1 and s.exit(bars(t1, 100), {}) is False
    assert s.entry(bars(t2, 100)) == 0 and s.exit(bars(t2, 100), {}) is True
    assert s.entry(bars("2020-01-06", 100)) == 0          # no forecast for that day: stay flat


def test_scoring_finds_a_planted_signal_and_ignores_noise(tmp_path):
    import numpy as np
    from tsfm import evaluate
    rng = np.random.default_rng(0)
    rows = []
    for sym in "ABCDEFGH":
        lc = np.cumsum(rng.normal(0, 0.01, 400)) + 4
        for t in range(399):
            nxt = lc[t + 1] - lc[t]
            for kind, sig in (("good", nxt + rng.normal(0, 0.01)), ("noise", rng.normal(0, 0.01))):
                rows.append((kind, sym, pd.Timestamp("2020-01-01") + pd.Timedelta(days=t), math.exp(lc[t]),
                             lc[t] + sig, lc[t] - 0.02, lc[t], lc[t] + 0.02))
    df = pd.DataFrame(rows, columns=["kind", "symbol", "timestamp", "close", "fc", "q10", "q50", "q90"])
    for kind, expect_strong in (("good", True), ("noise", False)):
        p = tmp_path / f"{kind}.csv"; df[df.kind == kind].drop(columns="kind").to_csv(p, index=False)
        s = evaluate.score(evaluate.frame(p))
        assert (s["cross_sectional_ic_t"] > 5) == expect_strong
