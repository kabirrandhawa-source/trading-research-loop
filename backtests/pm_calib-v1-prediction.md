# Prediction: calibration screen across 10 Kalshi 15-minute markets (hypothesis 5)

Written 2026-10-13, before any analysis of these series' data. (Bitcoin is excluded: its
development data was already examined for hypothesis 4.)

## The test (pm/calibrate.py, fixed in advance)
- Series: ETH, SOL, XRP, DOGE, gold, silver, oil, EUR/USD, USD/JPY, GBP/USD.
- Development windows only: first 70% of each series by time (about Sep 29 - Oct 9). Last 30% sealed.
- One row per window per 10-cent price bucket (first minute the mid enters it), from the second
  minute to the close. Buy YES at the ask or NO at 1 - bid, hold to settlement, pay the taker fee.
- 10 series x 10 buckets x 2 sides, up to 200 tests. A lead needs Bonferroni-adjusted p < 0.05
  across all tests, profit of at least 1c per contract after fees, and at least 30 windows.

## What I expect
1. No leads. Nothing clears the corrected bar.
2. Most tests lose money after fees: fewer than 35% of tests show positive profit per contract.
3. Calibration gaps (actual minus market) within +/- 5 points in the 20-80c buckets for every series,
   once sampling error is allowed for.
4. If anything shows up, it is a longshot effect: contracts priced under 10c win less often than
   their price implies (so buying the opposite side at 90c+ is the least-bad trade), but too small
   to beat fees.
5. The less-traded series (silver, oil, GBP/USD, DOGE) show larger but noisier gaps than ETH/EUR/USD.

## What counts as a pass
At least one lead as defined above. A pass makes that specific series/bucket/side a candidate for
its own sealed test, with human approval. Anything less is a fail for calib-v1.
