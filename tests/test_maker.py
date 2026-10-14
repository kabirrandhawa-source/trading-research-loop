import pytest

from pm import maker
from pm.maker import Leg, Order, fill, simulate_window


def test_queue_must_trade_before_we_fill():
    o, leg = Order("yes", .40, 10, ahead=25), Leg()
    fill(o, .40, 20, leg); assert leg.qty == 0 and o.ahead == 5
    fill(o, .40, 12, leg); assert leg.qty == 7 and o.qty == 3     # 5 ahead traded, then 7 of ours
    fill(o, .39, 1, leg);  assert leg.qty == 10 and o.qty == 0    # traded through: rest filled
    fill(o, .41, 50, leg); assert leg.qty == 10                    # trades above our bid never fill us


def book(ts, yb, ya, size=5):
    return (ts, yb, size, ya, size)


def test_matched_pair_earns_the_margin_whoever_wins():
    tob = [book(0, .45, .50)]                                      # YES bid .45, NO bid .50: pair costs .95
    trades = [(70, .45, 15, "no"), (75, .50, 15, "yes")]         # 5 ahead on each side, then ours fill
    for result in ("yes", "no"):
        r = simulate_window("W", 0, 900, result, tob, trades)
        assert r.yes.qty == 10 and r.no.qty == 10
        assert r.pnl() == pytest.approx(10 * (1 - .95))


def test_one_sided_fill_rides_to_settlement():
    tob = [book(0, .45, .50)]
    trades = [(70, .40, 30, "no")]                                 # price falls through our YES bid; NO never fills
    r = simulate_window("W", 0, 900, "no", tob, trades)
    assert r.yes.qty == 10 and r.no.qty == 0
    assert r.pnl() == pytest.approx(-4.5)                          # bought 10 YES at .45, YES lost


def test_no_quotes_when_the_pair_would_cost_more_than_98c():
    tob = [book(0, .49, .50)]                                      # .49 + .50 = .99 > .98
    r = simulate_window("W", 0, 900, "yes", tob, [(70, .40, 50, "no"), (71, .60, 50, "yes")])
    assert r.yes.qty == 0 and r.no.qty == 0


def test_filled_side_is_never_chased_and_orders_stop_before_close():
    tob = [book(0, .45, .50), book(100, .30, .35)]                 # book moves after YES filled
    trades = [(70, .44, 30, "no"), (880, .35, 999, "yes")]       # NO trades only after close-180: too late
    r = simulate_window("W", 0, 900, "yes", tob, trades)
    assert r.yes.qty == 10 and r.no.qty == 0


def test_pessimistic_fee_reduces_pnl():
    tob = [book(0, .45, .50)]
    trades = [(70, .45, 15, "no"), (75, .50, 15, "yes")]
    r = simulate_window("W", 0, 900, "yes", tob, trades)
    assert r.pnl(0.0175) < r.pnl(0.0)
