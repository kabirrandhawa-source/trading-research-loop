import json

import pandas as pd
import pytest

import ledger
import run_daily
from strategies.base import Strategy


class S(Strategy):
    NAME, VERSION = "s", "1"
    stop_loss_pct, take_profit_pct = 5.0, 10.0
    def entry(self, bars): return 1 if bars["close"].iloc[-1] > 100 else 0
    def exit(self, bars, pos): return pos["bars_held"] >= 3


def bars(closes):
    return pd.DataFrame({"timestamp": pd.bdate_range("2026-10-01", periods=len(closes), tz="UTC"),
                         "open": closes, "close": closes})


def test_entry_and_no_entry():
    assert run_daily.decide(S(), bars([99, 101]), 0, None, None)[0] == "open"
    assert run_daily.decide(S(), bars([99, 99]), 0, None, None)[0] is None


def test_stop_target_and_time_exit():
    assert "stop" in run_daily.decide(S(), bars([100, 94]), 10, 100, "2026-10-01")[2]
    assert "profit" in run_daily.decide(S(), bars([100, 111]), 10, 100, "2026-10-01")[2]
    b = bars([100, 101, 101, 101, 101])                     # opened 10-01 -> 4 bars held after
    assert run_daily.decide(S(), b, 10, 100, "2026-10-01")[0] == "close"
    assert run_daily.decide(S(), b, 10, 100, "2026-10-06")[0] is None


def test_short_stop():
    assert "stop" in run_daily.decide(S(), bars([100, 106]), -10, 100, "2026-10-01")[2]


def test_only_promoted_and_one_per_symbol(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily, "BENCHMARKS", tmp_path / "none.json")
    conn = ledger.connect(tmp_path / "l.db")
    a = ledger.add_hypothesis(conn, "a", "x", "SPY")
    b = ledger.add_hypothesis(conn, "b", "x", "spy")
    ledger.add_hypothesis(conn, "c", "x", "QQQ")                       # untested: ignored
    for h in (a, b):
        ledger.update(conn, h, status="passed_backtest", strategy_file="strategies/s_v1.py")
    assert run_daily.promoted(conn) == []                            # no sealed result yet
    ledger.record_sealed_result(conn, a, {"ok": 1})
    assert [s for _, s in run_daily.promoted(conn)] == ["SPY"]
    ledger.record_sealed_result(conn, b, {"ok": 1})
    with pytest.raises(RuntimeError, match="both trade SPY"):
        run_daily.promoted(conn)


def test_bars_held_reads_journal(tmp_path):
    (tmp_path / "2026-10-01.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"timestamp": "2026-10-01T21:00:00", "strategy": "s", "symbol": "SPY", "decision": "blocked", "action": "open"},
        {"timestamp": "2026-10-02T21:00:00", "strategy": "s", "symbol": "SPY", "decision": "submitted", "action": "open"},
        {"timestamp": "2026-10-03T21:00:00", "strategy": "s", "symbol": "SPY", "decision": "submitted", "action": "close"},
    ]))
    assert run_daily.bars_held("s", "SPY", tmp_path) == "2026-10-02"


def test_is_fresh_uses_new_york_date():
    b = pd.DataFrame({"timestamp": pd.to_datetime(["2026-10-09 04:00:00+00:00"])})
    assert run_daily.is_fresh(b, "2026-10-09")
    assert not run_daily.is_fresh(b, "2026-10-12")


def test_benchmarks_are_traded_but_clash_with_a_strategy_on_the_same_symbol(tmp_path):
    bm = tmp_path / "b.json"
    bm.write_text(json.dumps([{"name": "SPY bench", "strategy_file": "strategies/benchmark_spy_v1.py",
                               "strategy_version": "1", "symbol": "SPY"}]))
    conn = ledger.connect(tmp_path / "l.db")
    got = run_daily.promoted(conn, bm)
    assert [(h["benchmark"], s) for h, s in got] == [("SPY bench", "SPY")]
    h = ledger.add_hypothesis(conn, "x", "a", "SPY")
    ledger.update(conn, h, status="passed_backtest", strategy_file="strategies/s_v1.py")
    ledger.record_sealed_result(conn, h, {"ok": 1})
    with pytest.raises(RuntimeError, match="both trade SPY"):
        run_daily.promoted(conn, bm)


def test_benchmark_strategy_always_holds():
    from strategies.benchmark_spy_v1 import BenchmarkSPY
    s = BenchmarkSPY()
    assert s.entry(bars([100])) == 1 and s.exit(bars([100]), {"side": 1}) is False
    assert s.size(100_000, 500) == 19                       # 9.5% of $100k at $500 = 19 shares


def test_heartbeat_alerts_loudly_when_orders_are_blocked(monkeypatch):
    sent = []
    monkeypatch.setattr(run_daily.alerts, "send", lambda *a, **k: sent.append(a))
    base = {"date": "2026-10-15", "strategies": 0, "skipped": [], "no_action": 0}
    run_daily.heartbeat({**base, "orders": ["blocked", "blocked"],
                         "blocked": ["Claude sleeve v2: buy 6 DIA", "Claude sleeve v2: buy 45 XLF"]})
    title, msg, priority = sent[-1][:3]
    assert "2 order(s) BLOCKED" in title and priority == "high" and "buy 45 XLF" in msg
    run_daily.heartbeat({**base, "orders": ["submitted"]})
    assert sent[-1][0] == "Daily run OK 2026-10-15" and sent[-1][2] == "low"
