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
