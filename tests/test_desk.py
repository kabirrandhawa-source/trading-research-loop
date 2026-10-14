from desk import speak, status


def test_speech_text_is_cleaned_and_capped():
    t = speak.clean("**BTC** failed. See [report](backtests/x.md) and `ledger.py`. https://x.y " + "word " * 400)
    assert "*" not in t and "report" in t and "backtests/" not in t and "ledger.py" not in t and "http" not in t
    assert len(t) <= speak.MAX_CHARS + 1


def test_status_survives_a_broken_section(monkeypatch):
    monkeypatch.setattr(status, "paper_account", lambda: (_ for _ in ()).throw(RuntimeError("alpaca down")))
    for name in ("jobs", "recorders", "ledger_state", "latest_files", "recent_alerts", "git_state"):
        monkeypatch.setattr(status, name, lambda: {})
    s = status.status()
    assert s["paper_account"] == {"error": "RuntimeError: alpaca down"}
    assert "Paper account" in status.render({**s, "ledger": {"error": "x"}, "recorders": {"error": "x"}, "jobs": {"error": "x"}})


def test_snapshot_rows_are_uniform_and_keys_unique(monkeypatch):
    from desk import snapshot
    monkeypatch.setattr(snapshot, "lessons", lambda: {1: "Dropped before testing: too few trades"})
    s = {"as_of": "2026-10-14 01:00 UTC",
         "jobs": {"daily": "loaded, idle (last exit 0)", "pm-stream": "running (pid 1)", "pm-recorder": "running (pid 2)", "pm-archive": "loaded, idle (last exit 0)"},
         "recorders": {"stream_last_hour": {"ws_tob": 10}, "stream_last_write_s_ago": 3, "data_pm_gb": 1.0, "archived_days": 0},
         "ledger": {"by_status": {"failed": 1, "passed_backtest": 1}, "hypotheses": [
             {"id": 1, "status": "failed", "market": "SPY", "idea": "x", "variations": 1},
             {"id": 2, "status": "passed_backtest", "market": "QQQ", "idea": "y", "variations": 2}],
             "waiting_for_your_sealed_test_decision": [2], "papers_read": 0},
         "paper_account": {"equity": 100000.0, "day_change": 0.0, "positions": []},
         "latest": {"daily_summary": None}, "alerts_last_24h": ["12:00 UTC [high] Kalshi stream down"],
         "git": {"last_commit": "abc x", "uncommitted_files": 0, "sync": "## main...origin/main"}, "free_disk_gb": 50.0}
    rows = snapshot.build(s)
    assert len({r["key"] for r in rows}) == len(rows)
    assert all(set(r) == {"section", "key", "label", "status", "value", "detail"} for r in rows)
    k = {r["key"]: r for r in rows}
    assert k["kpi-tested"]["value"] == 2 and k["kpi-edges"]["value"] == 1
    assert k["kpi-waiting"]["status"] == "attention" and k["kpi-waiting"]["detail"] == "#2"
    assert k["alert-0"]["status"] == "high" and k["alert-0"]["label"] == "Kalshi stream down"
    assert k["health-summary"]["status"] == "attention"
