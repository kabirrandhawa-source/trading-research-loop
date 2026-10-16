"""Development backtest for hypothesis 15: S&P 500 long-only momentum plus cash profitability.

Rules live in strategies/momo_quality_v1.py. Development data only: every price row and every filing
used is dated before backtest.SEALED_START (2024-01-30); the last holding ends 2024-01-29.

    .venv/bin/python -m stocks.momo_quality run --hypothesis 15     # needs a locked prediction
    .venv/bin/python -m stocks.momo_quality stale                    # how often fundamentals.latest() is stale
"""
import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def _etf(sym, sealed):
    d = pd.read_csv(ROOT / "data" / f"{sym}.csv", usecols=["timestamp", "close"])
    d["day"] = pd.to_datetime(d["timestamp"].str[:10])
    d = d[d["day"] < pd.Timestamp(sealed)]
    return d.set_index("day")["close"]


def load():
    import backtest
    from stocks import universe
    from strategies.momo_quality_v1 import PARAMS
    sealed = backtest.SEALED_START
    m = universe.membership()
    px = universe.prices(sorted(set(m.ticker)), start=universe.START, end=sealed, m=m)
    px = px[px["day"] < sealed]
    close = px.pivot(index="day", columns="ticker", values="close")
    close.index = pd.to_datetime(close.index)
    spy = _etf("SPY", sealed)
    etfs = pd.DataFrame({s: _etf(s, sealed) for s in PARAMS["sector_etfs"]}).reindex(spy.index)
    close = close.reindex(spy.index)
    assert close.index.max() < pd.Timestamp(sealed) and spy.index.max() < pd.Timestamp(sealed)
    return close, spy, etfs, m


def anchors_and_formations(days, first_formation, last_hold_end):
    """anchors = [first day] + last trading day of each month. Formation k holds to anchors[k+1]."""
    s = pd.Series(days, index=days)
    month_ends = list(s.groupby([days.year, days.month]).max())
    anchors = [days[0]] + [d for d in month_ends if d != days[0]]
    forms = [k for k, d in enumerate(anchors) if pd.Timestamp(first_formation) <= d and k + 1 < len(anchors)
             and anchors[k + 1] <= pd.Timestamp(last_hold_end)]
    return anchors, forms


def profitability(fconn, tickers, as_of, max_age_months):
    """OCF / assets from the newest fiscal year in a 10-K filed by as_of (within max_age_months)."""
    from stocks import fundamentals as fu
    tickers = sorted(tickers)
    ocf = fu.latest_annual(fconn, tickers, "op_cash_flow", as_of, max_age_months=max_age_months)
    if not len(ocf):
        return pd.Series(dtype=float), {}
    q = (f"SELECT ticker, end, val, filed, accn FROM facts WHERE metric = 'assets' AND form = '10-K' AND filed <= ? "
         f"AND ticker IN ({','.join('?' * len(ocf))})")
    a = pd.read_sql(q, fconn, params=(str(pd.Timestamp(as_of).date()), *ocf.index))
    out, how = {}, {"same_filing": 0, "other_10k_same_year_end": 0}
    for t, row in ocf.iterrows():
        cand = a[(a.ticker == t) & (a.end == row["end"])]
        same = cand[cand.accn == row["accn"]]
        pick = same if len(same) else cand
        if not len(pick):
            continue
        v = pick.sort_values("filed").iloc[-1]["val"]
        if v > 0:
            out[t] = row["val"] / v
            how["same_filing" if len(same) else "other_10k_same_year_end"] += 1
    return pd.Series(out, dtype=float), how


def simulate(close, spy, etfs, m, P, fconn):
    from stocks import universe
    from strategies import momo_quality_v1 as S
    days = close.index
    anchors, forms = anchors_and_formations(days, P["first_formation"], P["last_hold_end"])
    anchor_closes = close.ffill(limit=P["anchor_ffill_days"]).loc[anchors]
    rets_d = close.pct_change(fill_method=None)
    spy_d, etf_d = spy.pct_change(), etfs.pct_change()
    variants = ("screened", "pure", "sector_neutral", "tech_capped")
    prev = {v: pd.Series(dtype=float) for v in variants}
    rows, cover, sector_log = [], [], []
    for k in forms:
        t0, t1 = anchors[k], anchors[k + 1]
        mem = universe.members_on(t0, m)
        priced = sorted(t for t in mem if t in close.columns and not np.isnan(close.at[t0, t]))
        mom = S.momentum_12_1(anchor_closes[priced], k)
        prof, how = profitability(fconn, priced, t0, P["max_age_months"])
        top, screened, uncovered = S.select(mom, prof, P["decile"], P["prof_quantile"])
        elig = list(mom.dropna().index)
        i0 = days.get_loc(t0)
        win = slice(max(0, i0 - P["sector_lookback"] + 1), i0 + 1)
        sec = S.assign_sectors(rets_d.iloc[win][elig], etf_d.iloc[win], spy_d.iloc[win],
                               P["sector_min_days"], P["sector_min_corr"])
        weights = {"screened": S.equal_weights(screened), "pure": S.equal_weights(top),
                   "sector_neutral": S.sector_neutral_weights(screened, sec, [sec[t] for t in elig]),
                   "tech_capped": S.tech_capped_weights(screened, sec, P["tech_cap"])}
        row = {"formed": t0.date(), "end": t1.date(), "spy": float(spy[t1] / spy[t0] - 1)}
        for v in variants:
            w = weights[v]
            h = S.hold(close, t0, t1, w)
            traded = S.traded_weight(w, prev[v])
            prev[v] = h["end_weights"]          # fractions of end value; exited names already sold (cash)
            row[f"{v}_gross"] = h["gross"]
            row[f"{v}_traded"] = traded
            row[f"{v}_exit_value"] = h["exit_value"]
            row[f"{v}_exits"] = len(h["exited"])
            row[f"{v}_n"] = len(w)
            for c in (P["cost_bps"], P["stress_cost_bps"]):
                row[f"{v}_net{int(c)}"] = h["gross"] - c / 1e4 * (traded + h["exit_value"])
            if v == "screened":
                row["screened_exited_names"] = ",".join(h["exited"])
        rows.append(row)
        cover.append({"formed": str(t0.date()), "members": len(mem), "members_priced": len(priced),
                      "with_12_1": len(elig), "members_with_prof": len(prof),
                      "member_prof_coverage": round(len(prof) / max(len(priced), 1), 3),
                      "top_decile": len(top), "top_decile_no_coverage_dropped": len(uncovered),
                      "screened": len(screened), "assets_match": how,
                      "dropped_names": uncovered})
        lab = pd.Series([sec.get(t, "other") for t in screened]).value_counts(normalize=True).round(3).to_dict()
        sector_log.append({"formed": str(t0.date()), "screened_sector_mix": lab,
                           "universe_xlk_share": round(float(np.mean([sec[t] == "XLK" for t in elig])), 3)})
    return pd.DataFrame(rows), cover, sector_log, sec


def sector_quality(sec):
    """Agreement of the return-based sector labels (last formation) with the sector SPDR holdings list
    in sleeve/context_v2.py (current large holdings; only names that were eligible members)."""
    from sleeve.context_v2 import SECTOR_HOLDINGS
    hits, n, misses = 0, 0, []
    for etf, names in SECTOR_HOLDINGS.items():
        for t in names:
            if t in sec:
                n += 1
                hits += sec[t] == etf
                if sec[t] != etf:
                    misses.append(f"{t}:{etf}->{sec[t]}")
    return {"checked": n, "agree": hits, "agree_pct": round(hits / n * 100, 1) if n else None, "misses": misses}


def stats(df, P, lconn, hid, version, record=True):
    import backtest
    import ledger
    from strategies import momo_quality_v1 as S
    c, c2 = int(P["cost_bps"]), int(P["stress_cost_bps"])
    spy = df["spy"].to_numpy()
    n = len(df)
    yrs = n / 12

    def block(v, cost):
        r = df[f"{v}_{cost}"].to_numpy() if cost != "gross" else df[f"{v}_gross"].to_numpy()
        ex = r - spy
        cap = S.capm(r, spy)
        return {"cagr": float(np.prod(1 + r) ** (1 / yrs) - 1), "mean_monthly": float(r.mean()),
                "vol_annual": float(r.std(ddof=1) * np.sqrt(12)),
                "sharpe_annual_rf0": float(r.mean() / r.std(ddof=1) * np.sqrt(12)),
                "excess_mean_monthly": float(ex.mean()), "excess_annualized": float(ex.mean() * 12),
                "excess_t": S.t_stat(ex), "tracking_error_annual": float(ex.std(ddof=1) * np.sqrt(12)),
                "info_ratio_annual": float(ex.mean() / ex.std(ddof=1) * np.sqrt(12)),
                "months_beating_spy_pct": float((ex > 0).mean() * 100), "positive_months_pct": float((r > 0).mean() * 100),
                "capm": cap, "alpha_annualized": cap["alpha_monthly"] * 12,
                "max_drawdown": S.max_drawdown(r)}

    out = {"months": n, "first_month_end": str(df["end"].iloc[0]), "last_hold_end": str(df["end"].iloc[-1]),
           "spy": {"cagr": float(np.prod(1 + spy) ** (1 / yrs) - 1), "max_drawdown": S.max_drawdown(spy),
                   "vol_annual": float(spy.std(ddof=1) * np.sqrt(12))}}
    for v in ("screened", "pure", "sector_neutral", "tech_capped"):
        out[v] = {f"net{c}": block(v, f"net{c}"), f"net{c2}": block(v, f"net{c2}"), "gross": block(v, "gross"),
                  "turnover_one_sided_monthly_mean": float(df[f"{v}_traded"].iloc[1:].mean() / 2),
                  "exit_sales_total": int(df[f"{v}_exits"].sum()),
                  "names_per_month_mean": float(df[f"{v}_n"].mean()), "names_min": int(df[f"{v}_n"].min())}
    scr = df[f"screened_net{c}"].to_numpy()
    rel = np.cumprod(1 + scr) / np.cumprod(1 + spy)
    rel = np.concatenate([[1.0], rel])
    out["screened"]["relative_drawdown_vs_spy"] = float((rel / np.maximum.accumulate(rel) - 1).min())
    w = df.assign(net=scr, excess=scr - spy).nsmallest(3, "net")
    out["worst_3_months"] = [{"month_end": str(r.end), "net": round(r.net, 4), "spy": round(r.spy, 4),
                              "excess": round(r.excess, 4)} for r in w.itertuples()]
    ex_w = df.assign(excess=scr - spy).nsmallest(3, "excess")
    out["worst_3_excess_months"] = [{"month_end": str(r.end), "excess": round(r.excess, 4)} for r in ex_w.itertuples()]
    df["year"] = pd.to_datetime(df["end"]).dt.year
    out["by_year"] = {str(y): {"screened_net": round(float(np.prod(1 + g[f"screened_net{c}"]) - 1), 4),
                               "pure_net": round(float(np.prod(1 + g[f"pure_net{c}"]) - 1), 4),
                               "spy": round(float(np.prod(1 + g["spy"]) - 1), 4), "months": len(g)}
                      for y, g in df.groupby("year")}
    ex = scr - spy
    pure_ex = df[f"pure_net{c}"].to_numpy() - spy
    sr = float(ex.mean() / ex.std(ddof=1))
    sr_pure = float(pure_ex.mean() / pure_ex.std(ddof=1))
    if record:
        ledger.record_trial(lconn, hid, version, sr, n)
    h12 = ledger.trial_sharpes(lconn, 12)
    trials = ledger.trial_sharpes(lconn, hid) + [sr_pure] + h12
    s = pd.Series(ex)
    out["deflated_sharpe"] = {
        "series": "monthly excess return vs SPY, net 10 bps",
        "trials": "h15 trials + pure-momentum basket (stand-in for untested h12's related momentum sample)"
                  f" + h12 recorded trials ({len(h12)})",
        "sharpe_per_month": sr, "pure_momentum_sharpe_per_month": sr_pure,
        **backtest.deflated_sharpe(sr, n, float(s.skew()), float(s.kurt() + 3), trials)}
    return out


def verdict(o, P):
    c = f"net{int(P['cost_bps'])}"
    s, sn = o["screened"][c], o["sector_neutral"][c]
    checks = {"excess_t_gt_2": s["excess_t"] > 2, "capm_alpha_positive": s["capm"]["alpha_monthly"] > 0,
              "sector_neutral_alpha_positive": sn["capm"]["alpha_monthly"] > 0}
    return {"checks": checks, "pass": all(checks.values()),
            "claim_beats_spy_after_costs": s["cagr"] > o["spy"]["cagr"],
            "claim_lower_max_dd_than_pure": s["max_drawdown"] > o["pure"][c]["max_drawdown"]}


def stale_report(months=None):
    """How often fundamentals.latest() returns an older period end than the newest one filed by that
    date (development dates only), per metric."""
    import backtest
    from stocks import fundamentals as fu
    from stocks import universe
    m, fconn = universe.membership(), fu.connect()
    dates = months or [d for d in pd.date_range("2017-01-31", "2023-12-31", freq="M")]
    metrics = ["revenue", "net_income", "shares_outstanding", "op_cash_flow", "assets", "eps_diluted", "equity"]
    out = {}
    for metric in metrics:
        n = stale = 0
        lags = []
        for d in dates:
            as_of = str(d.date())
            assert as_of < backtest.SEALED_START
            tick = sorted(universe.members_on(d, m))
            got = fu.latest(fconn, tick, metric, as_of)
            if not len(got):
                continue
            q = (f"SELECT ticker, MAX(end) AS newest FROM facts WHERE metric = ? AND filed <= ? AND ticker IN "
                 f"({','.join('?' * len(tick))}) GROUP BY ticker")
            newest = pd.read_sql(q, fconn, params=(metric, as_of, *tick)).set_index("ticker")["newest"]
            j = got.join(newest, how="inner")
            n += len(j)
            bad = j[j["end"] < j["newest"]]
            stale += len(bad)
            lags += list((pd.to_datetime(bad["newest"]) - pd.to_datetime(bad["end"])).dt.days)
        out[metric] = {"ticker_months": n, "stale": stale, "stale_pct": round(stale / n * 100, 1) if n else None,
                       "median_days_behind": float(np.median(lags)) if lags else 0.0}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "stale"])
    ap.add_argument("--hypothesis", type=int, default=15)
    a = ap.parse_args()
    if a.cmd == "stale":
        print(json.dumps(stale_report(), indent=2))
        return
    import backtest
    import ledger
    from stocks import fundamentals as fu
    from strategies.momo_quality_v1 import MomoQualityV1, PARAMS
    cls = MomoQualityV1
    lconn = ledger.connect()
    backtest._check_owner(cls, a.hypothesis)
    prediction = backtest.verify_prediction(lconn, a.hypothesis, cls.VERSION)    # refuses without a lock
    close, spy, etfs, m = load()
    df, cover, sector_log, last_sec = simulate(close, spy, etfs, m, PARAMS, fu.connect())
    o = stats(df, PARAMS, lconn, a.hypothesis, cls.VERSION)
    o["verdict"] = verdict(o, PARAMS)
    o["coverage"] = {"per_rebalance": cover,
                     "top_decile_dropped_total": int(sum(c["top_decile_no_coverage_dropped"] for c in cover)),
                     "top_decile_total": int(sum(c["top_decile"] for c in cover))}
    o["exits"] = {"screened_exit_sales": int(df["screened_exits"].sum()),
                  "names": [x for x in df["screened_exited_names"] if x]}
    o["sectors"] = {"method": "return-based: SPDR (8 sectors) with max corr of residual-vs-SPY daily returns over 252d",
                    "quality_vs_spdr_holdings_last_formation": sector_quality(last_sec), "per_rebalance": sector_log}
    o["data"] = {"prices": "Alpaca daily bars adjustment=all (splits+dividends) for stocks and SPY: total-return-like",
                 "risk_free": "taken as 0 in CAPM (no T-bill series in repo)", "sealed_start": backtest.SEALED_START,
                 "params": PARAMS}
    o["monthly"] = df.drop(columns=["year"]).astype({"formed": str, "end": str}).to_dict(orient="records")
    stem = f"momo_quality_{cls.VERSION}-{date.today().isoformat()}"
    jp = ROOT / "backtests" / f"{stem}.json"
    jp.write_text(json.dumps(o, indent=2, default=str))
    (ROOT / "backtests" / f"{stem}.md").write_text(
        f"# {stem}\n\n## Saved prediction (unedited)\n\n{prediction}\n\n## Results (summary; full in {jp.name})\n\n```json\n"
        + json.dumps({k: v for k, v in o.items() if k not in ("monthly", "coverage", "sectors")}, indent=2, default=str)
        + "\n```\n")
    ledger.update(lconn, a.hypothesis, strategy_file="strategies/momo_quality_v1.py", strategy_version=cls.VERSION,
                  date_tested=date.today().isoformat(),
                  backtest_result=json.dumps({"verdict": o["verdict"], "screened_net10": o["screened"]["net10"],
                                              "spy": o["spy"], "dsr": o["deflated_sharpe"]}, default=str))
    print(json.dumps({k: v for k, v in o.items() if k not in ("monthly", "coverage", "sectors")}, indent=2, default=str))
    print(jp)


if __name__ == "__main__":
    main()
