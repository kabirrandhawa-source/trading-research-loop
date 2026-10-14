import json
from types import SimpleNamespace

import pytest

from sleeve import book as sb
from sleeve import decide, execute

CFG = {"budget": 10000, "universe": ["QQQ", "GLD", "TLT", "XLE"], "long_only": True, "max_positions": 3,
       "max_position_pct_of_sleeve": 40, "min_trade_dollars": 200, "benchmark": "SPY"}
OK = {"date": "2026-10-14", "targets": {"QQQ": 40, "GLD": 30}, "reasoning": "Tech leading and gold as a hedge into CPI."}


def test_valid_decision_is_cleaned():
    d = decide.validate({**OK, "targets": {"qqq": 40, "GLD": 30, "TLT": 0}}, CFG, today="2026-10-14")
    assert d["targets"] == {"QQQ": 40.0, "GLD": 30.0}


@pytest.mark.parametrize("bad, msg", [
    ({"date": "2026-10-13"}, "date must be today"),
    ({"targets": {"SPY": 20}}, "not in the sleeve's universe"),
    ({"targets": {"QQQ": -10}}, "long only"),
    ({"targets": {"QQQ": 45}}, "per-position limit"),
    ({"targets": {"QQQ": 40, "GLD": 40, "TLT": 30}}, "max 100%"),
    ({"targets": {"QQQ": 10, "GLD": 10, "TLT": 10, "XLE": 10}}, "over the limit of 3"),
    ({"reasoning": "because"}, "reasoning is required"),
])
def test_rules_are_enforced(bad, msg):
    with pytest.raises(decide.Invalid, match=msg):
        decide.validate({**OK, **bad}, CFG, today="2026-10-14")


def test_one_decision_per_day(tmp_path):
    d = decide.validate(OK, CFG, today="2026-10-14")
    decide.save(d, tmp_path)
    with pytest.raises(decide.Invalid, match="already exists"):
        decide.save(d, tmp_path)


def test_plan_sells_first_and_buys_within_cash():
    book = {"cash": 1000.0, "holdings": {"XLE": 100}, "pending": [], "history": []}   # value 1000 + 100*90 = 10000
    prices = {"QQQ": 500.0, "GLD": 250.0, "XLE": 90.0, "TLT": 80.0}
    orders = execute.plan(book, {"QQQ": 40, "GLD": 30}, prices, CFG)
    assert orders[0] == ("XLE", "sell", 100)                    # exit what's no longer wanted, first
    assert ("QQQ", "buy", 8) in orders and ("GLD", "buy", 12) in orders
    assert sum(q * prices[s] for s, side, q in orders if side == "buy") <= 1000 + 9000


def test_plan_skips_tiny_changes():
    book = {"cash": 6000.0, "holdings": {"QQQ": 8}, "pending": [], "history": []}   # $10k sleeve, QQQ at 40%
    assert execute.plan(book, {"QQQ": 41}, {"QQQ": 500.0}, {**CFG, "max_position_pct_of_sleeve": 100}) == []


class FakeClient:
    def __init__(self, orders):
        self.orders = orders
    def get_order_by_id(self, oid):
        return self.orders[oid]


def test_reconcile_uses_actual_fill_prices():
    book = {"cash": 10000.0, "holdings": {}, "pending": [{"order_id": "a", "symbol": "QQQ", "side": "buy", "qty": 8},
                                                         {"order_id": "b", "symbol": "GLD", "side": "buy", "qty": 12}], "history": []}
    c = FakeClient({"a": SimpleNamespace(status="filled", filled_qty="8", filled_avg_price="501.25"),
                    "b": SimpleNamespace(status="new", filled_qty="0", filled_avg_price=None)})
    b = execute.reconcile(book, c)
    assert b["holdings"] == {"QQQ": 8} and b["cash"] == round(10000 - 8 * 501.25, 2)
    assert [p["order_id"] for p in b["pending"]] == ["b"]


def test_run_sends_orders_through_broker_and_records_value(tmp_path, monkeypatch):
    dd = tmp_path / "decisions"; dd.mkdir()
    (dd / "2026-10-14.json").write_text(json.dumps(decide.validate(OK, CFG, today="2026-10-14")))
    sent = []
    def fake_submit(name, ver, sym, side, qty, cond, why, client=None, extra=None):
        sent.append((sym, side, qty)); return {"decision": "submitted", "order_id": f"id-{sym}"}
    monkeypatch.setattr(execute.broker, "submit", fake_submit)
    monkeypatch.setattr(execute.journal, "log", lambda *a, **k: None)
    prices = {"QQQ": 500.0, "GLD": 250.0, "TLT": 80.0, "XLE": 90.0, "SPY": 700.0}
    res = execute.run(FakeClient({}), "2026-10-14", prices, 700.0, decisions_dir=dd, book_path=tmp_path / "book.json", cfg=CFG)
    assert res["status"] == "executed" and set(sent) == {("QQQ", "buy", 8), ("GLD", "buy", 12)}
    b = sb.load(tmp_path / "book.json", CFG)
    assert b["history"] == [{"day": "2026-10-14", "value": 10000.0, "spy_close": 700.0}] and len(b["pending"]) == 2


def test_sleeve_pauses_if_another_strategy_trades_its_symbols(tmp_path, monkeypatch):
    monkeypatch.setattr(execute.alerts, "send", lambda *a, **k: None)
    res = execute.run(FakeClient({}), "2026-10-14", {"SPY": 1}, 1, decisions_dir=tmp_path, book_path=tmp_path / "b.json",
                      cfg=CFG, conflicts=["QQQ"])
    assert res["status"] == "paused"
