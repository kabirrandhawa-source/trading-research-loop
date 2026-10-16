"""S&P 500 long-only momentum plus cash profitability, v1 (ledger hypothesis 15).

Cross-sectional and monthly, so it does not run in the single-asset bar engine (backtest.run).
The development backtest is stocks/momo_quality.py, which calls the pure functions below.
Rules, fixed before any test (spec = researcher design lesson + skeptic lesson, 2026-10-16):

- Formation at each month-end close t (last trading day of the month), 2016-12-30 .. 2023-12-29.
  Candidates: point-in-time S&P 500 members on t (stocks.universe.members_on), dead companies included.
- 12-1 momentum = close(month-end t-1) / close(month-end t-12) - 1 (the latest month skipped).
  Prices start 2016-01-04, so the t-12 anchor for the 2016-12-30 formation is 2016-01-04 (one trading
  day after 2015-12-31). Anchor closes may be forward-filled up to 5 trading days; the close on t itself
  must be a real bar (the buy price).
- Top decile = the round(N/10) members with the highest 12-1 return (ties by ticker).
- Profitability = annual operating cash flow / total assets, both from the newest fiscal year in a 10-K
  filed on or before t and within the prior 15 months (stocks.fundamentals.latest_annual), assets from
  the same filing and fiscal year end (else any 10-K with that year end filed by t); assets > 0.
- Screen: keep top-decile names whose profitability is at or above the MEDIAN of all members on t that
  have it ("top half of members"). Top-decile names without coverage are dropped, not kept.
- Equal weight, bought at the close on t, held to the next month-end close; the last holding ends at
  2024-01-29 (last development day). A name whose bars stop inside the month (it left the index) is
  sold at its last close; the cash earns 0 until month-end.
- Costs 10 bps per side on traded weight (rebalance trades and exit sales); stress 20 bps.
- Comparison basket (pre-specified): the same top decile, unscreened, equal weight.
- Robustness (not a different rule): sector-neutral weights. Sector = the sector SPDR (XLK XLF XLE XLV
  XLY XLP XLU XLI) whose daily return minus SPY correlates most with the stock's return minus SPY over
  the 252 trading days to t (min 126 days); best correlation below 0.10 -> "other". Each sector in the
  basket gets its share of the momentum-eligible members, renormalized over sectors present; names are
  equal weight within a sector. Tech cap (also reported): XLK names capped at 25% in total.
"""
import math

import numpy as np
import pandas as pd

from strategies.base import Strategy

PARAMS = dict(decile=0.10, prof_quantile=0.50, max_age_months=15, anchor_ffill_days=5,
              cost_bps=10.0, stress_cost_bps=20.0, sector_lookback=252, sector_min_days=126,
              sector_min_corr=0.10, tech_cap=0.25,
              sector_etfs=("XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLU", "XLI"),
              first_formation="2016-12-30", last_hold_end="2024-01-29")


class MomoQualityV1(Strategy):
    NAME = "momo_quality"
    VERSION = "v1"
    HYPOTHESIS = ("S&P 500 long-only: top-decile 12-1 momentum, keep the top half by 10-K OCF/assets, "
                  "equal weight, monthly; beats SPY after 10 bps/side with t>2 and positive CAPM alpha.")
    HYPOTHESIS_ID = 15
    stop_loss_pct = None
    max_position_pct = 100.0
    params = PARAMS

    def entry(self, bars):
        raise NotImplementedError("Cross-sectional strategy: run with `python -m stocks.momo_quality run`.")


# ---------- pure rule functions (tested in tests/test_momo_quality_v1.py) ----------

def momentum_12_1(anchor_closes, k):
    """anchor_closes: DataFrame indexed by [first day] + month-ends, columns tickers, forward-filled.
    Return at anchor index k (formation) = close[k-1] / close[k-12] - 1; NaN where either is missing."""
    if k < 12:
        raise ValueError("12-1 momentum needs 12 earlier anchors")
    return anchor_closes.iloc[k - 1] / anchor_closes.iloc[k - 12] - 1


def select(mom, prof, decile=PARAMS["decile"], prof_quantile=PARAMS["prof_quantile"]):
    """mom: 12-1 returns of members (NaN = no history). prof: OCF/assets of members with coverage.
    Returns (top_decile, screened, uncovered), each a list of tickers in momentum order."""
    mom = mom.dropna()
    prof = prof.dropna()
    n = max(1, int(round(len(mom) * decile))) if len(mom) else 0
    order = sorted(mom.index, key=lambda t: (-mom[t], t))
    top = order[:n]
    cut = prof.quantile(prof_quantile) if len(prof) else math.inf
    screened = [t for t in top if t in prof.index and prof[t] >= cut]
    uncovered = [t for t in top if t not in prof.index]
    return top, screened, uncovered


def equal_weights(names):
    return pd.Series(1.0 / len(names), index=list(names)) if len(names) else pd.Series(dtype=float)


def sector_neutral_weights(names, sector, universe_sector):
    """names: basket. sector: ticker -> sector label. universe_sector: labels of the eligible universe.
    Each sector present in the basket gets its universe share (renormalized); equal within sector."""
    if not len(names):
        return pd.Series(dtype=float)
    lab = pd.Series({t: sector.get(t, "other") for t in names})
    share = pd.Series(list(universe_sector)).value_counts(normalize=True)
    present = share.reindex(lab.unique()).fillna(0.0)
    if present.sum() <= 0:
        return equal_weights(names)
    present = present / present.sum()
    return pd.Series({t: present[lab[t]] / (lab == lab[t]).sum() for t in names})


def tech_capped_weights(names, sector, cap=PARAMS["tech_cap"], tech="XLK"):
    w = equal_weights(names)
    if not len(w):
        return w
    is_tech = pd.Series({t: sector.get(t) == tech for t in w.index})
    tw = w[is_tech].sum()
    if tw <= cap or is_tech.all():
        return w
    w[is_tech] *= cap / tw
    w[~is_tech] *= (1 - cap) / w[~is_tech].sum()
    return w


def assign_sectors(stock_rets, etf_rets, spy_rets, min_days=PARAMS["sector_min_days"],
                   min_corr=PARAMS["sector_min_corr"]):
    """Daily returns over the lookback (rows = days). Sector = ETF whose (ret - SPY) correlates most
    with the stock's (ret - SPY). Returns {ticker: label}; too little history -> 'other'."""
    er = etf_rets.sub(spy_rets, axis=0)
    out = {}
    for t in stock_rets.columns:
        s = (stock_rets[t] - spy_rets).dropna()
        if len(s) < min_days:
            out[t] = "other"
            continue
        c = er.loc[s.index].corrwith(s)
        out[t] = c.idxmax() if c.notna().any() and c.max() >= min_corr else "other"
    return out


def hold(close, t0, t1, weights):
    """Hold `weights` (bought at the close on t0) to the close on t1. close: raw daily closes (NaN
    where no bar). A name whose last bar in (t0, t1] is before t1 is sold at that close.
    Returns dict: gross return, per-name returns, end weights (as fraction of end value; exited names
    absent), exited names, exit value (fraction of START value) that was sold."""
    rets, exited, exit_val = {}, [], 0.0
    for t, w in weights.items():
        p0 = close.at[t0, t]
        win = close.loc[(close.index > t0) & (close.index <= t1), t].dropna()
        if not len(win):
            r, last = 0.0, None
        else:
            r, last = win.iloc[-1] / p0 - 1, win.index[-1]
        rets[t] = r
        if last is None or last < t1:
            exited.append(t)
            exit_val += w * (1 + r)
    rets = pd.Series(rets, dtype=float)
    gross = float((weights * rets).sum())
    held = [t for t in weights.index if t not in exited]
    end_w = weights[held] * (1 + rets[held]) / (1 + gross) if held else pd.Series(dtype=float)
    return {"gross": gross, "rets": rets, "end_weights": end_w, "exited": exited, "exit_value": exit_val}


def traded_weight(target, drifted):
    """Sum of |weight change| at a rebalance (buys + sells), as a fraction of portfolio value."""
    idx = target.index.union(drifted.index)
    return float((target.reindex(idx).fillna(0) - drifted.reindex(idx).fillna(0)).abs().sum())


def capm(port, mkt, nw_lags=3):
    """OLS port = a + b * mkt (monthly, risk-free taken as 0). Returns alpha, beta, OLS and
    Newey-West t-stats for alpha."""
    y, x = np.asarray(port, float), np.asarray(mkt, float)
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ coef
    n = len(y)
    xtx_inv = np.linalg.inv(X.T @ X)
    s2 = e @ e / (n - 2)
    se = np.sqrt(np.diag(xtx_inv) * s2)
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, nw_lags + 1):
        wgt = 1 - L / (nw_lags + 1)
        G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += wgt * (G + G.T)
    nw = np.sqrt(np.diag(xtx_inv @ S @ xtx_inv) * n / (n - 2))
    return {"alpha_monthly": float(coef[0]), "beta": float(coef[1]), "alpha_t": float(coef[0] / se[0]),
            "alpha_t_newey_west": float(coef[0] / nw[0]), "beta_t": float(coef[1] / se[1]),
            "r2": float(1 - e @ e / ((y - y.mean()) @ (y - y.mean())))}


def t_stat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))) if len(x) > 1 and x.std(ddof=1) > 0 else 0.0


def max_drawdown(monthly):
    eq = np.cumprod(1 + np.asarray(monthly, float))
    eq = np.concatenate([[1.0], eq])
    return float((eq / np.maximum.accumulate(eq) - 1).min())
