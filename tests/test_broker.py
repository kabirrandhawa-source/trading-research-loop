import json
from types import SimpleNamespace

import pytest

import broker


class FakeClient:
    def __init__(self, equity=100_000, last=100_000, positions=None):
        self.acct = SimpleNamespace(equity=str(equity), last_equity=str(last))
        self.positions = [SimpleNamespace(symbol=s, qty=str(q)) for s, q in (positions or {}).items()]
        self.submitted = []

    def get_account(self): return self.acct
    def get_all_positions(self): return self.positions
    def submit_order(self, req):
        self.submitted.append(req); return SimpleNamespace(id="abc")


@pytest.fixture
def env(tmp_path, monkeypatch):
    import risk
    lim = tmp_path / "risk.json"
    lim.write_text(json.dumps({"max_daily_loss_pct": 2, "max_drawdown_pct": 8,
                               "max_position_pct": 10, "max_open_positions": 5}))
    monkeypatch.setattr(risk, "LIMITS_PATH", lim)
    monkeypatch.setattr(risk, "HALT_PATH", tmp_path / "HALT")
    return {"peak_path": tmp_path / "peak.json", "journal_dir": tmp_path}


def submit(client, env, qty, side="buy", price=100.0):
    return broker.submit("s", "1", "SPY", side, qty, {"vix": 15}, "test", client=client,
                         price_fn=lambda s: price, **env)


def test_oversized_order_never_reaches_broker(env):
    c = FakeClient()
    rec = submit(c, env, qty=200)          # $20k > 10% of $100k
    assert rec["decision"] == "blocked" and c.submitted == []
    logged = json.loads(next(env["journal_dir"].glob("*.jsonl")).read_text().splitlines()[-1])
    assert logged["decision"] == "blocked" and logged["reasoning"] == "test"


def test_allowed_order_is_submitted_and_journaled(env):
    c = FakeClient()
    rec = submit(c, env, qty=50)
    assert rec["decision"] == "submitted" and len(c.submitted) == 1


def test_daily_loss_blocks_new_but_allows_exit(env):
    c = FakeClient(equity=97_000, last=100_000, positions={"SPY": 10})
    assert submit(c, env, qty=5)["decision"] == "blocked"
    assert submit(c, env, qty=10, side="sell")["decision"] == "submitted"


def test_oversized_sell_is_not_treated_as_exit(env):
    c = FakeClient(equity=97_000, last=100_000, positions={"SPY": 10})
    assert submit(c, env, qty=11, side="sell")["decision"] == "blocked"


def test_drawdown_tracked_from_peak(env):
    submit(FakeClient(equity=100_000), env, qty=1)
    rec = submit(FakeClient(equity=91_000, last=91_000), env, qty=1)
    assert rec["decision"] == "blocked" and "drawdown" in rec["risk_check"].lower()


def test_check_error_blocks(env):
    c = FakeClient()
    rec = broker.submit("s", "1", "SPY", "buy", 1, {}, "x", client=c,
                        price_fn=lambda s: (_ for _ in ()).throw(RuntimeError("feed down")), **env)
    assert rec["decision"] == "blocked" and c.submitted == []


def test_live_mode_refused(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "false")
    with pytest.raises(RuntimeError, match="Live trading"):
        broker.paper_client()


def test_paper_client_points_at_paper(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "true")
    monkeypatch.setenv("ALPACA_API_KEY", "PKTEST")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    c = broker.paper_client()             # no network call on construction
    assert broker.PAPER_HOST in str(getattr(c._base_url, "value", c._base_url))
