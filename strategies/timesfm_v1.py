"""TimesFM 3.0 next-day forecast, long-or-flat (hypothesis 6).

Forecasts come from tsfm/forecast_dev.py: for each day t, TimesFM saw only the 512 closes ending at t.
Long when the forecast close for t+1 is above today's close; flat otherwise. Fills at the next open.
"""
import math
from pathlib import Path

import pandas as pd

from strategies.base import Strategy

FORECASTS = Path(__file__).resolve().parent.parent / "data" / "tsfm" / "forecasts_dev.csv"


class TimesFMLongFlat(Strategy):
    NAME = "timesfm"
    VERSION = "1"
    HYPOTHESIS = "TimesFM 3.0 next-day forecasts: long when up, flat when down, beats buy-and-hold after costs."
    HYPOTHESIS_ID = 6
    SYMBOL = "SPY"
    stop_loss_pct = None          # the rule itself is the exit; no stop
    take_profit_pct = None
    max_position_pct = 10.0
    _signal = None

    @classmethod
    def signals(cls):
        if cls._signal is None:
            f = pd.read_csv(FORECASTS, parse_dates=["timestamp"])
            f = f[f.symbol == cls.SYMBOL]
            cls._signal = dict(zip(f.timestamp, f.fc - f.close.map(math.log)))
        return cls._signal

    def expected_return(self, bars):
        return self.signals().get(bars["timestamp"].iloc[-1])

    def entry(self, bars):
        s = self.expected_return(bars)
        return 1 if s is not None and s > 0 else 0

    def exit(self, bars, position):
        s = self.expected_return(bars)
        return s is None or s <= 0
