# Prediction: S&P 500 long-only momentum + cash profitability, v1 (hypothesis 15)

Written 2026-10-16 by desk-quant, after writing strategies/momo_quality_v1.py, stocks/momo_quality.py
and their tests (hand-built frames only), BEFORE running the strategy on any real price data. The only
real-data query run so far is the fundamentals.latest() stale-year count (filings only, no prices or
returns). Version 1; counts against the 5-variation limit. No parameter will be changed after results.

## The test (fixed in advance; full rules in the strategy docstring)
- Universe: point-in-time S&P 500 members on each month-end (stocks.universe.members_on), dead companies
  included; Alpaca daily bars adjusted for splits and dividends (so stock and SPY returns are both
  total-return-like). Only rows before 2024-01-30.
- Formation each month-end close 2016-12-30 .. 2023-12-29 (85 formations); hold to the next month-end
  close; last holding ends 2024-01-29. 12-1 momentum (t-12 anchor for the first formation = 2016-01-04).
- Top decile = round(N/10) by 12-1 return; keep names with 10-K OCF / total assets at or above the median
  of all members that have it (newest fiscal year in a 10-K filed by t and within 15 months, via the new
  fundamentals.latest_annual; assets from the same filing). Uncovered names dropped. Equal weight.
- Index exits sold at their last close (cash at 0% to month-end). Costs 10 bps per side on traded weight
  and exit sales; 20 bps also reported. One-sided monthly turnover reported.
- Benchmark: SPY over the same month-end to month-end windows. CAPM with risk-free = 0 (no T-bill series).
- Comparison basket: pure top decile, equal weight (pre-specified, not a variation).
- Robustness: sector-neutral weights (return-based sectors from 8 SPDRs, rules in the docstring) and a
  25% tech cap, same costs.
- Deflated Sharpe on monthly excess vs SPY; trials = h15 trials + the pure-momentum basket as a
  stand-in for hypothesis 12's related momentum sample (h12 is untested, no recorded Sharpe) + any h12
  recorded trials.

## The bar (all three must hold for passed_backtest; anything else = failed)
Net of 10 bps per side:
1. Monthly excess return vs SPY has t-stat > 2 (plain t on 85 monthly differences).
2. CAPM alpha vs SPY (monthly, OLS) is positive.
3. CAPM alpha of the SECTOR-NEUTRAL weighting is also positive.

Also reported, not part of the pass/fail bar (they are the memo's original claim): screened CAGR above
SPY's, and screened max drawdown shallower than the pure-momentum basket's.

## What I honestly expect (central guess, with a rough range)
- Screened basket CAGR net 10 bps: about 14% a year (range 9% to 19%); SPY about 13-14% over these months.
- Monthly excess vs SPY: about +0.5% a year (range -4% to +5%); tracking error 10-14% a year;
  excess t-stat about 0.2 (range -1 to 1.5). t > 2 would need an information ratio near 0.75: unlikely.
- CAPM beta 0.95 to 1.15; alpha about +0.5% a year with t well below 2. Sign could go either way.
- Sector-neutral alpha: smaller than the equal-weight alpha (momentum's 2020-21 tech and 2022 energy tilts
  are removed); sign a coin flip.
- Win rate: beats SPY in about 50% of months (range 42% to 58%); positive in about 63% of months.
- Max drawdown on monthly marks: about -25% (range -18% to -35%), similar to SPY's (about -24%, 2022).
  Pure momentum about -28%. I give roughly even odds that the screen gives a shallower drawdown.
- Turnover: one-sided about 40-60% a month; costs at 10 bps cost about 1% a year, at 20 bps about 2%.
- Coverage: about 5-15% of top-decile names dropped for missing 10-K OCF/assets, more in 2017.
  Index exits from held names: a handful (under 15 in total).
- Worst months: March 2020 and one of 2022 (or Jan 2023 momentum reversal) for excess.
- Deflated Sharpe on excess vs SPY: well under 0.95.
- Probability the bar passes: about 10%.

## What would make me suspicious of a pass
Excess t > 2 driven by one or two months (check the worst/best months and by-year table); a big gap
between sector-neutral and equal-weight alpha (a sector bet, not momentum/quality); coverage gaps that
skew toward later-dead firms (survivorship in the screen); any position marked after 2024-01-29.

A pass earns Skeptic review and then the sealed test (2024-01-30 onward) only with Kabir's explicit yes.
Never real money directly.
