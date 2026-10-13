"""Does Kalshi's 15-minute Bitcoin market lag the spot price? (Ledger hypothesis 4.)

    python -m pm.analyze lag          # second-level lead/lag: market trades vs spot-implied odds
    python -m pm.analyze calibration  # minute-level: market odds vs model vs actual outcomes
    python -m pm.analyze sim --version taker-v1 --hypothesis 4 [--edge 0.03]
    python -m pm.analyze predict --version taker-v1 --hypothesis 4 --from research/<memo>.md
    python -m pm.analyze sealed --version taker-v1 --hypothesis 4   # once, human-approved only

Windows are split by time: the first 70% is development data, the last 30% is sealed.
Everything except `sealed` uses development windows only.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import stat
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import ledger
from pm import store
from pm.model import fair_prob, realized_sigma, spot_series, taker_fee

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "backtests"
SEALED_FRAC = 0.30
SIGMA_LOOKBACK = 1800


# ---------- data ----------

def windows(conn, part="dev", sealed_frac=None, series="KXBTC15M"):
    """One series' settled windows with outcomes, split by time into dev / sealed.
    sealed_frac defaults to SEALED_FRAC, looked up at call time."""
    sealed_frac = SEALED_FRAC if sealed_frac is None else sealed_frac
    w = pd.read_sql("SELECT ticker, open_ts, close_ts, floor_strike, result FROM markets "
                    "WHERE result IN ('yes','no') AND floor_strike IS NOT NULL AND ticker LIKE ? "
                    "ORDER BY close_ts", conn, params=(f"{series}-%",))
    cut = int(len(w) * (1 - sealed_frac))
    return (w.iloc[:cut] if part == "dev" else w.iloc[cut:]).reset_index(drop=True)


def spot_for(conn, start, end):
    rows = conn.execute("SELECT ts, price FROM spot_trades WHERE source='kraken' AND ts BETWEEN ? AND ? "
                        "ORDER BY ts", (start, end)).fetchall()
    return spot_series(rows, start, end) if len(rows) > 100 else None


_MODEL_CACHE = {}


def window_model(conn, w):
    """Cached per (database, window): the same model series is used by every analysis."""
    key = (conn.execute("PRAGMA database_list").fetchone()[2], w.ticker)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = _window_model(conn, w)
    return _MODEL_CACHE[key]


def _window_model(conn, w):
    """Per-second model probability for one window, with the Kraken-vs-index basis removed.
    The strike is the BRTI 60s average before open; Kraken's average over the same 60s gives the
    basis, which is known at open (no look-ahead)."""
    s = spot_for(conn, w.open_ts - SIGMA_LOOKBACK - 120, w.close_ts)
    if s is None or s.loc[w.open_ts - 60:w.open_ts].isna().all():
        return None
    sigma = realized_sigma(s, SIGMA_LOOKBACK)
    basis = s.loc[w.open_ts - 60:w.open_ts].mean() - w.floor_strike
    adj = s - basis
    out = {}
    for t in np.arange(math.ceil(w.open_ts), math.floor(w.close_ts) + 1, dtype=float):
        sp, sg = adj.get(t), sigma.get(t)
        if sp is None or sg is None or np.isnan(sp) or np.isnan(sg) or sg <= 0:
            continue
        tau = w.close_ts - t
        known = adj.loc[w.close_ts - 60:t].mean() if tau < 60 else None
        out[t] = fair_prob(sp, w.floor_strike, tau, sg, known)
    ser = pd.Series(out, dtype=float)
    ser.index = ser.index.astype(float)
    return ser


# ---------- analyses ----------

def lag_analysis(conn, max_lag=30, part="dev"):
    """Correlation of 1-second changes: market price(t) vs model probability(t - k).
    A peak at k > 0 means the market follows spot k seconds late. Both series are sampled on a
    1-second grid, so the answer is accurate to about +/- 1 second."""
    ws = windows(conn, part)
    have = {r[0] for r in conn.execute("SELECT DISTINCT ticker FROM kalshi_trades")}
    ws = ws[ws.ticker.isin(have)]
    dm_all, dp_all = [], []
    for w in ws.itertuples():
        p = window_model(conn, w)
        if p is None or len(p) < 300:
            continue
        tr = conn.execute("SELECT ts, yes_price FROM kalshi_trades WHERE ticker=? ORDER BY ts", (w.ticker,)).fetchall()
        m = spot_series(tr, p.index[0], p.index[-1]).reindex(p.index)
        keep = (p.index > w.open_ts + 60) & (p.index < w.close_ts - 60)   # skip open/close edges
        dm_all.append(m.diff()[keep].to_numpy()); dp_all.append(p.diff()[keep].to_numpy())
    if not dm_all:
        return {"windows": 0, "note": "no windows with both Kalshi trades and Kraken data yet"}
    res = {}
    for k in range(-5, max_lag + 1):
        xs, ys = [], []
        for dm, dp in zip(dm_all, dp_all):
            if k >= 0:
                a, b = dm[k:], dp[:len(dp) - k] if k else dp
            else:
                a, b = dm[:k], dp[-k:]
            ok = ~(np.isnan(a) | np.isnan(b))
            xs.append(a[ok]); ys.append(b[ok])
        x, y = np.concatenate(xs), np.concatenate(ys)
        res[k] = round(float(np.corrcoef(x, y)[0, 1]), 4) if len(x) > 100 else None
    best = max((k for k in res if res[k] is not None), key=lambda k: res[k])
    return {"windows": len(dm_all), "corr_by_lag_s": res, "peak_lag_s": best,
            "reading": ("market moves at the same time as spot (no exploitable lag at 1s resolution)"
                        if best <= 0 else f"market changes trail spot-implied odds by ~{best}s")}


def minute_frame(conn, part="dev"):
    """One row per (window, minute): market quotes, model probability, outcome."""
    rows = []
    for w in windows(conn, part).itertuples():
        c = pd.read_sql("SELECT ts, yes_bid, yes_ask FROM candles WHERE ticker=? AND ts > ? AND ts < ? "
                        "ORDER BY ts", conn, params=(w.ticker, w.open_ts + 60, w.close_ts))
        if c.empty:
            continue
        p = window_model(conn, w)
        if p is None:
            continue
        for r in c.itertuples():
            if not (0 < r.yes_bid < r.yes_ask < 1) or r.ts not in p.index:
                continue
            rows.append({"ticker": w.ticker, "ts": r.ts, "tau": w.close_ts - r.ts, "bid": r.yes_bid,
                         "ask": r.yes_ask, "mid": (r.yes_bid + r.yes_ask) / 2, "model": p[r.ts],
                         "y": 1.0 if w.result == "yes" else 0.0})
    return pd.DataFrame(rows)


def calibration(conn, part="dev"):
    f = minute_frame(conn, part)
    if f.empty:
        return {"rows": 0, "note": "no data yet"}
    brier = lambda q: float(((f[q] - f.y) ** 2).mean())
    f["blend"] = (f["mid"] + f["model"]) / 2
    bins = pd.cut(f["mid"], np.linspace(0, 1, 11))
    table = f.groupby(bins, observed=True).agg(n=("y", "size"), market=("mid", "mean"), actual=("y", "mean"),
                                              model=("model", "mean")).round(3)
    return {"rows": len(f), "windows": int(f.ticker.nunique()),
            "brier_market": round(brier("mid"), 5), "brier_model": round(brier("model"), 5),
            "brier_blend": round(brier("blend"), 5),
            "reading": "lower Brier is better; if the blend beats the market, the model adds information the market hasn't priced",
            "by_market_price": table.reset_index().astype({"mid": str}).to_dict("records")}


def simulate(conn, edge=0.03, fill="next", part="dev", contracts=100):
    """Taker strategy, at most one entry per window, held to settlement.
    Each minute: if model - ask > edge + fee, buy YES; if (1 - model) - (1 - bid) > edge + fee, buy NO.
    fill='same' pays the ask seen at the signal (no delay: optimistic).
    fill='next' pays the ask one minute later (pessimistic delay)."""
    f = minute_frame(conn, part)
    if f.empty:
        return {"trades": 0, "note": "no data yet"}
    trades = []
    for ticker, g in f.groupby("ticker", sort=False):
        g = g.sort_values("ts").reset_index(drop=True)
        for i, r in g.iterrows():
            yes_px, no_px = r.ask, 1 - r.bid
            side = None
            if r.model - yes_px > edge + taker_fee(yes_px, contracts):
                side = "yes"
            elif (1 - r.model) - no_px > edge + taker_fee(no_px, contracts):
                side = "no"
            if not side:
                continue
            if fill == "next":
                if i + 1 >= len(g):
                    break
                n = g.iloc[i + 1]
                px = n.ask if side == "yes" else 1 - n.bid
            else:
                px = yes_px if side == "yes" else no_px
            fee = taker_fee(px, contracts)
            win = r.y if side == "yes" else 1 - r.y
            trades.append({"ticker": ticker, "ts": r.ts, "side": side, "price": px, "fee": fee,
                           "model": r.model, "pnl": win - px - fee})
            break
    t = pd.DataFrame(trades)
    if t.empty:
        return {"trades": 0, "edge": edge, "fill": fill}
    pnl = t.pnl
    sharpe = float(pnl.mean() / pnl.std(ddof=1)) if len(pnl) > 1 and pnl.std(ddof=1) > 0 else 0.0
    return {"edge": edge, "fill": fill, "trades": len(t), "windows_seen": int(f.ticker.nunique()),
            "win_rate": round(float((pnl > 0).mean()), 4), "avg_price": round(float(t.price.mean()), 4),
            "avg_fee_per_contract": round(float(t.fee.mean()), 4),
            "pnl_per_contract": round(float(pnl.mean()), 5), "total_pnl_per_contract": round(float(pnl.sum()), 3),
            "sharpe_per_trade": round(sharpe, 4), "t_stat": round(sharpe * math.sqrt(len(pnl)), 2)}


# ---------- discipline: locked predictions, counted variations, sealed holdout ----------

def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def lock_prediction(conn, hid, version, source):
    dest = RESULTS / f"pm_{version}-prediction.md"
    if dest.exists() or ledger.get_prediction(conn, hid, version):
        raise PermissionError(f"A prediction for {version} is already locked.")
    shutil.copyfile(source, dest)
    os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    ledger.set_prediction(conn, hid, version, dest, _sha(dest))
    return dest


def verify_prediction(conn, hid, version):
    pred = ledger.get_prediction(conn, hid, version)
    if not pred:
        raise PermissionError(f"No locked prediction for {version}. Run `predict` first.")
    if _sha(pred["path"]) != pred["sha256"]:
        raise PermissionError(f"{pred['path']} was edited after it was locked.")
    return Path(pred["path"]).read_text()


def write_report(name, result, prediction=None):
    stamp = date.today().isoformat()
    j = RESULTS / f"{name}-{stamp}.json"
    j.write_text(json.dumps(result, indent=2, default=str))
    md = RESULTS / f"{name}-{stamp}.md"
    pred = f"## Locked prediction (unedited)\n\n{prediction}\n\n" if prediction else ""
    md.write_text(f"# {name} ({stamp})\n\n{pred}## Results\n\n```json\n{json.dumps(result, indent=2, default=str)}\n```\n")
    return j, md


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["lag", "calibration", "sim", "predict", "sealed"])
    p.add_argument("--hypothesis", type=int)
    p.add_argument("--version")
    p.add_argument("--from", dest="source")
    p.add_argument("--edge", type=float, default=0.03)
    a = p.parse_args()
    hconn = store.connect("history")

    if a.cmd == "lag":
        print(json.dumps(lag_analysis(hconn), indent=2)); return
    if a.cmd == "calibration":
        print(json.dumps(calibration(hconn), indent=2, default=str)); return

    if a.hypothesis is None or not a.version:
        p.error("--hypothesis and --version are required")
    lconn = ledger.connect()
    if a.cmd == "predict":
        print(lock_prediction(lconn, a.hypothesis, a.version, a.source)); return

    prediction = verify_prediction(lconn, a.hypothesis, a.version)
    if a.cmd == "sim":
        result = {"part": "dev", "version": a.version,
                  "fills": {fill: simulate(hconn, a.edge, fill, "dev") for fill in ("same", "next")},
                  "lag": lag_analysis(hconn), "calibration": calibration(hconn)}
        s = result["fills"]["next"]
        ledger.record_trial(lconn, a.hypothesis, a.version, s.get("sharpe_per_trade", 0.0), s.get("trades", 0))
        ledger.update(lconn, a.hypothesis, date_tested=date.today().isoformat(), strategy_file="pm/analyze.py",
                      strategy_version=a.version, backtest_result=json.dumps(result["fills"]))
    else:
        if ledger.get(lconn, a.hypothesis)["strategy_version"] != a.version:
            raise PermissionError("Sealed test must use the version that passed development.")
        ledger.claim_sealed_test(lconn, a.hypothesis)
        result = {"part": "sealed", "version": a.version,
                  "fills": {fill: simulate(hconn, a.edge, fill, "sealed") for fill in ("same", "next")}}
        ledger.record_sealed_result(lconn, a.hypothesis, result)
    print(*write_report(f"pm_{a.version}{'-SEALED' if a.cmd == 'sealed' else ''}", result, prediction), sep="\n")


if __name__ == "__main__":
    main()
