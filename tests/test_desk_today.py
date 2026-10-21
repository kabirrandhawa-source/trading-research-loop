import json
from datetime import date

from desk import today


def test_orders_sorts_submitted_blocked_errors_and_netted(tmp_path):
    rows = [{"strategy": "claude_sleeve", "symbol": "QQQ", "side": "buy", "qty": 1, "decision": "submitted"},
            {"strategy": "claude_sleeve_v2", "symbol": "DIA", "side": "buy", "qty": 6, "decision": "blocked",
             "risk_check": "Too many open positions."},
            {"strategy": "claude_sleeve_v2", "symbol": "QQQ", "decision": "broker_error", "error": "wash trade"},
            {"event": "slice_intent", "strategy": "claude_sleeve", "symbol": "QQQ", "decision": "netted"},
            "not json"]
    (tmp_path / "2026-10-16.jsonl").write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows))
    out = today.orders("2026-10-16", journal_dir=tmp_path)
    assert [len(out[k]) for k in ("submitted", "blocked", "errors", "netted")] == [1, 1, 1, 1]
    assert out["blocked"][0]["risk_check"] == "Too many open positions."
    assert today.orders("2026-01-01", journal_dir=tmp_path)["note"] == "no journal for this day"


def test_summaries_lists_weekdays_only(tmp_path):
    (tmp_path / "summary-2026-10-15.md").write_text("x")
    out = today.summaries(5, journal_dir=tmp_path, today=date(2026, 10, 19))      # a Monday
    assert list(out) == ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]
    assert out["2026-10-15"] is True and out["2026-10-16"] is False
