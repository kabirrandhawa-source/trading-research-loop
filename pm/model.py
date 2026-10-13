"""Fair value for Kalshi's 15-minute Bitcoin up/down market, and its fees.

The market resolves YES if the average of the CF Benchmarks BRTI over the 60 seconds before close
is at least the strike (the same 60-second average before open). Treat Bitcoin as a random walk
with per-second volatility sigma. With tau seconds to close:

  tau >= 60: the settlement average X has mean S and variance S^2 sigma^2 (tau - 60 + 60/3)
             (the walk until the averaging window starts, plus an average over 60 seconds,
             which has 1/3 the variance of the endpoint)
  tau <  60: part of the average is already known. X = ((60 - tau) * A_known + tau * future_avg) / 60,
             where future_avg has mean S and variance S^2 sigma^2 tau / 3.

P(YES) = Phi((mean - K) / sd). This is deliberately simple; it is the yardstick for testing whether
the market's odds lag the spot price, not a claim that this is the true probability.
"""
import math
from statistics import NormalDist

import numpy as np
import pandas as pd

WINDOW = 60.0
_N = NormalDist()


def fair_prob(spot, strike, tau, sigma, known_avg=None):
    """P(settlement average >= strike). sigma is per-second log-return volatility."""
    if tau <= 0:
        return 1.0 if (known_avg if known_avg is not None else spot) >= strike else 0.0
    if tau >= WINDOW:
        mean, var = spot, spot ** 2 * sigma ** 2 * (tau - WINDOW + WINDOW / 3)
    else:
        known = known_avg if known_avg is not None else spot
        mean = ((WINDOW - tau) * known + tau * spot) / WINDOW
        var = (tau / WINDOW) ** 2 * spot ** 2 * sigma ** 2 * tau / 3
    sd = math.sqrt(max(var, 1e-12))
    return min(max(_N.cdf((mean - strike) / sd), 0.0), 1.0)


def taker_fee(price, contracts=100, multiplier=1.0):
    """Kalshi quadratic taker fee: round-up(0.07 * C * P * (1 - P)) to the cent, per order.
    Returns the fee per contract. Source: Kalshi fee schedule (Feb 2026); KXBTC15M reports
    fee_type=quadratic, fee_multiplier=1. Re-check before trusting results."""
    total = 0.07 * multiplier * contracts * price * (1 - price)
    return math.ceil(round(total * 100, 6)) / 100 / contracts


def maker_fee(price, contracts=100, rate=0.0):
    """Maker fee per contract. Kalshi's schedule lists 0.0175 for series with maker fees; this
    series appears to have none (rate=0). Pass rate=0.0175 to test the pessimistic case."""
    if rate <= 0:
        return 0.0
    total = rate * contracts * price * (1 - price)
    return math.ceil(round(total * 100, 6)) / 100 / contracts


def spot_series(trades, start, end, freq_s=1):
    """Last-trade price on a regular grid (epoch seconds) from (ts, price) rows, forward-filled."""
    df = pd.DataFrame(trades, columns=["ts", "price"]).sort_values("ts")
    grid = np.arange(math.floor(start), math.ceil(end) + 1, freq_s, dtype=float)
    idx = np.searchsorted(df["ts"].to_numpy(), grid, side="right") - 1
    prices = np.where(idx >= 0, df["price"].to_numpy()[np.clip(idx, 0, None)], np.nan)
    return pd.Series(prices, index=grid)


def realized_sigma(series, lookback_s=1800):
    """Per-second volatility from 1-second log returns over a trailing window (no look-ahead)."""
    r = np.log(series).diff()
    return r.rolling(int(lookback_s), min_periods=int(lookback_s * 0.5)).std()
