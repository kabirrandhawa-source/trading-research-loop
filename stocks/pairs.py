"""Pairs trading on S&P 500 stocks, distance method (ledger hypothesis 11, version v1).

Rules follow Gatev, Goetzmann & Rouwenhorst (2006), fixed BEFORE any test:
- Each month, formation = the previous 252 trading days. Candidates: index members on the day before
  the month starts with a full price history over the window (dead companies included).
- Prices are normalized to 1 at the window start; the 20 pairs with the smallest sum of squared
  differences are chosen. Pairs that are two share classes of one company (daily return correlation
  above 0.98, e.g. GOOG/GOOGL) are excluded: that's not two companies.
- Trading = the next 126 trading days. Spread = difference of prices normalized to 1 at the formation
  end. When |spread| > 2 x its formation standard deviation at a close, buy the low stock and short
  the high one ($1 each) at the NEXT open. Close at the next open after the spread crosses zero;
  can reopen. Anything open at the period end closes at the last close. If a stock's data stops
  (it left the index), the pair closes at the last close both had, and stops for the period.
- Costs: 5 bps per leg per trade (desk default), short borrow 0.5% a year on the short leg.
- Return = profit on committed capital: portfolio P&L / 20 pairs. A new portfolio starts every month,
  so six overlap; the strategy's daily return is their average.

    .venv/bin/python -m stocks.pairs run --hypothesis 11 --version v1
"""
import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARAMS_V1 = dict(formation=252, trading=126, n_pairs=20, open_sd=2.0, same_company_corr=0.98,
                 cost_bps=5.0, borrow_pa=0.005, first_trading_month="2017-01")
DIAGNOSTIC_PAIRS = [("KO", "PEP"), ("HD", "LOW")]


def load(end=None):
    """Adjusted closes and opens (days x tickers), development period only."""
    import backtest
    from stocks import universe
    end = min(end or backtest.SEALED_START, backtest.SEALED_START)
    m = universe.membership()
    px = universe.prices(sorted(set(m.ticker)), start=universe.START, end=end, m=m)
    px = px[px["day"] < backtest.SEALED_START]
    close = px.pivot(index="day", columns="ticker", values="close").sort_index()
    opn = px.pivot(index="day", columns="ticker", values="open").reindex_like(close)
    close.index = opn.index = pd.to_datetime(close.index)
    return close, opn, m


def select_pairs(form_close, n_pairs, same_company_corr):
    """form_close: days x candidate tickers, no gaps. Returns [(a, b, ssd, sigma)] smallest SSD first."""
    p = form_close / form_close.iloc[0]
    x = p.to_numpy(float).T
    sq = (x ** 2).sum(1)
    ssd = sq[:, None] + sq[None, :] - 2 * x @ x.T
    iu = np.triu_indices(len(x), 1)
    order = np.argsort(ssd[iu])
    rets = form_close.pct_change().iloc[1:].to_numpy(float)
    cols = list(form_close.columns)
    out = []
    for k in order:
        i, j = iu[0][k], iu[1][k]
        if np.corrcoef(rets[:, i], rets[:, j])[0, 1] > same_company_corr:
            continue
        out.append((cols[i], cols[j], float(ssd[i, j]), float(np.std(x[i] - x[j], ddof=1))))
        if len(out) == n_pairs:
            break
    return out


def simulate_pair(ci, cj, oi, oj, base_i, base_j, sigma, p):
    """One pair over one trading period. Arrays are that period's closes/opens.
    Returns (daily P&L on $1 per leg, list of trades)."""
    n = len(ci)
    pnl = np.zeros(n)
    trades = []
    cost = p["cost_bps"] / 10_000
    pos, pending, entry_t = 0, None, None
    ni = nj = ref_i = ref_j = 0.0
    trade_pnl = 0.0

    def close_trade(t, pi, pj, reason):
        nonlocal pos, trade_pnl
        g = pos * (ni * (pi - ref_i) - nj * (pj - ref_j))
        c = cost * (ni * pi + nj * pj)
        pnl[t] += g - c
        trade_pnl += g - c
        trades.append({"open_day": entry_t, "close_day": t, "dir": pos, "pnl": trade_pnl, "reason": reason})
        pos = 0

    for t in range(n):
        if any(np.isnan(v) for v in (ci[t], cj[t], oi[t], oj[t])):
            if pos:
                close_trade(max(t - 1, 0), ref_i, ref_j, "data_end")   # at the last close both had
            break
        if pending == "close":
            close_trade(t, oi[t], oj[t], "converged")
        elif pending in (1, -1):
            pos, entry_t = pending, t
            ni, nj, ref_i, ref_j = 1 / oi[t], 1 / oj[t], oi[t], oj[t]
            trade_pnl = -2 * cost
            pnl[t] -= 2 * cost
        pending = None
        if pos:
            g = pos * (ni * (ci[t] - ref_i) - nj * (cj[t] - ref_j))
            short_val = nj * cj[t] if pos == 1 else ni * ci[t]
            b = short_val * p["borrow_pa"] / 252
            pnl[t] += g - b
            trade_pnl += g - b
            ref_i, ref_j = ci[t], cj[t]
        s = ci[t] / base_i - cj[t] / base_j
        last = t == n - 1
        if pos and last:
            close_trade(t, ci[t], cj[t], "period_end")
        elif pos and s * pos >= 0:
            pending = "close"
        elif not pos and not last and abs(s) > p["open_sd"] * sigma:
            pending = -1 if s > 0 else 1         # i is high -> short i, long j
    return pnl, trades


def simulate(close, opn, m, p=PARAMS_V1, diagnostic=DIAGNOSTIC_PAIRS):
    from stocks import universe
    days = close.index
    month_starts = [d for k, d in enumerate(days) if k and d.month != days[k - 1].month
                    and d >= pd.Timestamp(p["first_trading_month"] + "-01")]
    port_rets, all_trades, picks, diag = [], [], [], {f"{a}/{b}": {"selected": 0, "pnl": 0.0, "trades": 0}
                                                         for a, b in diagnostic}
    for d0 in month_starts:
        k0 = days.get_loc(d0)
        if k0 < p["formation"]:
            continue
        form = close.iloc[k0 - p["formation"]:k0]
        members = universe.members_on(form.index[-1], m) & set(close.columns)
        form = form[sorted(members)].dropna(axis=1)
        trade_idx = days[k0:k0 + p["trading"]]
        pairs = select_pairs(form, p["n_pairs"], p["same_company_corr"])
        picks.append({"month": str(d0.date()), "pairs": [f"{a}/{b}" for a, b, *_ in pairs], "candidates": form.shape[1]})
        total = np.zeros(len(trade_idx))

        def run_pair(a, b, sigma):
            sl = slice(k0, k0 + len(trade_idx))
            return simulate_pair(close[a].to_numpy(float)[sl], close[b].to_numpy(float)[sl],
                                 opn[a].to_numpy(float)[sl], opn[b].to_numpy(float)[sl],
                                 form[a].iloc[-1], form[b].iloc[-1], sigma, p)

        for a, b, _, sigma in pairs:
            pnl, trades = run_pair(a, b, sigma)
            total += pnl
            for tr in trades:
                all_trades.append({"formed": str(d0.date()), "pair": f"{a}/{b}", **tr,
                                   "open_day": str(trade_idx[tr["open_day"]].date()),
                                   "close_day": str(trade_idx[tr["close_day"]].date()),
                                   "days_held": tr["close_day"] - tr["open_day"]})
        port_rets.append(pd.Series(total / p["n_pairs"], index=trade_idx))
        # Descriptive only: the famous pairs, traded by the same rules every month whether picked or not.
        for a, b in diagnostic:
            if a in form.columns and b in form.columns:
                key = f"{a}/{b}"
                diag[key]["selected"] += any({a, b} == {x, y} for x, y, *_ in pairs)
                sigma = float(np.std(form[a] / form[a].iloc[0] - form[b] / form[b].iloc[0], ddof=1))
                pnl, trades = run_pair(a, b, sigma)
                diag[key]["pnl"] += float(pnl.sum()) / 6     # six overlapping portfolios
                diag[key]["trades"] += len(trades)
    daily = pd.concat(port_rets, axis=1).mean(axis=1)
    return daily, pd.DataFrame(all_trades), picks, diag


def summary(daily, trades, spy_close=None):
    r = daily.to_numpy(float)
    monthly = daily.groupby(daily.index.to_period("M")).sum()
    eq = daily.cumsum()
    out = {"days": len(r), "first_day": str(daily.index[0].date()), "last_day": str(daily.index[-1].date()),
           "annual_return": float(r.mean() * 252), "annual_vol": float(r.std(ddof=1) * math.sqrt(252)),
           "sharpe": float(r.mean() / r.std(ddof=1) * math.sqrt(252)),
           "sharpe_per_period": float(r.mean() / r.std(ddof=1)),
           "months": len(monthly), "monthly_t_stat": float(monthly.mean() / monthly.std(ddof=1) * math.sqrt(len(monthly))),
           "max_drawdown": float((eq - eq.cummax()).min()),
           "skew": float(pd.Series(r).skew()), "kurtosis": float(pd.Series(r).kurt() + 3),
           "by_year": {str(y): round(float(g.sum()), 4) for y, g in daily.groupby(daily.index.year)}}
    if spy_close is not None:
        spy = spy_close.pct_change().reindex(daily.index)
        out["corr_with_spy"] = float(daily.corr(spy))
    if len(trades):
        out["pair_trades"] = int(len(trades))
        out["mean_trade_pnl"] = float(trades["pnl"].mean())
        out["trade_win_rate"] = float((trades["pnl"] > 0).mean())
        out["median_days_held"] = float(trades["days_held"].median())
        out["exits"] = trades["reason"].value_counts().to_dict()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--version", default="v1")
    ap.add_argument("--hypothesis", type=int, required=True)
    a = ap.parse_args()
    import backtest
    import ledger
    lconn = ledger.connect()
    if not ledger.get_prediction(lconn, a.hypothesis, a.version):
        raise SystemExit(f"No locked prediction for hypothesis {a.hypothesis} {a.version}; write it first.")
    close, opn, m = load()
    daily, trades, picks, diag = simulate(close, opn, m)
    spy = pd.read_csv(ROOT / "data" / "SPY.csv", parse_dates=["timestamp"])
    spy = spy[spy["timestamp"] < pd.Timestamp(backtest.SEALED_START, tz="UTC")]
    spy_close = pd.Series(spy["close"].to_numpy(), index=pd.to_datetime(spy["timestamp"].dt.date))
    gross_p = dict(PARAMS_V1, cost_bps=0.0, borrow_pa=0.0)
    gross, _, _, _ = simulate(close, opn, m, gross_p, diagnostic=[])
    s = summary(daily, trades, spy_close)
    ledger.record_trial(lconn, a.hypothesis, a.version, s["sharpe_per_period"], s["days"])
    s["deflated_sharpe"] = backtest.deflated_sharpe(s["sharpe_per_period"], s["days"], s["skew"], s["kurtosis"],
                                                    ledger.trial_sharpes(lconn, a.hypothesis))
    out = {"version": a.version, "params": PARAMS_V1, "sealed_start": backtest.SEALED_START, "net": s,
           "gross_no_costs": {k: v for k, v in summary(gross, pd.DataFrame()).items()
                              if k in ("annual_return", "sharpe", "monthly_t_stat", "by_year")},
           "famous_pairs_descriptive": diag,
           "most_picked_pairs": pd.Series([x for pk in picks for x in pk["pairs"]]).value_counts().head(15).to_dict(),
           "candidates_per_formation": [pk["candidates"] for pk in picks[::12]]}
    stem = ROOT / "backtests" / f"pairs_{a.version}-{date.today().isoformat()}"
    stem.with_suffix(".json").write_text(json.dumps(out, indent=2, default=str))
    trades.to_csv(ROOT / "data" / "stocks" / f"pairs_trades_{a.version}.csv", index=False)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
