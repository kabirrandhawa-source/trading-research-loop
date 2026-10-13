# Prediction — spy_prefomc_v1 (ledger id 2), written 2026-10-12, before any backtest

Strategy: strategies/spy_prefomc_v1.py. Long 100% SPY from open(T-1) to open(T+1) around each
scheduled FOMC statement day T, flat otherwise. No stop, no filters, no fitted parameters.
Data: data/SPY.csv dev portion only (2016-01-04 .. 2024-01-29); walk-forward OOS covers roughly
mid-2017 .. Jan 2024 (~52 events). Costs 5 bp one-way (10 bp round trip per event).

Window choice: the engine fills at the next open, so the memo's close(T-1)->close(T) can't be
traded. open(T-1)->open(T+1) is the only window that contains the full published
2pm(T-1)->2pm(T) drift; it also carries the statement/presser reaction and one extra overnight.
Before writing this I checked only the trade count (63 events, all 2-bar holds), not any returns.

## Prior
Weak. The effect was published in 2015 and follow-up work reports it faded; all OOS data is
post-publication, and the 2022 hiking cycle had several bad FOMC days. My honest expectation is
a small positive edge that may not clear the bar below.

## Expected (walk-forward OOS)
- Mean per-event return: about +0.2% net (vs ~+0.1% for a random 2-day SPY hold)
- Annual return: about +1.5% per year (exposure ~16 trading days/year, ~6% of the time)
- Win rate: about 57%
- Max drawdown: about -6% (a handful of bad FOMC weeks at 100% notional)
- OOS annualized Sharpe (daily equity curve incl. flat days): about 0.4
- 2x costs: still positive. Delayed fills (delay=2) are a placebo (window moves post-event):
  I expect that result near zero; a strongly positive delay=2 result is a red flag that the
  edge is generic SPY drift, not FOMC.

## Counts as FAILURE (any one)
1. Walk-forward OOS total return <= 0 after costs.
2. OOS annualized return < 0.8%/yr (≈ what 16 random days of SPY's drift would give).
3. OOS annualized Sharpe < 0.3.
4. OOS win rate < 50%.
5. Return under 2x costs <= 0.

PASS (passed_backtest) only if none of the above trigger. Even then, n≈52 events is weak
evidence, and the sealed test is the human's decision.
