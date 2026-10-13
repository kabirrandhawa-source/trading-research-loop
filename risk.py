"""Kill switch. Runs before every order. Lives in code so no prompt can talk past it.

All limits in config/risk.json are percentages (2.0 means 2%).
Touch config/HALT to block every new risk-increasing order immediately.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).parent
LIMITS_PATH = ROOT / "config" / "risk.json"
HALT_PATH = ROOT / "config" / "HALT"
REQUIRED = ("max_daily_loss_pct", "max_drawdown_pct", "max_position_pct", "max_open_positions")


def load_limits(path=None):
    limits = json.loads(Path(path or LIMITS_PATH).read_text())
    missing = [k for k in REQUIRED if k not in limits]
    if missing:
        raise ValueError(f"config/risk.json is missing {missing}")
    return limits


def _num(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def check_order(order, account, limits=None, halt_path=None):
    """Return (allowed, reason). Fails closed on any bad or missing input.

    order:   {"value": float, "reduces_position": bool}
    account: {"equity", "daily_loss_pct", "drawdown_pct", "open_positions"}

    Orders that only shrink an existing position are always allowed, so the system
    can still get out after a limit is hit. The broker works out reduces_position
    from actual positions; it never trusts the caller for that.
    """
    try:
        limits = limits or load_limits()
    except Exception as e:
        return False, f"Could not load risk limits ({e}). Trading stopped."

    if order.get("reduces_position") is True:
        return True, "OK (reduces an existing position)"

    if Path(halt_path or HALT_PATH).exists():
        return False, "Manual HALT file present. Trading stopped."

    fields = [account.get(k) for k in ("equity", "daily_loss_pct", "drawdown_pct", "open_positions")]
    if not all(_num(f) for f in fields) or not _num(order.get("value")):
        return False, "Missing or invalid account/order data. Order blocked."
    if order["value"] <= 0 or account["equity"] <= 0:
        return False, "Non-positive order value or equity. Order blocked."

    if account["daily_loss_pct"] >= limits["max_daily_loss_pct"]:
        return False, "Daily loss limit hit. Trading stopped."
    if account["drawdown_pct"] >= limits["max_drawdown_pct"]:
        return False, "Max drawdown hit. Trading stopped."
    if order["value"] > account["equity"] * limits["max_position_pct"] / 100:
        return False, "Order is larger than the position limit."
    if account["open_positions"] >= limits["max_open_positions"]:
        return False, "Too many open positions."
    return True, "OK"
