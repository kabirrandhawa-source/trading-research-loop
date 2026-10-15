"""Asian-range breakout on DAX and UK100 CFDs (hypothesis registered in the ledger; version v1).

Rules, from a social-media post Kabir brought in, with the vague parts fixed BEFORE any test:
- Box: high and low of 00:00-07:00 London time (mid prices, 5-minute bars).
- Signal: the first 15-minute bar starting 08:00-09:45 London whose CLOSE is outside the box and
  whose body is at least half its range ("a clean, strong candle"). Direction = side it broke.
- Entry: open of the next 5-minute bar, buying at the ask / selling at the bid, plus slippage.
- Stop: the far end of the breakout candle (its low for a long, high for a short).
- Target: 2R. Anything still open at 16:30 London is closed. One trade per index per day.
- Fills: exits are checked on 5-minute bid/ask bars; when stop and target are both inside one bar,
  the stop is assumed to have hit first.
- Skip days whose Asian window is missing more than 20% of its 5-minute bars (the feed has gaps).

Result unit: R per trade (profit divided by the planned risk). Fixed 1% risk sizing turns that
into account returns: 1R = 1% of equity.

    .venv/bin/python -m intraday.asian_breakout run --version v1
"""
import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from intraday import data

ROOT = Path(__file__).resolve().parent.parent
LONDON = "Europe/London"
SLIPPAGE = {"DAX": 0.5, "UK100": 0.5}     # index points per side, on top of the quoted spread

PARAMS_V1 = dict(asia=("00:00", "07:00"), watch=("08:00", "10:00"), signal_tf="15min",
                 min_body=0.5, target_r=2.0, flat_at="16:30", min_coverage=0.8)


def days(df):
    """Group 5-minute bars by London calendar day."""
    local = df.tz_convert(LONDON)
    return local.groupby(local.index.date)


def day_trade(bars, name, p):
    """One London day of 5-minute bars (London-time index) -> trade dict, or None, or a skip reason."""
    t = bars.index.strftime("%H:%M")
    asia = bars[(t >= p["asia"][0]) & (t < p["asia"][1])]
    a0, a1 = (pd.Timestamp(f"2000-01-01 {x}") for x in p["asia"])
    expected = (a1 - a0) / pd.Timedelta("5min")
    if len(asia) < p["min_coverage"] * expected:
        return "asia_gaps"
    hi, lo = asia["high"].max(), asia["low"].min()
    if not hi > lo:
        return "flat_box"

    watch = bars[(t >= p["watch"][0]) & (t < p["watch"][1])]
    if watch.empty:
        return "no_session"
    agg = watch.resample(p["signal_tf"], label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    for start, c in agg.iterrows():
        rng = c["high"] - c["low"]
        if rng <= 0 or abs(c["close"] - c["open"]) < p["min_body"] * rng:
            continue
        side = 1 if c["close"] > hi else -1 if c["close"] < lo else 0
        if side == 0 or (side == 1 and c["close"] < c["open"]) or (side == -1 and c["close"] > c["open"]):
            continue
        signal_end = start + pd.Timedelta(p["signal_tf"])
        return _simulate(bars, signal_end, side, c, name, p, hi, lo)
    return "no_signal"


def _simulate(bars, after, side, candle, name, p, box_hi, box_lo):
    t = bars.index.strftime("%H:%M")
    rest = bars[(bars.index >= after) & (t < p["flat_at"])]
    if rest.empty:
        return "no_bars_after_signal"
    slip = SLIPPAGE[name]
    first = rest.iloc[0]
    entry = (first["ask_open"] + slip) if side == 1 else (first["bid_open"] - slip)
    stop = candle["low"] if side == 1 else candle["high"]
    risk = (entry - stop) * side
    if risk <= 0:
        return "entry_beyond_stop"
    target = entry + side * p["target_r"] * risk
    exit_px, why, when = None, None, None
    for ts, b in rest.iterrows():
        # A long is closed at the bid, a short at the ask.
        lo_, hi_ = (b["bid_low"], b["bid_high"]) if side == 1 else (b["ask_low"], b["ask_high"])
        hit_stop = lo_ <= stop if side == 1 else hi_ >= stop
        hit_tgt = hi_ >= target if side == 1 else lo_ <= target
        if hit_stop:
            gap = b["bid_open"] if side == 1 else b["ask_open"]       # a gap through the stop fills worse
            exit_px = min(stop, gap) if side == 1 else max(stop, gap)
            why, when = "stop", ts
            break
        if hit_tgt:
            exit_px, why, when = target, "target", ts
            break
    if exit_px is None:
        last = rest.iloc[-1]
        exit_px, why, when = (last["bid_close"] if side == 1 else last["ask_close"]), "time", rest.index[-1]
    exit_px -= side * slip
    return {"symbol": name, "day": str(rest.index[0].date()), "side": side, "entry": entry,
            "stop": stop, "target": target, "exit": exit_px, "reason": why, "exit_time": str(when),
            "risk_pts": risk, "r": (exit_px - entry) * side / risk,
            "box_hi": box_hi, "box_lo": box_lo, "spread_at_entry": first["ask_open"] - first["bid_open"]}


def backtest(df, name, p=PARAMS_V1):
    trades, skips = [], {}
    for _, bars in days(df):
        res = day_trade(bars, name, p)
        if isinstance(res, dict):
            trades.append(res)
        else:
            skips[res] = skips.get(res, 0) + 1
    return pd.DataFrame(trades), skips


def summary(tr):
    if tr.empty:
        return {"trades": 0}
    r = tr["r"].to_numpy()
    sd = r.std(ddof=1) if len(r) > 1 else float("nan")
    eq = np.cumsum(r)                       # in R; 1R = 1% of equity at fixed-fractional risk
    dd = (eq - np.maximum.accumulate(np.concatenate([[0], eq]))[1:]).min()
    losing = max((len(list(g)) for k, g in __import__("itertools").groupby(r < 0) if k), default=0)
    return {"trades": int(len(r)), "mean_r": float(r.mean()), "t_stat": float(r.mean() / sd * math.sqrt(len(r))),
            "win_rate": float((r > 0).mean()), "total_r": float(r.sum()), "max_drawdown_r": float(dd),
            "longest_losing_streak": int(losing),
            "exits": tr["reason"].value_counts().to_dict(),
            "sharpe_per_trade": float(r.mean() / sd)}


def by_year(tr):
    tr = tr.assign(year=tr["day"].str[:4])
    return {y: {"trades": int(len(g)), "mean_r": round(float(g["r"].mean()), 3), "total_r": round(float(g["r"].sum()), 1)}
            for y, g in tr.groupby("year")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--version", default="v1")
    ap.add_argument("--hypothesis", type=int, required=True)
    a = ap.parse_args()
    import ledger
    lconn = ledger.connect()
    if not ledger.get_prediction(lconn, a.hypothesis, a.version):
        raise SystemExit(f"No locked prediction for hypothesis {a.hypothesis} {a.version}; write it first.")
    conn = data.connect()
    out, all_trades = {"version": a.version, "params": PARAMS_V1, "slippage_pts": SLIPPAGE,
                       "sealed_start": data.sealed_start().isoformat(), "symbols": {}}, []
    for name in data.SYMBOLS:
        df = data.load(name, conn)
        tr, skips = backtest(df, name)
        out["symbols"][name] = {"summary": summary(tr), "by_year": by_year(tr) if len(tr) else {},
                                "skipped_days": skips, "first_day": str(df.index[0].date()),
                                "last_day": str(df.index[-1].date()),
                                "median_spread_at_entry": float(tr["spread_at_entry"].median()) if len(tr) else None}
        all_trades.append(tr)
    pooled = pd.concat(all_trades, ignore_index=True)
    out["pooled"] = {"summary": summary(pooled), "by_year": by_year(pooled)}
    ledger.record_trial(lconn, a.hypothesis, a.version, out["pooled"]["summary"]["sharpe_per_trade"],
                        out["pooled"]["summary"]["trades"])
    stem = ROOT / "backtests" / f"asian_breakout_{a.version}-{date.today().isoformat()}"
    stem.with_suffix(".json").write_text(json.dumps(out, indent=2, default=str))
    pooled.to_csv(ROOT / "data" / "intraday" / f"trades_{a.version}.csv", index=False)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
