"""Netting same-symbol orders across the paper slices (v1, v2, moby) within one 17:00 run.

Approved by Kabir 2026-10-19 after Oct 16: v1 sold 1 QQQ, then v2's buy of 2 QQQ was rejected by Alpaca as a
potential wash trade. Orders go through the REAL broker.submit (kill switch + journal) with a fake client.
"""
import functools
import json
from types import SimpleNamespace

import pandas as pd
import pytest

import broker
import journal
import risk
import run_daily
from sleeve import book as sb
from sleeve import decide, execute

CFG = {"budget": 10000, "universe": ["QQQ", "GLD", "TLT", "XLE"], "long_only": True, "max_positions": 3,
       "max_position_pct_of_sleeve": 40, "min_trade_dollars": 200, "benchmark": "SPY"}
PRICES = {"QQQ": 500.0, "GLD": 250.0, "TLT": 80.0, "XLE": 90.0, "SPY": 700.0}
DAY = "2026-10-14"
WHY = "Tech leading and gold as a hedge into CPI."


class Client:
    """Fake Alpaca paper client: records orders, never reaches a broker."""
    def __init__(self, positions=None, equity=100_000):
        self.acct = SimpleNamespace(equity=str(equity), last_equity=str(equity))
        self.positions = [SimpleNamespace(symbol=s, qty=str(q)) for s, q in (positions or {}).items()]
        self.submitted, self.orders = [], {}

    def get_account(self): return self.acct
    def get_all_positions(self): return self.positions

    def submit_order(self, req):
        oid = f"o{len(self.submitted) + 1}"
        self.submitted.append((req.symbol, str(getattr(req.side, "value", req.side)), float(req.qty)))
        self.orders[oid] = SimpleNamespace(status="new", filled_qty="0", filled_avg_price=None)
        return SimpleNamespace(id=oid)

    def get_order_by_id(self, oid): return self.orders[oid]

    def fill(self, oid, qty, px, status="filled"):
        self.orders[oid] = SimpleNamespace(status=status, filled_qty=str(qty), filled_avg_price=str(px) if qty else None)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    lim = tmp_path / "risk.json"
    lim.write_text(json.dumps({"max_daily_loss_pct": 2, "max_drawdown_pct": 8,
                               "max_position_pct": 10, "max_open_positions": 5}))
    monkeypatch.setattr(risk, "LIMITS_PATH", lim)
    monkeypatch.setattr(risk, "HALT_PATH", tmp_path / "HALT")
    jdir = tmp_path / "journal"; jdir.mkdir()
    monkeypatch.setattr(journal, "JOURNAL_DIR", jdir)
    real = broker.submit
    monkeypatch.setattr(execute.broker, "submit", functools.partial(real, price_fn=lambda s: PRICES[s],
                                                                    peak_path=tmp_path / "peak.json"))
    alerts_sent = []
    monkeypatch.setattr(execute.alerts, "send", lambda *a, **k: alerts_sent.append(a))
    monkeypatch.setattr(run_daily.backtest, "load_prices", lambda p: pd.DataFrame({"close": [PRICES[p.stem]]}))
    monkeypatch.setattr(run_daily, "is_fresh", lambda bars, today: True)
    return SimpleNamespace(root=tmp_path, journal=jdir, alerts=alerts_sent, halt=tmp_path / "HALT")


def entries(desk, **match):
    out = []
    for f in desk.journal.glob("*.jsonl"):
        out += [json.loads(line) for line in f.read_text().splitlines()]
    return [e for e in out if all(e.get(k) == v for k, v in match.items())]


def slice_dir(desk, monkeypatch, key, book, targets):
    d = desk.root / key; (d / "decisions").mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(CFG))
    (d / "book.json").write_text(json.dumps({"pending": [], "history": [], **book}))
    dec = decide.validate({"date": DAY, "targets": targets, "reasoning": WHY}, CFG, today=DAY)
    (d / "decisions" / f"{DAY}.json").write_text(json.dumps(dec))
    monkeypatch.setitem(sb.SLEEVES, key, {**sb.SLEEVES[key], "dir": d})
    return d


def run_slices(client, positions, keys=("v1", "v2")):
    """run_daily's slice phases: plan every slice (v1 first), then send together."""
    a = SimpleNamespace(today=DAY, dry_run=False)
    summary = {"date": DAY, "strategies": 1, "orders": [], "skipped": [], "no_action": 0}
    held, sold, cache = dict(positions), {}, {}
    plans = {k: run_daily.plan_sleeve(client, a, {"SPY buy-and-hold benchmark": ["SPY"]}, k, held, sold, cache)
             for k in keys}
    return run_daily.finish_slices(client, summary, plans), summary


def book(d):
    return json.loads((d / "book.json").read_text())


def total_cash(*dirs):
    return round(sum(book(d)["cash"] for d in dirs), 2)


# v1 holds 4 QQQ + $3,000 (value $5,000); 30% QQQ -> 3 shares: sell 1. v2 has $10,000; 10% QQQ -> buy 2.
V1 = ({"cash": 3000.0, "holdings": {"QQQ": 4.0}}, {"QQQ": 30})
V2 = ({"cash": 10000.0, "holdings": {}}, {"QQQ": 10})


def test_oct16_case_one_net_buy_books_and_cash(desk, monkeypatch):
    d1 = slice_dir(desk, monkeypatch, "v1", *V1)
    d2 = slice_dir(desk, monkeypatch, "v2", *V2)
    c = Client(positions={"QQQ": 4})
    res, summary = run_slices(c, {"QQQ": 4.0})
    assert c.submitted == [("QQQ", "buy", 1.0)]                       # one order for the net, not sell 1 + buy 2
    assert summary["orders"] == ["submitted"] and "blocked" not in summary
    assert res["v1"]["orders"] == [("QQQ", "sell", 1, "netted")] and res["v2"]["orders"] == [("QQQ", "buy", 2, "netted")]
    net = entries(desk, strategy="slices_net")
    assert len(net) == 1 and net[0]["decision"] == "submitted" and net[0]["order_id"] == "o1"
    intents = entries(desk, event="slice_intent")
    assert {(e["strategy"], e["side"], e["qty"], e["net_order_id"], e["crossed_qty"], e["via_net_order_qty"])
            for e in intents} == {("claude_sleeve", "sell", 1, "o1", 1, 0), ("claude_sleeve_v2", "buy", 2, "o1", 1, 1)}
    assert all(e["decision_file"] == f"{DAY}.json" and e["action"] == "rebalance" for e in intents)
    cash0 = total_cash(d1, d2)
    c.fill("o1", 1, 510.0)
    b1, b2 = (execute.reconcile(book(d), c) for d in (d1, d2))
    assert b1["holdings"] == {"QQQ": 3.0} and b1["cash"] == 3000 + 510
    assert b2["holdings"] == {"QQQ": 2} and b2["cash"] == 10000 - 2 * 510
    assert b1["pending"] == b2["pending"] == []
    assert round(b1["cash"] + b2["cash"] - cash0, 2) == -510.0            # cash moves only by the real fill
    sent = []
    monkeypatch.setattr(run_daily.alerts, "send", lambda *a, **k: sent.append(a))
    run_daily.heartbeat(summary)
    assert sent[-1][0].startswith("Daily run OK") and "1 orders sent" in sent[-1][1]


def test_exact_offset_sends_nothing_and_books_at_decision_close(desk, monkeypatch):
    d1 = slice_dir(desk, monkeypatch, "v1", {"cash": 3000.0, "holdings": {"QQQ": 4.0}}, {"QQQ": 20})   # sell 2
    d2 = slice_dir(desk, monkeypatch, "v2", *V2)                                                   # buy 2
    c = Client(positions={"QQQ": 4})
    res, summary = run_slices(c, {"QQQ": 4.0})
    assert c.submitted == [] and summary["orders"] == []
    b1, b2 = book(d1), book(d2)
    assert b1["holdings"] == {"QQQ": 2.0} and b1["cash"] == 4000.0 and b1["pending"] == []
    assert b2["holdings"] == {"QQQ": 2} and b2["cash"] == 9000.0 and b2["pending"] == []
    assert total_cash(d1, d2) == 13000.0
    intents = entries(desk, event="slice_intent")
    assert {e["net_decision"] for e in intents} == {"offset"} and {e["internal_price"] for e in intents} == {500.0}


def test_partial_fill_crossed_part_done_remainder_pro_rata(desk, monkeypatch):
    d1 = slice_dir(desk, monkeypatch, "v1", {"cash": 3000.0, "holdings": {"QQQ": 4.0}}, {"QQQ": 20})   # sell 2
    d2 = slice_dir(desk, monkeypatch, "v2", {"cash": 10000.0, "holdings": {}}, {"QQQ": 20})           # buy 4
    c = Client(positions={"QQQ": 4})
    run_slices(c, {"QQQ": 4.0})
    assert c.submitted == [("QQQ", "buy", 2.0)]
    cash0 = total_cash(d1, d2)
    c.fill("o1", 1, 505.0, status="partially_filled")                     # first look: 1 of 2 filled, still open
    b1, b2 = execute.reconcile(book(d1), c), execute.reconcile(book(d2), c)
    assert b1["holdings"] == {"QQQ": 2.0} and b1["cash"] == 3000 + 2 * 505 and b1["pending"] == []
    assert b2["holdings"] == {"QQQ": 3} and b2["cash"] == 10000 - 3 * 505 and len(b2["pending"]) == 1
    c.fill("o1", 1, 505.0, status="canceled")                             # then cancelled: remainder never fills
    b2 = execute.reconcile(b2, c)
    assert b2["holdings"] == {"QQQ": 3} and b2["pending"] == [] and b2["cash"] == 10000 - 3 * 505
    assert round(b1["cash"] + b2["cash"] - cash0, 2) == -505.0


def test_net_order_cancelled_unfilled_books_crossed_part_at_decision_close(desk, monkeypatch):
    d1 = slice_dir(desk, monkeypatch, "v1", *V1)
    d2 = slice_dir(desk, monkeypatch, "v2", *V2)
    c = Client(positions={"QQQ": 4})
    run_slices(c, {"QQQ": 4.0})
    c.fill("o1", 0, None, status="canceled")
    b1, b2 = execute.reconcile(book(d1), c), execute.reconcile(book(d2), c)
    assert b1["holdings"] == {"QQQ": 3.0} and b1["cash"] == 3500.0
    assert b2["holdings"] == {"QQQ": 1} and b2["cash"] == 9500.0 and b2["pending"] == []


def test_blocked_net_order_changes_no_book_and_alerts_high(desk, monkeypatch):
    d1 = slice_dir(desk, monkeypatch, "v1", *V1)
    d2 = slice_dir(desk, monkeypatch, "v2", *V2)
    before = {d: book(d) for d in (d1, d2)}
    desk.halt.write_text("stop")                                         # kill switch: net buy is risk-increasing
    c = Client(positions={"QQQ": 4})
    res, summary = run_slices(c, {"QQQ": 4.0})
    assert c.submitted == [] and summary["orders"] == ["blocked"]
    assert summary["blocked"] == ["Slices net: buy 1 QQQ (claude_sleeve sell 1, claude_sleeve_v2 buy 2)"]
    for d in (d1, d2):
        b = book(d)
        assert (b["cash"], b["holdings"], b["pending"]) == (before[d]["cash"], before[d]["holdings"], [])
    assert res["v2"]["orders"] == [("QQQ", "buy", 2, "netted_blocked")]
    sent = []
    monkeypatch.setattr(run_daily.alerts, "send", lambda *a, **k: sent.append(a))
    run_daily.heartbeat(summary)
    assert "1 order(s) BLOCKED" in sent[-1][0] and sent[-1][2] == "high" and "Slices net: buy 1 QQQ" in sent[-1][1]


def test_three_slices_on_one_symbol(desk, monkeypatch):
    d1 = slice_dir(desk, monkeypatch, "v1", {"cash": 1000.0, "holdings": {"QQQ": 4.0}}, {"QQQ": 10})   # value 3000: sell 4
    d2 = slice_dir(desk, monkeypatch, "v2", *V2)                                                   # buy 2
    d3 = slice_dir(desk, monkeypatch, "moby", {"cash": 10000.0, "holdings": {}}, {"QQQ": 20})       # buy 4
    c = Client(positions={"QQQ": 4})
    res, summary = run_slices(c, {"QQQ": 4.0}, keys=("v1", "v2", "moby"))
    assert c.submitted == [("QQQ", "buy", 2.0)] and summary["orders"] == ["submitted"]
    got = {e["strategy"]: (e["crossed_qty"], e["via_net_order_qty"]) for e in entries(desk, event="slice_intent")}
    assert got == {"claude_sleeve": (4, 0), "claude_sleeve_v2": (1, 1), "moby_sleeve": (3, 1)}   # 4 crossed, pro rata 2:4
    cash0 = total_cash(d1, d2, d3)
    c.fill("o1", 2, 502.0)
    bs = [execute.reconcile(book(d), c) for d in (d1, d2, d3)]
    assert [b["holdings"] for b in bs] == [{}, {"QQQ": 2}, {"QQQ": 4}]
    assert round(sum(b["cash"] for b in bs) - cash0, 2) == -2 * 502.0
    assert bs[0]["cash"] == 1000 + 4 * 502


def test_old_style_pending_entries_reconcile_exactly_as_before():
    b = {"cash": 10000.0, "holdings": {"XLE": 2}, "pending": [
        {"order_id": "a", "symbol": "QQQ", "side": "buy", "qty": 8},
        {"order_id": "b", "symbol": "GLD", "side": "buy", "qty": 12},
        {"order_id": "c", "symbol": "XLE", "side": "sell", "qty": 2},
        {"order_id": "d", "symbol": "TLT", "side": "buy", "qty": 10}], "history": []}
    c = Client()
    c.orders = {"a": SimpleNamespace(status="filled", filled_qty="8", filled_avg_price="501.25"),
                "b": SimpleNamespace(status="new", filled_qty="0", filled_avg_price=None),
                "c": SimpleNamespace(status="filled", filled_qty="2", filled_avg_price="90.5"),
                "d": SimpleNamespace(status="partially_filled", filled_qty="4", filled_avg_price="80")}
    out = execute.reconcile(b, c)
    assert out["holdings"] == {"QQQ": 8, "TLT": 4}
    assert out["cash"] == round(10000 - 8 * 501.25 + 2 * 90.5 - 4 * 80, 2)
    assert out["pending"] == [{"order_id": "b", "symbol": "GLD", "side": "buy", "qty": 12},
                              {"order_id": "d", "symbol": "TLT", "side": "buy", "qty": 6}]


def test_single_slice_symbols_unchanged_own_orders_and_old_pending(desk, monkeypatch):
    d1 = slice_dir(desk, monkeypatch, "v1", *V1)                                   # only v1 trades QQQ
    d2 = slice_dir(desk, monkeypatch, "v2", {"cash": 10000.0, "holdings": {}}, {"GLD": 10})   # only v2 trades GLD
    c = Client(positions={"QQQ": 4})
    res, summary = run_slices(c, {"QQQ": 4.0})
    assert c.submitted == [("QQQ", "sell", 1.0), ("GLD", "buy", 4.0)]
    assert summary["orders"] == ["submitted", "submitted"] and entries(desk, event="slice_intent") == []
    assert [e["strategy"] for e in entries(desk, decision="submitted")] == ["claude_sleeve", "claude_sleeve_v2"]
    assert book(d1)["pending"] == [{"order_id": "o1", "symbol": "QQQ", "side": "sell", "qty": 1}]
    assert book(d2)["pending"] == [{"order_id": "o2", "symbol": "GLD", "side": "buy", "qty": 4}]
    assert res["v1"] == {"status": "executed", "orders": [("QQQ", "sell", 1, "submitted")], "value": 5000.0}


def test_net_sell_never_exceeds_account_shares(desk, monkeypatch):
    """Books say v1 and v2 each hold 4 QQQ but the account has 5: v1 sells 4, v2's sell is capped at 1."""
    d1 = slice_dir(desk, monkeypatch, "v1", {"cash": 0.0, "holdings": {"QQQ": 4.0}}, {})
    d2 = slice_dir(desk, monkeypatch, "v2", {"cash": 0.0, "holdings": {"QQQ": 4.0}}, {})
    c = Client(positions={"QQQ": 5})
    run_slices(c, {"QQQ": 5.0})
    assert c.submitted == [("QQQ", "sell", 5.0)]
    assert any("sell capped" in a[0] for a in desk.alerts)


def test_allocate_is_whole_shares_and_deterministic():
    assert execute.allocate(3, [("a", 2), ("b", 4)]) == {"a": 1, "b": 2}
    assert execute.allocate(1, [("a", 1), ("b", 1)]) == {"a": 1, "b": 0}
    assert execute.allocate(0, [("a", 1)]) == {"a": 0}
    assert sum(execute.allocate(7, [("a", 3), ("b", 3), ("c", 3)]).values()) == 7
