# Prediction: S&P 500 pairs trading, distance method, v1 (hypothesis 11)

Written 2026-10-15, after writing stocks/pairs.py and its tests (synthetic prices only), before
running it on any real price data.

## The test (fixed in advance)
- Rules exactly as stocks/pairs.py PARAMS_V1 (Gatev, Goetzmann & Rouwenhorst 2006): monthly formation
  on the previous 252 days over point-in-time S&P 500 members (dead companies included); top 20 pairs
  by sum of squared differences of normalized prices, share classes of one company excluded; trade the
  next 126 days; open at 2 formation sd at the next open, close at the next open after the spread
  crosses; 5 bps per leg per trade, 0.5%/yr borrow on the short. Return on committed capital, six
  overlapping monthly portfolios averaged.
- Data: Alpaca adjusted daily bars 2016-01-04 to 2024-01-29 (development only). First trading month
  2017-01; about 85 months. Nothing on/after 2024-01-30 is read.
- One version. No tuning of thresholds, pair count or windows on this data.

## What I expect
1. Gross (no costs): about +1% to +4% a year on committed capital; well below the paper's ~11% (1962-2002).
2. Net: about -1% to +2% a year; Sharpe below 0.5; monthly t-stat below 2.
3. Close to zero correlation with SPY (|corr| < 0.2), with losses clustered in 2020 (COVID dispersion).
4. Many trades end at the period end without converging (over 30%), as pairs drift apart for good.
5. KO/PEP and HD/LOW are picked in only a minority of months, and by themselves earn little.

## What counts as a pass
Net annual return > 0 with monthly t-stat above 3; Sharpe after costs above 1; positive in at least 5
of 7 full years (2017-2023); |corr with SPY| below 0.3. A pass earns Skeptic review, then the sealed
test (2024-01-30 onward) only with Kabir's explicit yes. Never money directly.
