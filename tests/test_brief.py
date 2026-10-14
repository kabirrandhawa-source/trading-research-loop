from brief import gather


def test_a_failing_section_does_not_stop_the_others(monkeypatch):
    monkeypatch.setattr(gather, "movers", lambda: (_ for _ in ()).throw(RuntimeError("screener down")))
    monkeypatch.setattr(gather, "news", lambda: [{"headline": "x"}])
    for name in ("etf_moves", "crypto", "paper_account", "loop_status"):
        monkeypatch.setattr(gather, name, lambda: {"ok": True})
    d = gather.gather()
    assert d["movers"] == {"error": "RuntimeError: screener down"}
    assert d["news"] == [{"headline": "x"}] and d["crypto"] == {"ok": True}
