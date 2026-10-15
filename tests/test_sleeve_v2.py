"""Multi-sleeve support: v1 (hypothesis 7) must behave exactly as before; v2 runs beside it."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

import run_daily
from sleeve import book as sb
from sleeve import context_v2, decide, evaluate, execute

CFG = {"budget": 10000, "universe": ["QQQ", "GLD", "TLT", "XLE"], "long_only": True, "max_positions": 3,
       "max_position_pct_of_sleeve": 40, "min_trade_dollars": 200, "benchmark": "SPY"}
OK = {"date": "2026-10-14", "targets": {"QQQ": 40, "GLD": 30}, "reasoning": "Tech leading and gold as a hedge into CPI."}
PRICES = {"QQQ": 500.0, "GLD": 250.0, "TLT": 80.0, "XLE": 90.0, "SPY": 700.0}


class FakeClient:
    def __init__(self, orders=None):
        self.orders = orders or {}
    def get_order_by_id(self, oid):
        return self.orders[oid]
    def submit_order(self, *a, **k):
        raise AssertionError("tests must never reach the broker")


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(execute.journal, "log", lambda *a, **k: None)
    monkeypatch.setattr(execute.alerts, "send", lambda *a, **k: None)


@pytest.fixture
def sent(monkeypatch):
    out = []
    def fake_submit(name, ver, sym, side, qty, cond, why, client=None, extra=None):
        out.append((name, ver, sym, side, qty)); return {"decision": "submitted", "order_id": f"{name}-{sym}-{side}"}
    monkeypatch.setattr(execute.broker, "submit", fake_submit)
    return out


def decision_dir(tmp_path, d=OK):
    dd = tmp_path / "decisions"; dd.mkdir(parents=True, exist_ok=True)
    (dd / f"{d['date']}.json").write_text(json.dumps(decide.validate(d, CFG, today=d["date"])))
    return dd


# ---------- v1 is unchanged ----------

def test_v1_paths_names_and_versions_unchanged():
    assert sb.DIR == sb.ROOT / "paper" / "claude_sleeve"
    assert sb.DEFAULT == "v1" and sb.folder() == sb.DIR and sb.folder("v1") == sb.DIR
    assert (execute.NAME, execute.VERSION) == ("claude_sleeve", "1")
    assert (sb.info()["name"], sb.info()["version"], sb.info()["hypothesis"]) == ("claude_sleeve", "1", 7)
    assert evaluate.VERSION == "claude-sleeve-v1" and sb.info("v1")["prediction_version"] == "claude-sleeve-v1"
    assert sb.config() == sb.config(sb.DIR / "config.json") and sb.config()["approved_by"] == "Kabir, in chat, 2026-10-14"


def test_v2_paths_names_and_config():
    v2 = sb.info("v2")
    assert v2["dir"] == sb.ROOT / "paper" / "claude_sleeve_v2"
    assert (v2["name"], v2["version"], v2["hypothesis"]) == ("claude_sleeve_v2", "1", 10)
    assert sb.by_hypothesis(7) == "v1" and sb.by_hypothesis(10) == "v2"
    c1, c2 = sb.config(), sb.config(sleeve="v2")
    assert c2["budget"] == 10000 and c2["approved_by"] == "Kabir, in chat, 2026-10-15"
    for k in ("universe", "long_only", "max_positions", "max_position_pct_of_sleeve", "min_trade_dollars",
              "evaluation_weeks", "benchmark"):
        assert c1[k] == c2[k]
    assert (v2["dir"] / "decisions").is_dir() and (v2["dir"] / "drafts").is_dir()


def test_v1_execute_default_tags_orders_and_book(tmp_path, quiet, sent):
    dd = decision_dir(tmp_path)
    res = execute.run(FakeClient(), "2026-10-14", PRICES, 700.0, decisions_dir=dd, book_path=tmp_path / "book.json", cfg=CFG)
    assert res["status"] == "executed"
    assert sorted(sent) == [("claude_sleeve", "1", "GLD", "buy", 12), ("claude_sleeve", "1", "QQQ", "buy", 8)]
    b = sb.load(tmp_path / "book.json", CFG)
    assert b["history"] == [{"day": "2026-10-14", "value": 10000.0, "spy_close": 700.0}]
    assert sorted(p["order_id"] for p in b["pending"]) == ["claude_sleeve-GLD-buy", "claude_sleeve-QQQ-buy"]


def test_v1_orders_identical_with_and_without_account_guard(tmp_path, quiet, sent):
    """The new sell guard never changes v1's orders while its book matches the account."""
    book = {"cash": 1000.0, "holdings": {"XLE": 100}, "pending": [], "history": []}
    runs = []
    for i, pos in enumerate([None, {"XLE": 100.0}]):
        d = tmp_path / str(i); d.mkdir()
        (d / "book.json").write_text(json.dumps(book))
        sent.clear()
        execute.run(FakeClient(), "2026-10-14", PRICES, 700.0, decisions_dir=decision_dir(d), book_path=d / "book.json",
                    cfg=CFG, positions=pos)
        runs.append(list(sent))
    assert runs[0] == runs[1] and ("claude_sleeve", "1", "XLE", "sell", 100) in runs[0]


def test_v2_execute_uses_its_own_name_and_folder(tmp_path, quiet, sent, monkeypatch):
    v2dir = tmp_path / "claude_sleeve_v2"
    (v2dir).mkdir()
    (v2dir / "config.json").write_text(json.dumps(CFG))
    decision_dir(v2dir)
    monkeypatch.setitem(sb.SLEEVES, "v2", {**sb.SLEEVES["v2"], "dir": v2dir})
    res = execute.run(FakeClient(), "2026-10-14", PRICES, 700.0, sleeve="v2")
    assert res["status"] == "executed" and {s[0] for s in sent} == {"claude_sleeve_v2"} and {s[1] for s in sent} == {"1"}
    assert len(json.loads((v2dir / "book.json").read_text())["pending"]) == 2


def test_new_book_starts_from_budget(tmp_path):
    assert sb.load(tmp_path / "none.json", {**CFG, "budget": 10000}) == {"cash": 10000.0, "holdings": {}, "pending": [], "history": []}


# ---------- sharing symbols ----------

def test_sibling_sleeves_are_not_conflicts_but_other_strategies_are(tmp_path, quiet, sent):
    dd = decision_dir(tmp_path)
    def go(i, conflicts):
        return execute.run(FakeClient(), "2026-10-14", PRICES, 700.0, decisions_dir=dd, book_path=tmp_path / f"b{i}.json",
                           cfg=CFG, conflicts=conflicts)["status"]
    assert go(1, {"claude_sleeve_v2": ["QQQ", "GLD"], "claude_sleeve": ["XLE"]}) == "executed"
    assert go(2, {"SPY buy-and-hold benchmark": ["QQQ"]}) == "paused"
    assert go(3, ["QQQ"]) == "paused"
    assert go(4, {"SPY buy-and-hold benchmark": ["SPY"]}) == "executed"


def test_sell_capped_at_account_shares_left_after_sibling_sells(tmp_path, quiet, sent):
    """Account holds 15 XLE: v1's book 10, v2's book 8 (books drifted). v1 sells 10, then v2 may only sell 5."""
    sold, pos = {}, {"XLE": 15.0}
    exit_all = {"date": "2026-10-14", "targets": {}, "reasoning": "Exit energy entirely, hold cash for now."}
    for name, held in (("a", 10), ("b", 8)):
        d = tmp_path / name; d.mkdir()
        (d / "book.json").write_text(json.dumps({"cash": 0.0, "holdings": {"XLE": held}, "pending": [], "history": []}))
        execute.run(FakeClient(), "2026-10-14", PRICES, 700.0, decisions_dir=decision_dir(d, exit_all), book_path=d / "book.json",
                    cfg=CFG, positions=pos, committed_sells=sold)
    assert [s[2:] for s in sent] == [("XLE", "sell", 10), ("XLE", "sell", 5)] and sold == {"XLE": 15}


def test_sell_skipped_when_account_has_nothing(tmp_path, quiet, sent):
    (tmp_path / "book.json").write_text(json.dumps({"cash": 0.0, "holdings": {"XLE": 10}, "pending": [], "history": []}))
    exit_all = {"date": "2026-10-14", "targets": {}, "reasoning": "Exit energy entirely, hold cash for now."}
    res = execute.run(FakeClient(), "2026-10-14", PRICES, 700.0, decisions_dir=decision_dir(tmp_path, exit_all),
                      book_path=tmp_path / "book.json", cfg=CFG, positions={})
    assert sent == [] and res["orders"][0][2] == 0


# ---------- decide ----------

def test_draft_folder_picks_the_sleeve():
    assert decide.sleeve_for_draft(sb.DIR / "drafts" / "x.json") == "v1"
    assert decide.sleeve_for_draft(sb.info("v2")["dir"] / "drafts" / "x.json") == "v2"
    assert decide.sleeve_for_draft("/tmp/x.json") == "v1"
    with pytest.raises(decide.Invalid, match="folder"):
        decide.sleeve_for_draft(sb.DIR / "drafts" / "x.json", "v2")


def test_decide_saves_to_the_right_sleeve(tmp_path, monkeypatch):
    monkeypatch.setitem(sb.SLEEVES, "v2", {**sb.SLEEVES["v2"], "dir": tmp_path})
    d = decide.validate(OK, CFG, today="2026-10-14")
    assert decide.save(d, sleeve="v2") == tmp_path / "decisions" / "2026-10-14.json"


# ---------- run_daily ----------

def test_run_daily_runs_v1_then_v2_and_dry_run_places_nothing(tmp_path, monkeypatch, sent, quiet):
    dirs = {}
    for k in ("v1", "v2"):
        d = tmp_path / k; d.mkdir()
        (d / "config.json").write_text(json.dumps(CFG))
        decision_dir(d)
        dirs[k] = d
        monkeypatch.setitem(sb.SLEEVES, k, {**sb.SLEEVES[k], "dir": d})
    monkeypatch.setattr(run_daily.journal, "log", lambda *a, **k: None)
    monkeypatch.setattr(run_daily.alerts, "send", lambda *a, **k: None)
    monkeypatch.setattr(run_daily.backtest, "load_prices", lambda p: pd.DataFrame({"close": [PRICES[p.stem]]}))
    monkeypatch.setattr(run_daily, "is_fresh", lambda bars, today: True)
    a = SimpleNamespace(today="2026-10-14", dry_run=True)
    summary = {"orders": []}
    assert run_daily.run_sleeve(FakeClient(), a, {}, summary, sleeve="v1")["status"] == "dry run"
    assert run_daily.run_sleeve(FakeClient(), a, {}, summary, sleeve="v2")["status"] == "dry run"
    assert sent == [] and not (dirs["v1"] / "book.json").exists()
    a.dry_run = False
    taken = {"SPY buy-and-hold benchmark": ["SPY"]}
    r1 = run_daily.run_sleeve(FakeClient(), a, taken, summary, sleeve="v1", positions={}, committed_sells={})
    r2 = run_daily.run_sleeve(FakeClient(), a, taken, summary, sleeve="v2", positions={}, committed_sells={})
    assert r1["status"] == r2["status"] == "executed"
    assert [s[0] for s in sent] == ["claude_sleeve"] * 2 + ["claude_sleeve_v2"] * 2
    assert summary["orders"] == ["submitted"] * 4


def test_run_daily_missing_v2_config_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setitem(sb.SLEEVES, "v2", {**sb.SLEEVES["v2"], "dir": tmp_path / "nothing"})
    assert run_daily.run_sleeve(FakeClient(), SimpleNamespace(today="2026-10-14", dry_run=True), {}, {"orders": []}, sleeve="v2") is None


# ---------- evaluate ----------

def test_compare_side_by_side_on_common_days():
    h1 = [{"day": d, "value": v, "spy_close": s} for d, v, s in [("a", 100, 10), ("b", 110, 11), ("c", 120, 12)]]
    h2 = [{"day": d, "value": v, "spy_close": s} for d, v, s in [("b", 200, 11), ("c", 210, 12)]]
    out = evaluate.compare({"v1": {"history": h1}, "v2": {"history": h2}})
    assert out["common_days"] == 2
    assert out["side_by_side"]["v1"]["sleeve_return_pct"] == round((120 / 110 - 1) * 100, 2)
    assert out["side_by_side"]["v2"]["sleeve_return_pct"] == 5.0
    assert out["side_by_side"]["SPY"]["sleeve_return_pct"] == round((12 / 11 - 1) * 100, 2)
    assert out["own_history"]["v1"]["days"] == 3


# ---------- context_v2 ----------

def test_context_v2_sections_fail_soft_and_report_failures(monkeypatch):
    def boom():
        raise RuntimeError("no network")
    monkeypatch.setattr(context_v2, "base", boom)
    out = context_v2.build({"ok": lambda: {"x": 1}, "bad": boom})
    assert out["base"] == {"error": "RuntimeError: no network"} and out["ok"] == {"x": 1}
    assert set(out["failed_sections"]) == {"base", "bad"}


def test_context_v2_trims_to_size(monkeypatch):
    monkeypatch.setattr(context_v2, "base", lambda: {"headlines": [{"headline": "h" * 300}] * 40})
    big = {"morning_brief": lambda: {"text": "b" * 30000}, "daily_summary": lambda: {"text": "s" * 20000},
           "research_memos": lambda: [{"excerpt": "m" * 450}] * 6}
    out = context_v2.build(big)
    assert out["size_bytes"] < context_v2.MAX_BYTES


def test_context_v2_text_sections(tmp_path):
    j = tmp_path / "journal"; j.mkdir()
    (j / "summary-2026-10-12.md").write_text("old"); (j / "summary-2026-10-13.md").write_text("# newest summary")
    (j / "brief-2026-10-15.md").write_text("brief text")
    assert context_v2.daily_summary(j)["file"] == "journal/summary-2026-10-13.md"
    assert context_v2.morning_brief(pd.Timestamp("2026-10-15").date(), j)["text"] == "brief text"
    assert context_v2.morning_brief(pd.Timestamp("2026-10-16").date(), j)["available"] is False
    r = tmp_path / "research"; r.mkdir()
    (r / "a-2026-10-01.md").write_text("# Old memo\nbody one"); (r / "b-2026-10-14.md").write_text("# New memo\nbody two")
    (r / "AREAS.md").write_text("# areas")
    memos = context_v2.research_memos(r)
    assert [m["title"] for m in memos] == ["New memo", "Old memo"] and memos[0]["excerpt"] == "body two"


def test_context_v2_timesfm_is_labeled_and_stale_files_ignored(tmp_path):
    pd.DataFrame({"symbol": ["SPY"], "timestamp": ["2024-01-29 05:00:00+00:00"], "close": [100.0], "fc": [4.6],
                  "q10": [4.5], "q90": [4.7]}).to_csv(tmp_path / "f.csv", index=False)
    out = context_v2.timesfm(tmp_path, pd.Timestamp("2026-10-15").date())
    assert out["available"] is False and "hypothesis 6" in out["label"]
    assert context_v2.timesfm(tmp_path / "none", pd.Timestamp("2026-10-15").date())["available"] is False


def test_context_v2_ledger_and_track_record(tmp_path):
    import ledger
    conn = ledger.connect(tmp_path / "l.db")
    hid = ledger.add_hypothesis(conn, "idea", "human", "SPY")
    ledger.add_lesson(conn, hid, "it failed", "backtester")
    rows = context_v2.desk_ledger(conn)
    assert rows[0]["status"] == "untested" and "it failed" in rows[0]["latest_lessons"][0]
    (tmp_path / "decisions").mkdir()
    (tmp_path / "config.json").write_text(json.dumps(CFG))
    (tmp_path / "decisions" / "2026-10-15.json").write_text(json.dumps({"date": "2026-10-15", "targets": {"QQQ": 40}, "reasoning": "r"}))
    tr = context_v2.own_track_record(tmp_path)
    assert tr["decisions"][0]["targets"] == {"QQQ": 40} and tr["score_vs_spy"]["days"] == 0


def test_context_v2_never_contains_config_secrets(monkeypatch):
    import os
    monkeypatch.setattr(context_v2, "base", lambda: {})
    text = json.dumps(context_v2.build({"daily_summary": context_v2.daily_summary, "timesfm": context_v2.timesfm}))
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "SEC_CONTACT"):
        v = os.getenv(k)
        assert k not in text and (not v or v not in text)
