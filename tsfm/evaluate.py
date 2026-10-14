"""Score TimesFM forecasts on development data (hypothesis 6). Main environment:
    .venv/bin/python -m tsfm.evaluate
Only uses data/tsfm/forecasts_dev.csv (all before backtest.SEALED_START). The next-day return for
each forecast comes from the next development row, so the last development day is dropped rather
than reaching into the sealed period.
"""
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import backtest
from strategies.base import Strategy

ROOT = Path(__file__).resolve().parent.parent
FORECASTS = ROOT / "data" / "tsfm" / "forecasts_dev.csv"


def frame(path=FORECASTS):
    f = pd.read_csv(path, parse_dates=["timestamp"]).sort_values(["symbol", "timestamp"])
    f["lc"] = np.log(f.close)
    f["signal"] = f.fc - f.lc                                      # forecast log return for t+1
    g = f.groupby("symbol")
    f["ret_next"] = g.lc.shift(-1) - f.lc                           # realized t -> t+1 (dev rows only)
    f["ret_prev"] = f.lc - g.lc.shift(1)                            # t-1 -> t, for the echo check
    f["in_band"] = (g.lc.shift(-1) >= f.q10) & (g.lc.shift(-1) <= f.q90)
    return f.dropna(subset=["ret_next", "ret_prev"])


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else 0.0


def score(f):
    daily_ic = f.groupby("timestamp").apply(lambda d: d.signal.rank().corr(d.ret_next.rank()) if len(d) >= 5 else np.nan).dropna()
    per_etf = f.groupby("symbol").apply(lambda d: d.signal.corr(d.ret_next))
    hit = (np.sign(f.signal) == np.sign(f.ret_next)).mean()
    up_days = (f.ret_next > 0).mean()                               # hit rate of always guessing "up"
    n = len(f)
    return {
        "forecasts_scored": n, "days": int(f.timestamp.nunique()),
        "cross_sectional_ic_mean": round(float(daily_ic.mean()), 4), "cross_sectional_ic_t": round(tstat(daily_ic), 2),
        "time_series_ic_by_etf": {k: round(float(v), 4) for k, v in per_etf.items()},
        "time_series_ic_mean": round(float(per_etf.mean()), 4),
        "hit_rate": round(float(hit), 4), "always_up_hit_rate": round(float(up_days), 4),
        "hit_rate_edge_z": round(float((hit - up_days) / math.sqrt(up_days * (1 - up_days) / n)), 2),
        "share_of_forecasts_up": round(float((f.signal > 0).mean()), 4),
        "echo_corr_with_yesterdays_move": round(float(f.signal.corr(f.ret_prev)), 4),
        "band_80pct_coverage": round(float(f.in_band.mean()), 4),
    }


class _BuyHold(Strategy):
    NAME, VERSION = "buy_and_hold", "benchmark"
    stop_loss_pct = None
    def entry(self, bars): return 1


def benchmark_spy():
    """Buy-and-hold SPY through the same walk-forward folds, sizing and costs as the strategy."""
    dev, _ = backtest.split(backtest.load_prices(ROOT / "data" / "SPY.csv"))
    folds, oos = backtest.walk_forward(_BuyHold, dev)
    curve = pd.concat([pd.Series([1.0]), (1 + oos).cumprod()], ignore_index=True)
    m = backtest.metrics(curve, [])
    return {k: m[k] for k in ("total_return_pct", "max_drawdown_pct", "sharpe_annual")}


def main():
    result = {"signal": score(frame()), "spy_buy_and_hold_walk_forward": benchmark_spy()}
    out = ROOT / "backtests" / f"timesfm_v1-signal-{date.today().isoformat()}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(out)


if __name__ == "__main__":
    main()
