import numpy as np
import pandas as pd
import pytest

from stocks import pairs

P = dict(pairs.PARAMS_V1, cost_bps=0.0, borrow_pa=0.0)


def test_diverge_and_converge_makes_money():
    # j stays at 100; i jumps to 110 (spread 0.10 > 2 x 0.01), then comes back to 100.
    ci = np.array([100, 110, 110, 105, 99, 99.0])
    cj = np.full(6, 100.0)
    pnl, trades = pairs.simulate_pair(ci, cj, ci.copy(), cj.copy(), 100, 100, 0.01, P)
    assert len(trades) == 1 and trades[0]["dir"] == -1 and trades[0]["reason"] == "converged"
    # Short i entered at the open of day 2 (110), covered at the open of day 5 (99): 11/110 = 0.10.
    assert pnl.sum() == pytest.approx(0.10)


def test_costs_and_borrow_reduce_pnl():
    ci = np.array([100, 110, 110, 105, 99, 99.0])
    cj = np.full(6, 100.0)
    gross, _ = pairs.simulate_pair(ci, cj, ci.copy(), cj.copy(), 100, 100, 0.01, P)
    net, _ = pairs.simulate_pair(ci, cj, ci.copy(), cj.copy(), 100, 100, 0.01, pairs.PARAMS_V1)
    assert gross.sum() - net.sum() == pytest.approx(0.0005 * (2 + 99 / 110 + 1) + (110 + 105 + 99) / 110 * 0.005 / 252)   # 4 legs x 5bps (exit at 99) + 3 days borrow on the short


def test_no_trade_inside_threshold_and_open_position_closed_at_end():
    flat = np.full(5, 100.0)
    pnl, trades = pairs.simulate_pair(flat, flat, flat, flat, 100, 100, 0.01, P)
    assert trades == [] and pnl.sum() == 0
    ci = np.array([100, 110, 112, 115.0])
    cj = np.full(4, 100.0)
    _, trades = pairs.simulate_pair(ci, cj, ci.copy(), cj.copy(), 100, 100, 0.01, P)
    assert trades[-1]["reason"] == "period_end"


def test_data_stop_closes_at_last_shared_close():
    ci = np.array([100, 110, 108, np.nan, 90.0])
    oi = np.array([100, 110, 110, np.nan, 90.0])
    cj = np.full(5, 100.0)
    pnl, trades = pairs.simulate_pair(ci, cj, oi, cj.copy(), 100, 100, 0.01, P)
    assert trades[0]["reason"] == "data_end"
    assert pnl.sum() == pytest.approx(2 / 110)        # short from 110 open, out at the 108 close


def test_select_pairs_picks_closest_and_skips_share_classes():
    rng = np.random.default_rng(0)
    base = 100 * np.cumprod(1 + rng.normal(0, 0.01, 252))
    noise = lambda s: 1 + rng.normal(0, s, 252)
    df = pd.DataFrame({"A": base, "A2": base * 1.0001,              # same company, two classes
                       "B": base * noise(0.004), "C": 100 * np.cumprod(1 + rng.normal(0, 0.01, 252))})
    picked = pairs.select_pairs(df, 1, 0.98)
    assert {picked[0][0], picked[0][1]} in ({"A", "B"}, {"A2", "B"})


def test_load_never_reads_sealed(monkeypatch):
    import backtest
    from stocks import universe
    rows = pd.DataFrame({"ticker": ["X", "X"], "day": ["2024-01-29", "2024-01-30"],
                         "open": [1, 1], "high": [1, 1], "low": [1, 1], "close": [1.0, 2.0], "volume": [1, 1]})
    monkeypatch.setattr(universe, "membership", lambda: pd.DataFrame({"ticker": ["X"]}))
    monkeypatch.setattr(universe, "prices", lambda *a, **k: rows)
    close, _, _ = pairs.load()
    assert close.index.max() < pd.Timestamp(backtest.SEALED_START)
