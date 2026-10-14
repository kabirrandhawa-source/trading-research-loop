"""Backtester built to kill strategies, not flatter them.

    python backtest.py predict  --hypothesis 3 --strategy strategies/x_v1.py --from research/memo.md
    python backtest.py run      --hypothesis 3 --strategy strategies/x_v1.py --data data/SPY.csv
    python backtest.py sealed   --hypothesis 3 --strategy strategies/x_v1.py --data data/SPY.csv

Data CSVs need columns: timestamp, open, high, low, close, volume (daily bars, oldest first).
"""
import argparse
import hashlib
import importlib.util
import inspect
import json
import math
import os
import shutil
import stat
from datetime import date
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

import ledger
from strategies.base import Strategy

ROOT = Path(__file__).parent
RESULTS = ROOT / "backtests"
SEALED_PCT = 25.0        # legacy; the split is now by date (SEALED_START)
SEALED_START = "2024-01-30"   # first sealed day. Fixed, so daily data updates never move the boundary
COST_BPS = 5.0           # one-way cost per trade, basis points (commission + slippage)
PERIODS_PER_YEAR = 252
EULER_GAMMA = 0.5772156649


# ---------- loading ----------

def load_strategy(path):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if issubclass(c, Strategy) and c is not Strategy and c.__module__ == mod.__name__]
    if len(classes) != 1:
        raise ValueError(f"{path} must define exactly one Strategy subclass")
    return classes[0]


def load_prices(path):
    df = pd.read_csv(path, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    missing = {"open", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing columns {missing}")
    return df


def split(df, sealed_pct=None, sealed_start=None):
    """Return (development, sealed): everything before SEALED_START is development.
    The boundary is a fixed date, not a fraction of rows: a fraction would creep forward as the
    daily job appends prices, turning sealed days into development days. sealed_pct is ignored
    (kept so old command lines still work)."""
    start = pd.Timestamp(sealed_start or SEALED_START)
    tz = df["timestamp"].dt.tz
    start = start.tz_localize(tz) if tz is not None and start.tzinfo is None else start
    dev = df["timestamp"] < start
    return df[dev].reset_index(drop=True), df[~dev].reset_index(drop=True)


# ---------- engine ----------

def run(strategy, df, start=None, end=None, cost_bps=COST_BPS, delay=1, equity=100_000.0):
    """Bar-by-bar simulation. Decisions use bars[:t+1] only and fill at the open of bar t+delay.
    Trades only between start and end (indices); earlier bars are just indicator history."""
    start = max(start or 0, strategy.warmup)
    end = len(df) if end is None else end
    opens, closes = df["open"].to_numpy(float), df["close"].to_numpy(float)
    cost = cost_bps / 10_000
    cash, qty, pos = equity, 0, None
    curve, trades, pending = [], [], None

    for t in range(start, end):
        if pending and pending["at"] == t:          # execute delayed order at this bar's open
            px = opens[t]
            if pending["action"] == "open" and pos is None:
                n = strategy.size(cash, px)
                if n > 0:
                    qty = n * pending["side"]
                    cash -= qty * px + abs(qty) * px * cost
                    pos = {"side": pending["side"], "entry_price": px, "bars_held": 0, "entry_t": t}
            elif pending["action"] == "close" and pos is not None:
                cash += qty * px - abs(qty) * px * cost
                trades.append({"entry_t": pos["entry_t"], "exit_t": t,
                               "return": pos["side"] * (px / pos["entry_price"] - 1) - 2 * cost})
                qty, pos = 0, None
            pending = None

        curve.append(cash + qty * closes[t])
        if pending or t + delay >= end:
            continue
        bars = df.iloc[: t + 1]
        if pos is None:
            side = strategy.entry(bars)
            if side in (1, -1):
                pending = {"action": "open", "side": side, "at": t + delay}
        else:
            pos["bars_held"] += 1
            move = pos["side"] * (closes[t] / pos["entry_price"] - 1) * 100
            stop = strategy.stop_loss_pct is not None and move <= -strategy.stop_loss_pct
            target = strategy.take_profit_pct is not None and move >= strategy.take_profit_pct
            if stop or target or strategy.exit(bars, dict(pos)):
                pending = {"action": "close", "at": t + delay}

    if pos is not None and curve:                    # mark open position closed at the last close
        px = closes[end - 1]
        trades.append({"entry_t": pos["entry_t"], "exit_t": end - 1,
                       "return": pos["side"] * (px / pos["entry_price"] - 1) - 2 * cost})
        curve[-1] -= abs(qty) * px * cost
    return pd.Series(curve, dtype=float), trades


def metrics(curve, trades):
    rets = curve.pct_change().dropna()
    sd = rets.std(ddof=1) if len(rets) > 1 else 0.0
    sr = float(rets.mean() / sd) if sd > 0 else 0.0
    dd = float((curve / curve.cummax() - 1).min()) if len(curve) else 0.0
    wins = [t for t in trades if t["return"] > 0]
    return {
        "total_return_pct": round(float(curve.iloc[-1] / curve.iloc[0] - 1) * 100, 3) if len(curve) > 1 else 0.0,
        "max_drawdown_pct": round(dd * 100, 3),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else None,
        "n_trades": len(trades),
        "sharpe_annual": round(sr * math.sqrt(PERIODS_PER_YEAR), 3),
        "sharpe_per_period": sr,
        "skew": float(rets.skew()) if len(rets) > 2 else 0.0,
        "kurtosis": float(rets.kurt()) + 3 if len(rets) > 3 else 3.0,   # non-excess
        "n_obs": len(rets),
    }


# ---------- tests that try to kill it ----------

def walk_forward(strategy_cls, dev, n_folds=5, **kw):
    """Expanding train window, test on the next chunk, slide forward. Returns folds and the
    stitched out-of-sample equity curve."""
    edges = np.linspace(0, len(dev), n_folds + 2, dtype=int)
    folds, oos = [], []
    for k in range(n_folds):
        train_end, test_end = edges[k + 1], edges[k + 2]
        strat = strategy_cls()
        strat.fit(dev.iloc[:train_end].reset_index(drop=True))
        curve, trades = run(strat, dev, start=train_end, end=test_end, **kw)
        if len(curve) < 2:
            continue
        m = metrics(curve, trades)
        folds.append({"fold": k + 1, "test_from": str(dev["timestamp"].iloc[train_end]),
                      "test_to": str(dev["timestamp"].iloc[test_end - 1]), **m})
        oos.append(curve.pct_change().dropna())
    stitched = pd.concat(oos, ignore_index=True) if oos else pd.Series(dtype=float)
    return folds, stitched


def worst_periods(df, n=5, window=63):
    """The n worst non-overlapping `window`-bar stretches for the asset itself."""
    ret = df["close"].pct_change(window).shift(-window)
    order = ret.dropna().sort_values().index
    picked = []
    for i in order:
        if all(abs(i - j) >= window for j in picked):
            picked.append(i)
        if len(picked) == n:
            break
    return [(int(i), int(i + window)) for i in picked]


def stress(strategy_cls, dev, cost_bps=COST_BPS):
    out = {}
    for label, kw in {"2x_costs": {"cost_bps": 2 * cost_bps},
                      "delayed_fills": {"delay": 2},
                      "2x_costs_and_delayed": {"cost_bps": 2 * cost_bps, "delay": 2}}.items():
        out[label] = metrics(*run(strategy_cls(), dev, **kw))
    out["worst_periods"] = []
    for s, e in worst_periods(dev):
        m = metrics(*run(strategy_cls(), dev, start=s, end=e, cost_bps=2 * cost_bps, delay=2))
        out["worst_periods"].append({"from": str(dev["timestamp"].iloc[s]),
                                     "to": str(dev["timestamp"].iloc[e - 1]), **m})
    return out


def deflated_sharpe(sr, n_obs, skew, kurt, trial_srs):
    """Bailey & Lopez de Prado (2014). sr and trial_srs are per-period (not annualized).
    Probability the true Sharpe beats the best you'd expect from luck across len(trial_srs) tries."""
    n = len(trial_srs)
    nd = NormalDist()
    if n >= 2:
        var = float(np.var(trial_srs, ddof=1))
        sr0 = math.sqrt(var) * ((1 - EULER_GAMMA) * nd.inv_cdf(1 - 1 / n)
                                + EULER_GAMMA * nd.inv_cdf(1 - 1 / (n * math.e)))
    else:
        sr0 = 0.0
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if n_obs < 2 or denom <= 0:
        return {"dsr": None, "sr0": sr0, "n_trials": n}
    z = (sr - sr0) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return {"dsr": round(nd.cdf(z), 4), "sr0": sr0, "n_trials": n}


def classify_regime(df):
    """Rough label for the period: high_volatility, trending_up, trending_down, or choppy."""
    r = df["close"].pct_change().dropna()
    vol = r.std() * math.sqrt(PERIODS_PER_YEAR)
    total = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    years = max(len(df) / PERIODS_PER_YEAR, 1e-9)
    cagr = (1 + total) ** (1 / years) - 1 if total > -1 else -1
    if vol > 0.30:
        return "high_volatility"
    if cagr > 0.08:
        return "trending_up"
    if cagr < -0.08:
        return "trending_down"
    return "choppy"


# ---------- prediction lock ----------

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _check_owner(cls, hypothesis_id):
    if cls.HYPOTHESIS_ID is not None and cls.HYPOTHESIS_ID != hypothesis_id:
        raise PermissionError(f"{cls.NAME} v{cls.VERSION} belongs to hypothesis {cls.HYPOTHESIS_ID}, "
                              f"not {hypothesis_id}.")


def save_prediction(conn, hypothesis_id, strategy_path, source):
    """Lock a prediction for this exact strategy version. Each version gets its own."""
    cls = load_strategy(strategy_path)
    _check_owner(cls, hypothesis_id)
    dest = RESULTS / f"{Path(strategy_path).stem}-prediction.md"
    if dest.exists():
        raise PermissionError(f"{dest} already exists and cannot be replaced.")
    if ledger.get_prediction(conn, hypothesis_id, cls.VERSION):
        raise PermissionError(f"A prediction for version {cls.VERSION} is already locked.")
    shutil.copyfile(source, dest)
    os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)   # read-only
    ledger.set_prediction(conn, hypothesis_id, cls.VERSION, dest, _sha(dest))
    return dest


def verify_prediction(conn, hypothesis_id, strategy_version):
    pred = ledger.get_prediction(conn, hypothesis_id, strategy_version)
    if not pred:
        raise PermissionError(f"No saved prediction for version {strategy_version}. "
                              "Run `backtest.py predict` before any backtest.")
    if _sha(pred["path"]) != pred["sha256"]:
        raise PermissionError(f"{pred['path']} was edited after it was saved. Backtest refused.")
    return Path(pred["path"]).read_text()


def publication_split(cls, dev, published_date, **kw):
    """Did the effect survive its own publication? Compares the dev period before and after
    the paper first appeared. McLean & Pontiff (2016) find anomaly returns are about 26% lower
    out-of-sample and 58% lower after publication, so a big drop here is a strong warning."""
    if not published_date:
        return None
    pub = pd.Timestamp(published_date, tz=dev["timestamp"].dt.tz)
    cut = int((dev["timestamp"] < pub).sum())
    if cut < PERIODS_PER_YEAR or len(dev) - cut < PERIODS_PER_YEAR:
        return {"published_date": published_date,
                "note": "under 1 year of dev data on one side of publication; no comparison"}
    before = metrics(*run(cls(), dev, end=cut, **kw))
    after = metrics(*run(cls(), dev, start=cut, **kw))
    keep = ("total_return_pct", "sharpe_annual", "max_drawdown_pct", "n_trades", "win_rate_pct")
    return {"published_date": published_date,
            "before": {k: before[k] for k in keep}, "after": {k: after[k] for k in keep}}


# ---------- commands ----------

def _write(name, result, prediction):
    stamp = date.today().isoformat()
    jpath = RESULTS / f"{name}-{stamp}.json"
    jpath.write_text(json.dumps(result, indent=2, default=str))
    mpath = RESULTS / f"{name}-{stamp}.md"
    mpath.write_text(f"# {name} ({stamp})\n\n## Saved prediction (unedited)\n\n{prediction}\n\n"
                     f"## Results\n\n```json\n{json.dumps(result, indent=2, default=str)}\n```\n")
    return jpath, mpath


def cmd_run(conn, hid, strategy_path, data_path, sealed_pct):
    cls = load_strategy(strategy_path)
    _check_owner(cls, hid)
    prediction = verify_prediction(conn, hid, cls.VERSION)
    dev, _ = split(load_prices(data_path), sealed_pct)      # sealed part is discarded here
    folds, oos = walk_forward(cls, dev)
    wf_curve = (1 + oos).cumprod()
    oos_m = metrics(pd.concat([pd.Series([1.0]), wf_curve], ignore_index=True), [])
    trades = sum(f["n_trades"] for f in folds)
    wins = sum((f["win_rate_pct"] or 0) * f["n_trades"] / 100 for f in folds)
    oos_m.update(n_trades=trades, win_rate_pct=round(wins / trades * 100, 2) if trades else None)

    ledger.record_trial(conn, hid, cls.VERSION, oos_m["sharpe_per_period"], oos_m["n_obs"])
    dsr = deflated_sharpe(oos_m["sharpe_per_period"], oos_m["n_obs"], oos_m["skew"],
                          oos_m["kurtosis"], ledger.trial_sharpes(conn, hid))
    result = {"hypothesis_id": hid, "strategy": cls.NAME, "version": cls.VERSION,
              "dev_period": [str(dev["timestamp"].iloc[0]), str(dev["timestamp"].iloc[-1])],
              "sealed_pct": sealed_pct, "regime": classify_regime(dev),
              "walk_forward_oos": oos_m, "folds": folds, "stress": stress(cls, dev),
              "deflated_sharpe": dsr,
              "publication_split": publication_split(cls, dev, ledger.get(conn, hid)["published_date"])}
    ledger.update(conn, hid, strategy_file=str(strategy_path), strategy_version=cls.VERSION,
                  date_tested=date.today().isoformat(), regime=result["regime"],
                  backtest_result=json.dumps({"oos": oos_m, "dsr": dsr}))
    return _write(f"{Path(strategy_path).stem}", result, prediction)


def cmd_sealed(conn, hid, strategy_path, data_path, sealed_pct):
    cls = load_strategy(strategy_path)
    _check_owner(cls, hid)
    prediction = verify_prediction(conn, hid, cls.VERSION)
    df = load_prices(data_path)
    dev, sealed = split(df, sealed_pct)
    if ledger.get(conn, hid)["strategy_version"] != cls.VERSION:
        raise PermissionError("Sealed test must use the exact version that passed the dev backtest.")
    ledger.claim_sealed_test(conn, hid)                      # refuses a second run
    curve, trades = run(cls(), df, start=len(dev))           # history allowed for indicators only
    result = {"hypothesis_id": hid, "version": cls.VERSION, "sealed_period":
              [str(sealed["timestamp"].iloc[0]), str(sealed["timestamp"].iloc[-1])],
              "regime": classify_regime(sealed), **metrics(curve, trades)}
    ledger.record_sealed_result(conn, hid, result)
    return _write(f"{Path(strategy_path).stem}-SEALED", result, prediction)


def _main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["predict", "run", "sealed"])
    p.add_argument("--hypothesis", type=int, required=True)
    p.add_argument("--strategy", required=True)
    p.add_argument("--data")
    p.add_argument("--from", dest="source")
    p.add_argument("--sealed-pct", type=float, default=SEALED_PCT)
    a = p.parse_args()
    conn = ledger.connect()
    if a.cmd == "predict":
        print(save_prediction(conn, a.hypothesis, a.strategy, a.source))
    elif a.cmd == "run":
        print(*cmd_run(conn, a.hypothesis, a.strategy, a.data, a.sealed_pct), sep="\n")
    else:
        print(*cmd_sealed(conn, a.hypothesis, a.strategy, a.data, a.sealed_pct), sep="\n")


if __name__ == "__main__":
    _main()
