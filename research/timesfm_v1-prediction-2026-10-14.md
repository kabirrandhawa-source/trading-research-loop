# Prediction: TimesFM 3.0 next-day ETF forecasts (hypothesis 6, strategies/timesfm_v1.py)

Written 2026-10-14, before any forecast was generated.

## The test (fixed in advance)
- Model: Google TimesFM 3.0 (330M, google/timesfm-3.0-pytorch), zero-shot, default settings,
  univariate. Context: the 512 daily log closes ending at day t; forecast: log close at t+1.
- Data: 15 ETFs in universe.txt, development period only (Jan 2018 - Jan 29 2024; 22,800 forecasts).
  Nothing on or after 2024-01-30 (sealed) goes into the model.
- Signal: forecast minus today's log close.
- Scoring (tsfm/evaluate.py): daily cross-sectional rank IC across the 15 ETFs; per-ETF correlation;
  hit rate vs always guessing "up"; correlation with yesterday's move; 80% band coverage.
- Trading (backtest.py run, SPY): long when the signal is above 0, flat otherwise, next-open fills,
  5 bps costs, walk-forward, stress tests, Deflated Sharpe. Compared with SPY buy-and-hold through
  the same folds, sizing and costs.

## What I expect
1. No usable information: mean cross-sectional IC between -0.02 and +0.02, |t| below 2.
2. Hit rate within 1 percentage point of always guessing "up".
3. The forecast mostly echoes recent movement: |correlation with yesterday's move| above 0.2
   (sign could be either way: trend-following or mean-reverting).
4. Ranges are reasonable: 80% band coverage between 70% and 90%. The model should be better at
   how much prices move than at which direction.
5. SPY long/flat: lower walk-forward Sharpe than buy-and-hold (it sits out many up days and pays
   costs on switches); Deflated Sharpe below 0.5.

## What counts as a pass
All of: cross-sectional IC t-stat above 3; SPY walk-forward Sharpe above buy-and-hold's; Deflated
Sharpe above 0.95.

Contamination caveat, decided now: TimesFM 3.0's training data may include these ETF price histories
through its training cutoff, which is likely after this development period. A pass here is therefore
necessary but NOT sufficient. It would also need the one-time sealed test (Jan 2024 onward) and at
least 8 weeks of forward paper trading on prices the model cannot have seen.
