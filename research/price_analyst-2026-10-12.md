# Price Analyst memo, 2026-10-12

Universe scanned: SPY QQQ IWM DIA TLT IEF GLD XLK XLF XLE XLV XLY XLP XLU XLI.
Data: development copies only (daily bars 2016-01-04 to 2024-01-29). The sealed data/ folder was not opened.
Ledger checks: `ledger.py search --market "QQQ"`, `--market "QQQ" --status failed`, and `--text "IBS"` all returned nothing, so this idea has not been tested before.

## Idea (ledger id 3): QQQ low-IBS one-day mean reversion

**One sentence:** Buy QQQ at the close when its daily internal bar strength (IBS = (close-low)/(high-low)) is below 0.2, hold it for one day, and stay flat otherwise.

**Why it might work:** When a liquid index ETF closes near its daily low, part of that move is often short-term selling pressure (liquidity demand, stop-outs, end-of-day rebalancing) rather than news. That pressure tends to reverse over the next session. Large-cap equity indexes with a long-run upward drift, like QQQ, have shown this short-horizon mean reversion more strongly than bonds or gold.

**Conditions it needs:**
- Equity markets in a "buy-the-dip" regime: upward drift or range-bound, with normal intraday ranges.
- It works less well in persistent sell-offs where weakness continues for several days. In the dev data, 2022 had a Sharpe of -0.3 and 2019 about 0.
- Costs must stay low: trading at the close with about 5 bp per side or less. About 37 round trips a year.

**Rule parameters (daily bars, single ticker, long-or-flat, uses only the current and past bars):**
- Signal at bar t: IBS_t = (close_t - low_t) / (high_t - low_t). If high_t == low_t, there is no signal.
- If IBS_t < 0.20: hold long 100% from close t to close t+1. Otherwise: flat.
- Re-evaluate every day. Consecutive signals keep the position open.
- No stop and no trend filter. The 0.20 threshold was fixed before the sensitivity sweep, not chosen from it.

**What proves it wrong:** On the sealed out-of-sample period, any one of these refutes the idea:
- Sharpe at or below 0.3 after 5 bp per side.
- Mean next-day return after IBS<0.2 days not above the unconditional mean daily return.
- Sharpe falling below 0 when the threshold is moved to 0.15 or 0.30 (that would show it is fragile).

## Dev-data evidence (in-sample only, treat with suspicion)
- QQQ, IBS<0.2, 5 bp cost: Sharpe 0.92, about 10.5% annualised, 18% time in market. Buy-and-hold Sharpe was 0.90.
- Mean next-day return: 0.32% after IBS<0.2 (n=361), 0.08% unconditional, and 0.00% after IBS>0.8.
- Threshold sweep, Sharpe: 0.1 gives 0.74, 0.15 gives 0.82, 0.2 gives 0.92, 0.25 gives 0.87, 0.3 gives 0.97. The result changes smoothly with the threshold and does not hinge on one value.
- At 10 bp cost, Sharpe is 0.59.
- By year, Sharpe was positive in 2016-18, 2020, 2021 and 2023. It was about 0 in 2019, negative in 2022, and negative in the short 2024 stub.

## Data-snooping disclosure
I looked at 2 rule families (IBS<0.2 next day, and RSI(2)<10 above the 200-day SMA with exit above the 5-day SMA) across 15 tickers, which is 30 combinations. I then ran a 5-point threshold sweep and a by-year split on QQQ and XLK, another 10 threshold variants. That is about 40 variants in total.

XLK scored best (Sharpe 1.16). I deliberately chose QQQ, which is broader and more liquid, rather than the top scorer, to reduce selection bias.

The same rule did nothing on SPY (0.07), DIA (0.08) or IWM (0.23), and was negative on IEF, GLD and XLI. That is a real warning sign: the effect may be specific to tech and to this period. Discount the in-sample Sharpe heavily. A fair out-of-sample expectation is well below 0.9.
