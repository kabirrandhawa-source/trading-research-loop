from risk import check_order

LIMITS = {"max_daily_loss_pct": 2.0, "max_drawdown_pct": 8.0,
          "max_position_pct": 10.0, "max_open_positions": 5}
OK_ACCT = {"equity": 100_000, "daily_loss_pct": 0.0, "drawdown_pct": 0.0, "open_positions": 0}


def chk(order, acct=OK_ACCT, halt=None, tmp_path=None):
    return check_order(order, acct, LIMITS, halt_path=halt or "/nonexistent/HALT")


def test_ok():
    assert chk({"value": 9_000})[0]


def test_daily_loss_blocks():
    assert not chk({"value": 1_000}, {**OK_ACCT, "daily_loss_pct": 2.0})[0]


def test_drawdown_blocks():
    assert not chk({"value": 1_000}, {**OK_ACCT, "drawdown_pct": 8.5})[0]


def test_position_size_uses_percent():
    assert chk({"value": 10_000})[0]
    assert not chk({"value": 10_001})[0]


def test_open_positions_blocks():
    assert not chk({"value": 1_000}, {**OK_ACCT, "open_positions": 5})[0]


def test_fails_closed_on_bad_data():
    assert not chk({"value": float("nan")})[0]
    assert not chk({"value": 1_000}, {"equity": 100_000})[0]
    assert not chk({})[0]
    assert not chk({"value": -5})[0]


def test_missing_limits_file_blocks(tmp_path):
    import risk
    orig = risk.LIMITS_PATH
    risk.LIMITS_PATH = tmp_path / "missing.json"
    try:
        assert not risk.check_order({"value": 1}, OK_ACCT, halt_path="/nonexistent")[0]
    finally:
        risk.LIMITS_PATH = orig


def test_halt_file_blocks(tmp_path):
    halt = tmp_path / "HALT"; halt.touch()
    assert not chk({"value": 1_000}, halt=halt)[0]


def test_reducing_position_allowed_even_after_limit():
    acct = {**OK_ACCT, "daily_loss_pct": 5.0, "drawdown_pct": 20.0, "open_positions": 9}
    assert chk({"value": 50_000, "reduces_position": True}, acct)[0]
