# Prediction: Claude discretionary sleeve v2, "full research" (hypothesis 10)

Written 2026-10-15, before Claude made any sleeve v2 decision. Proposal approved by Kabir in chat on
2026-10-15: research/claude-sleeve-v2-proposal-2026-10-15.md.

## The experiment (fixed in advance)
- $10,000 of the paper account, separate from sleeve v1 (hypothesis 7) and the SPY benchmark.
  Universe: QQQ, IWM, DIA, TLT, IEF, GLD and the 8 sector SPDRs (not SPY). Long only, at most 4
  positions, each at most 40% of the sleeve. Same rules, schedule and scoring as v1.
- Change ONE thing versus v1: the inputs. Each weekday at 16:25 ET Claude reads sleeve.context_v2:
  everything v1 sees (90 days of prices, trend and volatility stats, the last day's headlines, its
  holdings) plus ledger lessons and statuses, the latest research memos, the latest daily summary,
  the morning brief, sector fundamentals (SEC filings, current large holdings of the 8 sector SPDRs),
  crypto prices and funding, TimesFM forecasts if any (labeled as a failed test, hypothesis 6), and
  its own past decisions and scored values. It may also use TradingView read tools and at most 6 web
  searches. sleeve.decide rejects anything outside the rules. The 17:00 job executes through the kill
  switch; orders fill at the next open. Claude never places orders.
- Forward test only. Period: 12 weeks from v2's first decision (about 2026-10-15 to 2027-01-07).
- Scored by sleeve.evaluate against SPY's price change over the same days (dividends ignored for
  both), and against v1 over the days both sleeves have values.

## What I expect
1. v2 does not beat SPY: excess return between -4 and +1 percentage points over 12 weeks.
2. v2 and v1 finish within 2 percentage points of each other (more information, little difference).
3. v2 trades more than v1 (more inputs, more reasons to change).

## What counts as a pass
v2 beats SPY by at least 2 percentage points AND beats v1 by at least 2 percentage points over the
12 weeks, with a max drawdown no worse than SPY's. Even a pass is weak evidence (12 weeks, about 60
decisions, one market regime; a 2-point gap between v1 and v2 may be noise): it would earn a longer
forward test, never real money.
