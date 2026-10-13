"""Pre-registered calibration screen across Kalshi 15-minute markets (ledger hypothesis 5).

Question: in any series, at any price level, does buying YES at the ask (or NO at 1 - bid) make
money after Kalshi's taker fee?

Design, fixed before looking at the data:
- Development windows only (first 70% of each series by time); the last 30% stays sealed.
- Rows: 1-minute quotes from the second minute to the close, with 0 < bid < ask < 1.
- Each window contributes at most ONE row per price bucket (the first minute its mid falls in that
  bucket), so correlated minutes from the same window can't inflate the sample.
- 10 buckets of mid price (0-10c, ..., 90-100c) x 2 sides x the tested series. A lead must have
  Bonferroni-adjusted p < 0.05 across ALL tests AND earn at least 1c per contract after fees.

    python -m pm.calibrate predict --hypothesis 5 --version calib-v1 --from <memo>
    python -m pm.calibrate run --hypothesis 5 --version calib-v1
"""
import argparse
import json
import math
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd

import ledger
from pm import analyze, store
from pm.model import taker_fee

SERIES = ["KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M", "KXGOLD15M", "KXSILVER15M", "KXWTI15M",
          "KXEURUSD15M", "KXUSDJPY15M", "KXGBPUSD15M"]
BUCKETS = np.linspace(0, 1, 11)
MIN_PROFIT = 0.01
ALPHA = 0.05


def bucket_rows(conn, series, part="dev"):
    """One row per (window, price bucket): first minute whose mid is in that bucket."""
    out = []
    for w in analyze.windows(conn, part, series=series).itertuples():
        c = pd.read_sql("SELECT ts, yes_bid, yes_ask FROM candles WHERE ticker=? AND ts > ? AND ts < ? ORDER BY ts",
                        conn, params=(w.ticker, w.open_ts + 60, w.close_ts))
        c = c[(c.yes_bid > 0) & (c.yes_ask < 1) & (c.yes_bid < c.yes_ask)]
        if c.empty:
            continue
        c["mid"] = (c.yes_bid + c.yes_ask) / 2
        c["bucket"] = np.clip(np.digitize(c.mid, BUCKETS) - 1, 0, 9)
        first = c.groupby("bucket", as_index=False).first()
        first["ticker"], first["y"] = w.ticker, 1.0 if w.result == "yes" else 0.0
        out.append(first)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def screen(conn, series_list=SERIES, part="dev"):
    tests, calib = [], {}
    for s in series_list:
        r = bucket_rows(conn, s, part)
        if r.empty:
            continue
        r["fee_yes"] = r.yes_ask.map(taker_fee)
        r["fee_no"] = (1 - r.yes_bid).map(taker_fee)
        r["pnl_yes"] = r.y - r.yes_ask - r.fee_yes
        r["pnl_no"] = (1 - r.y) - (1 - r.yes_bid) - r.fee_no
        calib[s] = []
        for b, g in r.groupby("bucket"):
            n = len(g)
            act, mid = g.y.mean(), g.mid.mean()
            se = math.sqrt(max(act * (1 - act), 1e-9) / n)
            calib[s].append({"bucket": f"{BUCKETS[b]:.1f}-{BUCKETS[b + 1]:.1f}", "n_windows": n,
                             "market": round(mid, 3), "actual": round(act, 3), "gap": round(act - mid, 3),
                             "gap_se": round(se, 3)})
            for side in ("yes", "no"):
                x = g[f"pnl_{side}"]
                sd = x.std(ddof=1) if n > 1 else float("nan")
                z = x.mean() / (sd / math.sqrt(n)) if n > 1 and sd > 0 else 0.0
                tests.append({"series": s, "bucket": f"{BUCKETS[b]:.1f}-{BUCKETS[b + 1]:.1f}", "side": side,
                              "n_windows": n, "pnl_per_contract": round(x.mean(), 4), "z": round(z, 2),
                              "p_one_sided": 1 - NormalDist().cdf(z)})
    m = len(tests)
    for t in tests:
        t["p_bonferroni"] = min(1.0, t["p_one_sided"] * m)
        t["lead"] = bool(t["p_bonferroni"] < ALPHA and t["pnl_per_contract"] >= MIN_PROFIT and t["n_windows"] >= 30)
    best = sorted(tests, key=lambda t: t["z"], reverse=True)[:10]
    return {"part": part, "series": series_list, "n_tests": m, "z_needed": round(NormalDist().inv_cdf(1 - ALPHA / max(m, 1)), 2),
            "leads": [t for t in tests if t["lead"]], "top_10_by_z": best,
            "share_of_tests_profitable": round(sum(t["pnl_per_contract"] > 0 for t in tests) / max(m, 1), 3),
            "calibration": calib}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["predict", "run"])
    p.add_argument("--hypothesis", type=int, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--from", dest="source")
    a = p.parse_args()
    lconn, hconn = ledger.connect(), store.connect("history")
    if a.cmd == "predict":
        print(analyze.lock_prediction(lconn, a.hypothesis, a.version, a.source))
        return
    prediction = analyze.verify_prediction(lconn, a.hypothesis, a.version)
    result = screen(hconn)
    top = result["top_10_by_z"][0] if result["top_10_by_z"] else {"z": 0, "n_windows": 0}
    ledger.record_trial(lconn, a.hypothesis, a.version, top["z"] / math.sqrt(max(top["n_windows"], 1)), top["n_windows"])
    ledger.update(lconn, a.hypothesis, date_tested=date.today().isoformat(), strategy_file="pm/calibrate.py",
                  strategy_version=a.version,
                  backtest_result=json.dumps({k: result[k] for k in ("n_tests", "z_needed", "leads", "share_of_tests_profitable")}))
    print(*analyze.write_report(f"pm_{a.version}", result, prediction), sep="\n")


if __name__ == "__main__":
    main()
