# Prediction: Kalshi 15-min Bitcoin, taker strategy v1 (hypothesis 4)

Written 2026-10-12, before any analysis of real data was run.

## The test
- Data: 14 days of settled KXBTC15M windows (first 70% development, last 30% sealed),
  Kalshi 1-minute odds, 2 days of Kalshi trades, Kraken BTC/USD trades as the spot proxy.
- Strategy taker-v1: each minute, if model probability minus the ask exceeds 3c plus the taker
  fee, buy that side; one entry per window; hold to settlement. Reported with two fill
  assumptions: same-minute ask (no delay) and next-minute ask (60s delay).

## What I expect
1. Lead/lag: the market's 1-second changes line up with spot-implied odds at a lag of 0-2 s.
   A lag of 5 s or more would surprise me.
2. Calibration: the market is well calibrated. The model alone scores a worse Brier than the
   market; the 50/50 blend improves on the market by less than 2%.
3. Taker sim, next-minute fills: loses money, about -1c to -3c per contract after fees.
4. Taker sim, same-minute fills: around break-even, between -1c and +1c per contract.

## What counts as a pass (the idea is worth pursuing further)
All of these, on development data:
- next-minute fills: profit of at least +0.5c per contract after fees, t-stat above 3,
  at least 100 trades;
- lead/lag peak at 2 s or more;
- blend Brier at least 2% better than the market's.

Anything less is a fail for taker-v1. A fail on (3) with a pass on (1) would point to a
second-level or maker strategy instead (taker-v2 or maker-v1), each needing its own prediction.
