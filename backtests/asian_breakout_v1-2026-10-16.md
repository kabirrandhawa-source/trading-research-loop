# asian_breakout_v1 (2026-10-16): FAILED

Hypothesis 9. Rules: intraday/asian_breakout.py PARAMS_V1. Prediction locked before the run:
backtests/asian_breakout_v1-prediction.md. Raw numbers: backtests/asian_breakout_v1-2026-10-16.json;
trades: data/intraday/trades_v1.csv. Dukascopy DAX and UK100 CFD bars, 2013-01-01 to 2024-01-29
(development only). Days without overnight quotes are skipped (about 1,800 symbol-days, mostly
mid-2015 to mid-2018), so the sample is effectively 2013-15 and mid-2018 to Jan 2024.

## Result vs the pass bar
| | DAX | UK100 | Pooled | Pass bar |
|---|---|---|---|---|
| Trades | 1,371 | 1,481 | **2,852** | 300+ |
| Mean R per trade, after costs | -0.057 | -0.126 | **-0.093** | > 0 |
| t-stat | -1.6 | -3.8 | **-3.8** | > +3 |
| Win rate (2R target; 33.3% breaks even before costs) | 34.9% | 34.2% | 34.5% | |
| Total R | -78 | -186 | **-264** | |
| Longest losing streak | 11 | 13 | 13 | |
| Positive years (20+ trades) | 3 of 9 | 2 of 9 | 2 of 9 | 2/3 of years |

The loss is statistically clear (t = -3.8): this isn't "no edge", it reliably loses money once you pay the
spread. At the post's sizing of 1% risk per trade, -264R over ~10 years means losing most of the
account; the worst drawdown was about 300R.

## Why
- Before costs it is break-even: about +0.015R a trade (win rate 34.5% vs 33.3% needed). The breakout
  carries no information about the next few hours.
- Costs then decide it: the quoted spread (~1 point on both) plus 0.5 point slippage each side is about
  0.07R a trade on the DAX (median stop 35 points) and 0.14R on the UK100 (median stop 17 points).
  Tight stops on breakout candles make the fixed spread a big fraction of the risk.
- 62% of trades hit the stop, 25% the target, 14% were closed at 16:30.
- Recent years are the worst: pooled 2021 -74R, 2022 -47R, 2023 -90R. Only 2014 and 2020 were positive.

## Prediction check
1. Signals on 50-70% of covered days: slightly wrong, about 77%.
2. Win rate 30-36%: right (34.5%).
3. Mean R -0.10 to +0.05, t below 2: right (-0.093; t is -3.8, significantly negative).
4. No consistency, signs flip: right (DAX 2014 +0.15R vs UK100 -0.12R; 2 of 9 years positive).
5. No edge; the post's claim is not supported: right.

## Lesson
The "every morning" Asian-range breakout is a coin flip before costs and a steady loser after them.
Tight breakout-candle stops make the spread a large share of each trade's risk. The $300k/year claim
is not reproducible from the rules as described.
