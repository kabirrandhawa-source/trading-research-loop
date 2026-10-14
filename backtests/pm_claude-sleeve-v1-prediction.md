# Prediction: Claude discretionary sleeve (hypothesis 7)

Written 2026-10-14, before Claude made any sleeve decision.

## The experiment (fixed in advance)
- $10,000 of the paper account. Universe: QQQ, IWM, DIA, TLT, IEF, GLD and the 8 sector SPDRs (not SPY,
  which the benchmark holds). Long only, at most 4 positions, each at most 40% of the sleeve.
- Each weekday at 16:25 ET Claude reads sleeve.context (90 days of prices, trend and volatility stats,
  the last day's headlines, its holdings) and writes target weights with reasoning. sleeve.decide
  rejects anything outside the rules. The 17:00 job executes through the kill switch; orders fill at
  the next open. Claude never places orders.
- Forward test only: a backtest would be meaningless because the model already knows how the past
  went. Period: 12 weeks from the first decision (about 2026-10-14 to 2027-01-06).
- Scored by sleeve.evaluate against SPY's price change over the same days (dividends ignored for both).

## What I expect
1. The sleeve does not beat SPY: excess return between -4 and +1 percentage points over 12 weeks.
2. More turnover than needed: at least 10 rebalancing orders over the period.
3. Max drawdown similar to or smaller than SPY's (diversification and cash), within 2 points.
4. Its reasoning will often cite recent trend and news that are already in the price.

## What counts as a pass
Beats SPY by at least 2 percentage points over the 12 weeks AND a max drawdown no worse than SPY's.
Even a pass is weak evidence (12 weeks, one market regime): it would earn a second, longer forward
test, not real money.
