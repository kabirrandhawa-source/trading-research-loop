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


def write_strategy(dirpath, name, version, hid=None):
    f = dirpath / f"{name}_v{version}.py"
    f.write_text("from strategies.base import Strategy\n"
                 f"class S(Strategy):\n    NAME, VERSION, HYPOTHESIS_ID = {name!r}, {version!r}, {hid!r}\n"
                 "    stop_loss_pct = None\n    def entry(self, bars): return 1\n")
    return f


def test_prediction_locked_per_version(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(backtest, "RESULTS", tmp_path)
    memo = tmp_path / "memo.md"; memo.write_text("Expect 8%/yr, fail if Sharpe < 0.5")
    h = ledger.add_hypothesis(conn, "x", "a", "SPY")
    v1, v2 = write_strategy(tmp_path, "x", "1"), write_strategy(tmp_path, "x", "2")
    dest = backtest.save_prediction(conn, h, v1, memo)
    assert "8%" in backtest.verify_prediction(conn, h, "1")
    with pytest.raises(PermissionError):                    # v1 can't be replaced
        backtest.save_prediction(conn, h, v1, memo)
    with pytest.raises(PermissionError, match="No saved prediction"):
        backtest.verify_prediction(conn, h, "2")             # v2 needs its own
    memo.write_text("v2: expect 5%")
    backtest.save_prediction(conn, h, v2, memo)
    assert "5%" in backtest.verify_prediction(conn, h, "2")
    os.chmod(dest, 0o644); dest.write_text("Expect 20%")
    with pytest.raises(PermissionError, match="edited"):
        backtest.verify_prediction(conn, h, "1")


def test_strategy_must_match_hypothesis(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(backtest, "RESULTS", tmp_path)
    memo = tmp_path / "m.md"; memo.write_text("p")
    a = ledger.add_hypothesis(conn, "a", "x", "SPY")
    b = ledger.add_hypothesis(conn, "b", "x", "SPY")
    with pytest.raises(PermissionError, match="belongs to hypothesis"):
        backtest.save_prediction(conn, b, write_strategy(tmp_path, "y", "1", hid=a), memo)


def test_drop_and_papers(conn):
    h = ledger.add_hypothesis(conn, "IBS bounce", "price_analyst", "QQQ")
    ledger.drop(conn, h, "next-open fills kill it", "skeptic")
    got = ledger.get(conn, h)
    assert got["status"] == "dropped" and "next-open" in got["lessons"]
    with pytest.raises(PermissionError):
        ledger.drop(conn, h, "again", "skeptic")
    pid = ledger.add_paper(conn, "https://ssrn.com/abstract=1", "Pre-FOMC drift", "testable",
                           published_date="2011-09-01", claim="SPY rises before FOMC", hypothesis_id=h)
    assert ledger.search_papers(conn, "FOMC")[0]["id"] == pid
    with pytest.raises(PermissionError):
        ledger.add_paper(conn, "https://ssrn.com/abstract=1", "dup", "weak")


def test_migrates_v1_ledger(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    old = sqlite3.connect(db)
    old.executescript(V1_SCHEMA)
    old.execute("INSERT INTO hypotheses (idea, source_agent, market, status, strategy_version, "
                "prediction_path, prediction_sha256, lessons) VALUES "
                "('fomc', 'macro', 'SPY', 'failed', '1', '/p.md', 'abc', 'lesson')")
    old.execute("INSERT INTO trials (hypothesis_id, strategy_version, sharpe_per_period, n_obs) "
                "VALUES (1, '1', -0.01, 100)")
    old.commit(); old.close()
    conn = ledger.connect(db)
    h = ledger.get(conn, 1)
    assert h["status"] == "failed" and h["lessons"] == "lesson" and "prediction_path" not in h
    assert ledger.get_prediction(conn, 1, "1")["sha256"] == "abc"
    assert ledger.trial_sharpes(conn, 1) == [-0.01]
    ledger.drop(conn, ledger.add_hypothesis(conn, "new", "a", "SPY"), "r", "s")   # new status works
    assert ledger.connect(db).execute("PRAGMA user_version").fetchone()[0] == ledger.SCHEMA_VERSION


def test_publication_split():
    df = prices(800)
    pub = str(df["timestamp"].iloc[400].date())
    r = backtest.publication_split(AlwaysLong, df, pub)
    assert set(r) == {"published_date", "before", "after"}
    assert "note" in backtest.publication_split(AlwaysLong, df, str(df["timestamp"].iloc[50].date()))
    assert backtest.publication_split(AlwaysLong, df, None) is None


def test_calendar_requires_sources(tmp_path):
    import calendars
    (tmp_path / "ok.csv").write_text("date,source_url,announced\n2024-01-31,https://fed.gov,2023-06-01\n"
                                     "2024-03-20,https://fed.gov,2024-02-01\n")
    (tmp_path / "bad.csv").write_text("date,source_url\n2024-01-31,\n")
    cal = calendars.load("ok", tmp_path)
    from datetime import date
    assert len(calendars.known_as_of(cal, date(2024, 1, 1))) == 1
    with pytest.raises(ValueError, match="source_url"):
        calendars.load("bad", tmp_path)


V1_SCHEMA = """
CREATE TABLE hypotheses (id INTEGER PRIMARY KEY AUTOINCREMENT,
 created_at TEXT NOT NULL DEFAULT (datetime('now')), idea TEXT NOT NULL, source_agent TEXT NOT NULL,
 market TEXT NOT NULL, date_tested TEXT, strategy_file TEXT, strategy_version TEXT,
 variations_tried INTEGER NOT NULL DEFAULT 0, regime TEXT, backtest_result TEXT,
 sealed_test_result TEXT, paper_result TEXT,
 status TEXT NOT NULL DEFAULT 'untested' CHECK (status IN
   ('untested','failed','passed_backtest','passed_paper','paused','retired')),
 lessons TEXT, prediction_path TEXT, prediction_sha256 TEXT, sealed_used_at TEXT);
CREATE TABLE trials (id INTEGER PRIMARY KEY AUTOINCREMENT,
 hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id),
 run_at TEXT NOT NULL DEFAULT (datetime('now')), strategy_version TEXT NOT NULL,
 sharpe_per_period REAL NOT NULL, n_obs INTEGER NOT NULL, UNIQUE (hypothesis_id, strategy_version));
"""


def test_split_is_a_fixed_date_that_new_rows_cannot_move():
    df = prices(100)                                  # business days from 2015-01-01
    dev, sealed = backtest.split(df, sealed_start="2015-03-02")
    assert dev["timestamp"].max() < pd.Timestamp("2015-03-02") <= sealed["timestamp"].min()
    longer = prices(160)                              # same start, 60 more days appended
    dev2, _ = backtest.split(longer, sealed_start="2015-03-02")
    assert len(dev2) == len(dev)                      # the boundary did not move


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
    monkeypatch.setattr(backtest, "SEALED_START", "2017-05-01")   # inside the synthetic 2015-2018 data
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


def test_v2_ledger_upgrades_to_forward_test_status(tmp_path):
    import sqlite3
    db = tmp_path / "v2.db"
    conn = ledger.connect(db)
    h = ledger.add_hypothesis(conn, "keep me", "a", "SPY")
    ledger.add_lesson(conn, h, "a lesson", "critic")
    conn.execute("PRAGMA user_version = 2"); conn.commit(); conn.close()
    conn = ledger.connect(db)                     # triggers the rebuild
    assert conn.execute("PRAGMA user_version").fetchone()[0] == ledger.SCHEMA_VERSION
    assert "a lesson" in ledger.get(conn, h)["lessons"]
    ledger.update(conn, h, status="forward_test")
    assert ledger.get(conn, h)["status"] == "forward_test"
