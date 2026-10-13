import pandas as pd

from backtest import run
from strategies.spy_prefomc_v1 import FOMC_DATES, SpyPreFomc, weekdays_to_next_fomc


def frame(start, end, price=100.0):
    ts = pd.bdate_range(start, end)
    return pd.DataFrame({"timestamp": ts, "open": price, "high": price, "low": price,
                         "close": price, "volume": 1})


def test_dates_sorted_unique_and_wednesday_or_thursday():
    assert FOMC_DATES == sorted(set(FOMC_DATES))
    assert all(d.weekday() in (2, 3) for d in FOMC_DATES)   # Wed (Thu for election-week 2018/2020/2024)


def test_weekday_distance():
    assert weekdays_to_next_fomc(pd.Timestamp("2016-01-27").date()) == 0
    assert weekdays_to_next_fomc(pd.Timestamp("2016-01-26").date()) == 1
    assert weekdays_to_next_fomc(pd.Timestamp("2016-01-25").date()) == 2
    assert weekdays_to_next_fomc(pd.Timestamp("2016-01-22").date()) == 3


def test_entry_only_on_t_minus_2():
    s = SpyPreFomc()
    bars = frame("2016-01-18", "2016-01-29")
    fired = [str(bars["timestamp"].iloc[i].date()) for i in range(len(bars))
             if s.entry(bars.iloc[: i + 1]) == 1]
    assert fired == ["2016-01-25"]


def test_exit_on_fomc_day_and_not_before():
    s = SpyPreFomc()
    bars = frame("2016-01-18", "2016-01-29")
    upto = lambda d: bars[bars["timestamp"] <= d]
    pos = {"side": 1, "entry_price": 100.0, "bars_held": 1}
    assert not s.exit(upto("2016-01-26"), pos)
    assert s.exit(upto("2016-01-27"), pos)


def test_exit_safety_cap():
    s = SpyPreFomc()
    bars = frame("2016-02-08", "2016-02-10")
    assert s.exit(bars, {"side": 1, "entry_price": 100.0, "bars_held": 3})


def test_engine_holds_open_t_minus_1_to_open_t_plus_1():
    bars = frame("2016-01-18", "2016-01-29")
    _, trades = run(SpyPreFomc(), bars)
    assert len(trades) == 1
    t = trades[0]
    assert str(bars["timestamp"].iloc[t["entry_t"]].date()) == "2016-01-26"
    assert str(bars["timestamp"].iloc[t["exit_t"]].date()) == "2016-01-28"


def test_flat_with_no_fomc_nearby():
    bars = frame("2016-02-08", "2016-02-26")
    _, trades = run(SpyPreFomc(), bars)
    assert trades == []
