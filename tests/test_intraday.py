import lzma
import struct
from datetime import date

import pandas as pd
import pytest

from intraday import asian_breakout as ab
from intraday import data


def _day(moves, start="2023-06-05 00:00", spread=1.0):
    """5-minute London-time bars from 00:00. moves: list of (open, high, low, close) mid prices."""
    idx = pd.date_range(start, periods=len(moves), freq="5min", tz=ab.LONDON)
    df = pd.DataFrame(moves, index=idx, columns=["open", "high", "low", "close"])
    for k in ("open", "high", "low", "close"):
        df[f"bid_{k}"] = df[k] - spread / 2
        df[f"ask_{k}"] = df[k] + spread / 2
    return df


def _flat(n, px=100.0, wiggle=5.0):
    return [(px, px + wiggle, px - wiggle, px)] * n


def test_long_breakout_hits_target():
    # 00:00-08:00 inside a 95-105 box, then a strong 15-min candle closing at 112 (low 104).
    bars = _flat(96) + [(104, 106, 104, 106), (106, 109, 105.5, 109), (109, 112, 108.5, 112)] + \
           [(112, 112.5, 111.5, 112)] + [(112, 140, 111, 139)] + _flat(20, 139, 1)
    tr = ab.day_trade(_day(bars), "DAX", ab.PARAMS_V1)
    assert isinstance(tr, dict) and tr["side"] == 1 and tr["reason"] == "target"
    assert tr["stop"] == 104
    assert tr["entry"] == pytest.approx(112 + 0.5 + 0.5)          # ask + slippage
    assert tr["r"] == pytest.approx(2 - 0.5 / tr["risk_pts"], rel=1e-6)


def test_stop_assumed_first_when_both_in_one_bar():
    bars = _flat(96) + [(104, 106, 104, 106), (106, 109, 105.5, 109), (109, 112, 108.5, 112)] + \
           [(112, 150, 90, 112)] + _flat(20, 112, 1)
    tr = ab.day_trade(_day(bars), "DAX", ab.PARAMS_V1)
    assert tr["reason"] == "stop" and tr["r"] < -1


def test_no_signal_inside_box_and_weak_candle_ignored():
    assert ab.day_trade(_day(_flat(200)), "DAX", ab.PARAMS_V1) == "no_signal"
    # Closes above the box but body is tiny relative to range: not a "strong" candle.
    bars = _flat(96) + [(105, 120, 100, 105.5), (105.5, 106, 105, 105.6), (105.6, 106, 105.4, 105.7)] + _flat(100)
    assert ab.day_trade(_day(bars), "DAX", ab.PARAMS_V1) == "no_signal"


def test_short_breakout_and_time_exit():
    bars = _flat(96) + [(96, 96, 94, 94), (94, 94, 90.5, 91), (91, 91.5, 88, 88)] + _flat(150, 87, 0.5)
    tr = ab.day_trade(_day(bars), "DAX", ab.PARAMS_V1)
    assert tr["side"] == -1 and tr["reason"] == "time" and tr["stop"] == 96


def test_asian_gaps_skipped():
    bars = _day(_flat(200)).iloc[60:]          # missing 00:00-05:00
    assert ab.day_trade(bars, "DAX", ab.PARAMS_V1) == "asia_gaps"


def test_sealed_days_never_downloaded():
    with pytest.raises(ValueError, match="sealed"):
        data.fetch_day(None, "DAX", date(2024, 1, 30))


def test_decode_and_5min():
    raw = b"".join(struct.pack(">5If", s, 100_000, 101_000, 99_000, 102_000, 1.0) for s in (0, 60, 300))
    raw += struct.pack(">5If", 360, 1, 1, 1, 1, 0.0)            # zero volume: dropped
    rows = data.decode(lzma.compress(raw, format=lzma.FORMAT_ALONE), date(2023, 1, 2))
    assert len(rows) == 3 and rows[0][1:5] == (100.0, 102.0, 99.0, 101.0)
    bars = data.to_5min(rows, rows)
    assert [b[0] for b in bars] == ["2023-01-02T00:00:00Z", "2023-01-02T00:05:00Z"]
