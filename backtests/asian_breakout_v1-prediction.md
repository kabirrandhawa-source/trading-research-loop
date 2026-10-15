# Prediction: Asian-range breakout on DAX and UK100, v1 (hypothesis 9)

Written 2026-10-15, after writing intraday/asian_breakout.py and before running it on any data.
(The only data looked at: three single days, to check the feed's format and which hours it covers.)

## The test (fixed in advance)
- Rules exactly as in intraday/asian_breakout.py PARAMS_V1: box = 00:00-07:00 London high/low (mid);
  signal = first 15-min candle starting 08:00-09:45 London that closes outside the box in its own
  direction with body >= 50% of its range; enter next 5-min open at ask/bid + 0.5 pt slippage; stop =
  the candle's far end; target 2R; flat 16:30 London; stop assumed first when both hit in one bar.
- Data: Dukascopy DAX (DEU.IDX) and UK100 (GBR.IDX) CFD minute bars, 2013-01-01 to 2024-01-29 (all
  development; the sealed period from 2024-01-30 is not downloaded). The feed has no overnight
  quotes for roughly 2015 to mid-2018; those days are skipped (Asian window < 80% covered).
- One version. No parameter tuning on this data. Alternative stop modes, R targets or "whole candle
  outside" are NEW versions and count as extra variations.

## What I expect
1. Signals on roughly 50-70% of covered days per index (most days drift out of a 7-hour overnight box
   within the first two hours).
2. Win rate 30-36% at a 2R target; break-even needs about 33.3% before costs.
3. Mean R per trade between -0.10 and +0.05 after spread and slippage; t-stat below 2.
4. No consistency across years: some years positive, some negative, sign flips between the indices.
5. Overall: no edge. The post's claim (works every day, $300k/yr) is not supported.

## What counts as a pass
Pooled mean R > 0 with t-stat above 3 over at least 300 trades, after costs; positive mean R on each
index separately; positive in at least 2/3 of years with 20+ trades. A pass earns Skeptic review,
then the sealed test (2024-01-30 onward) only with Kabir's explicit yes, never money directly.
