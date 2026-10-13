import os

import numpy as np
import pandas as pd
import pytest

import backtest
import ledger
from strategies.base import Strategy


@pytest.fixture
def conn(tmp_path):
    return ledger.connect(tmp_path / "ledger.db")


def prices(n=600, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, n))
    return pd.DataFrame({"timestamp": pd.bdate_range("2015-01-01", periods=n),
                         "open": close * (1 + rng.normal(0, 0.002, n)), "close": close})


class AlwaysLong(Strategy):
    NAME, VERSION = "always_long", "1"
    stop_loss_pct = None
    def entry(self, bars): return 1


class Peeker(Strategy):
    """Records how many bars it was shown, to prove no future data leaks in."""
    NAME, VERSION = "peeker", "1"
    seen = []
    def entry(self, bars):
        Peeker.seen.append(len(bars)); return 0


def test_search_and_lessons(conn):
    a = ledger.add_hypothesis(conn, "Gap fade", "price_analyst", "SPY")
    ledger.add_hypothesis(conn, "Rate cut drift", "macro_watcher", "TLT")
    ledger.update(conn, a, status="failed", regime="choppy")
    assert [h["id"] for h in ledger.search(conn, market="SPY", status="failed")] == [a]
    assert ledger.search(conn, regime="trending_up") == []
    ledger.add_lesson(conn, a, "first", "critic"); ledger.add_lesson(conn, a, "second", "critic")
    assert "first" in ledger.get(conn, a)["lessons"] and "second" in ledger.get(conn, a)["lessons"]
    assert ledger.search(conn, text="second")[0]["id"] == a


def test_variation_cap_and_no_rerun(conn):
    h = ledger.add_hypothesis(conn, "x", "a", "SPY")
    for v in range(ledger.MAX_VARIATIONS):
        ledger.record_trial(conn, h, str(v), 0.01, 100)
    assert ledger.get(conn, h)["variations_tried"] == ledger.MAX_VARIATIONS
    with pytest.raises(PermissionError):
        ledger.record_trial(conn, h, "new", 0.01, 100)
    with pytest.raises(PermissionError):
        ledger.record_trial(conn, h, "0", 0.01, 100)


def test_sealed_only_once(conn):
    h = ledger.add_hypothesis(conn, "x", "a", "SPY")
    ledger.claim_sealed_test(conn, h)
    with pytest.raises(PermissionError):
        ledger.claim_sealed_test(conn, h)


def test_prediction_locked(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(backtest, "RESULTS", tmp_path)
    memo = tmp_path / "memo.md"; memo.write_text("Expect 8%/yr, fail if Sharpe < 0.5")
    h = ledger.add_hypothesis(conn, "x", "a", "SPY")
    dest = backtest.save_prediction(conn, h, "strategies/x_v1.py", memo)
    assert "8%" in backtest.verify_prediction(conn, h)
    with pytest.raises(PermissionError):
        backtest.save_prediction(conn, h, "strategies/x_v1.py", memo)
    os.chmod(dest, 0o644); dest.write_text("Expect 20%")
    with pytest.raises(PermissionError, match="edited"):
        backtest.verify_prediction(conn, h)


def test_split_keeps_sealed_out():
    dev, sealed = backtest.split(prices(100), 25)
    assert len(dev) == 75 and len(sealed) == 25
    assert dev["timestamp"].max() < sealed["timestamp"].min()


def test_no_lookahead():
    Peeker.seen = []
    backtest.run(Peeker(), prices(50))
    assert Peeker.seen == list(range(1, 50))   # bar t sees exactly t+1 rows


def test_costs_and_delay_hurt():
    df = prices()
    base = backtest.metrics(*backtest.run(AlwaysLong(), df, cost_bps=0))
    costly = backtest.metrics(*backtest.run(AlwaysLong(), df, cost_bps=50))
    assert costly["total_return_pct"] < base["total_return_pct"]


def test_deflated_sharpe_rises_bar_with_trials():
    one = backtest.deflated_sharpe(0.05, 1000, 0, 3, [0.05])
    many = backtest.deflated_sharpe(0.05, 1000, 0, 3, list(np.linspace(-0.05, 0.05, 50)))
    assert many["sr0"] > one["sr0"] and many["dsr"] < one["dsr"]


def test_full_run_writes_results(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(backtest, "RESULTS", tmp_path)
    data = tmp_path / "SPY.csv"; prices(800).to_csv(data, index=False)
    strat = tmp_path / "always_long_v1.py"
    strat.write_text("from strategies.base import Strategy\n"
                     "class AL(Strategy):\n    NAME, VERSION = 'al', '1'\n"
                     "    def entry(self, bars): return 1\n")
    memo = tmp_path / "memo.md"; memo.write_text("prediction")
    h = ledger.add_hypothesis(conn, "x", "a", "SPY")
    with pytest.raises(PermissionError):           # no prediction yet
        backtest.cmd_run(conn, h, strat, data, 25)
    backtest.save_prediction(conn, h, strat, memo)
    jpath, _ = backtest.cmd_run(conn, h, strat, data, 25)
    assert "deflated_sharpe" in jpath.read_text()
    assert ledger.get(conn, h)["variations_tried"] == 1
    backtest.cmd_sealed(conn, h, strat, data, 25)
    with pytest.raises(PermissionError):
        backtest.cmd_sealed(conn, h, strat, data, 25)
