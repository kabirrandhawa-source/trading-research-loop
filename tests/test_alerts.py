import json
import sys
from types import SimpleNamespace

import pytest

import alerts
import run_daily


def test_send_never_raises_and_journals(tmp_path, monkeypatch):
    def boom(*a, **k): raise RuntimeError("no network")
    monkeypatch.setattr(alerts, "_mac", boom)
    monkeypatch.setattr(alerts, "_ntfy", boom)
    res = alerts.send("t", "m", journal_dir=tmp_path, state_path=tmp_path / "s.json")
    assert res["mac"].startswith("error") and res["ntfy"].startswith("error")
    logged = json.loads(next(tmp_path.glob("*.jsonl")).read_text())
    assert logged["event"] == "alert" and logged["title"] == "t"


def test_ntfy_skipped_without_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert "skipped" in alerts._ntfy("t", "m", "default", [])


def test_ntfy_posts_to_topic(monkeypatch):
    sent = {}
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def fake_urlopen(req, timeout):
        sent.update(url=req.full_url, prio=req.get_header("Priority"), body=req.data)
        return Resp()
    monkeypatch.setenv("NTFY_TOPIC", "abc123")
    monkeypatch.setattr(alerts.urllib.request, "urlopen", fake_urlopen)
    assert alerts._ntfy("Title", "body", "urgent", ["x"]) == "ok"
    assert sent == {"url": "https://ntfy.sh/abc123", "prio": "5", "body": b"body"}


@pytest.fixture
def captured(monkeypatch):
    got = []
    monkeypatch.setattr(run_daily.alerts, "send", lambda t, m, p="default", tags=(), **k: got.append((t, p)))
    return got


REC = {"side": "buy", "qty": 10, "symbol": "SPY", "strategy": "s", "version": "1", "reasoning": "r"}


def test_order_alert_routing(captured):
    run_daily.order_alert({**REC, "decision": "submitted", "order_id": "x"})
    run_daily.order_alert({**REC, "decision": "blocked", "risk_check": "Daily loss limit hit."})
    run_daily.order_alert({**REC, "decision": "broker_error", "error": "timeout"})
    assert [p for _, p in captured] == ["default", "high", "urgent"]
    assert captured[1][0].startswith("BLOCKED")


def test_failed_run_sends_urgent_alert(captured, monkeypatch, tmp_path):
    monkeypatch.setattr(run_daily, "LOCK_PATH", tmp_path / "lock")
    monkeypatch.setattr(run_daily.journal, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(run_daily, "run", lambda a: (_ for _ in ()).throw(RuntimeError("feed down")))
    monkeypatch.setattr(sys, "argv", ["run_daily.py"])
    assert run_daily.main() == 1
    assert captured == [("Daily run FAILED", "urgent")]


def test_heartbeat_mentions_blocks_and_halt(captured, monkeypatch, tmp_path):
    halt = tmp_path / "HALT"; halt.touch()
    monkeypatch.setattr(run_daily.risk, "HALT_PATH", halt)
    run_daily.heartbeat({"date": "2026-10-13", "strategies": 2, "orders": ["submitted", "blocked"],
                         "skipped": ["QQQ: order still open"], "no_action": 0})
    (title, prio), = captured
    assert prio == "high" and "2026-10-13" in title and "BLOCKED" in title   # a blocked order is never "OK"


def test_second_run_exits_while_first_holds_lock(captured, monkeypatch, tmp_path):
    import fcntl
    lock_path = tmp_path / "lock"
    monkeypatch.setattr(run_daily, "LOCK_PATH", lock_path)
    monkeypatch.setattr(run_daily.journal, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(run_daily, "run", lambda a: pytest.fail("should not run"))
    monkeypatch.setattr(sys, "argv", ["run_daily.py"])
    held = open(lock_path, "w"); fcntl.flock(held, fcntl.LOCK_EX)
    try:
        assert run_daily.main() == 0
    finally:
        held.close()


def test_repeats_are_suppressed_but_urgent_always_sent(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "_mac", lambda t, m: sent.append(t) or "ok")
    monkeypatch.setattr(alerts, "_ntfy", lambda *a: "skipped")
    st = tmp_path / "state.json"
    alerts.send("Recorder stalled", "x", "high", journal_dir=tmp_path, state_path=st)
    r = alerts.send("Recorder stalled", "x", "high", journal_dir=tmp_path, state_path=st)
    alerts.send("Daily run FAILED", "y", "urgent", journal_dir=tmp_path, state_path=st)
    alerts.send("Daily run FAILED", "y", "urgent", journal_dir=tmp_path, state_path=st)
    assert sent == ["Recorder stalled", "Daily run FAILED", "Daily run FAILED"]
    assert "suppressed" in r


@pytest.mark.real_imessage
def test_imessage_only_for_high_and_urgent(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts.subprocess, "run",
                        lambda args, **k: calls.append(args) or SimpleNamespace(returncode=0, stderr=""))
    monkeypatch.setattr(alerts.sys, "platform", "darwin")
    monkeypatch.delenv("SMS_TO", raising=False)
    assert "skipped" in alerts._imessage("t", "m", "urgent")
    monkeypatch.setenv("SMS_TO", "+15550000000")
    assert "skipped" in alerts._imessage("t", "m", "default")
    assert alerts._imessage("Daily run FAILED", "boom", "urgent") == "ok"
    assert len(calls) == 1 and calls[0][-2] == "+15550000000" and "Daily run FAILED" in calls[0][-1]
