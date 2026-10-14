# Research areas

Standing directions from the human. Research agents read this before proposing ideas.
An area is a direction to explore, not a conclusion. Every idea in it still goes through the
ledger check, the Skeptic, a locked prediction, and the backtest like any other.

## 1. Patient, structural edges on liquid ETFs (main focus)
Holding periods of days to months, effects driven by flows and constraints (rebalancing, index
changes, month-end, mandated hedging), and combinations of several weak, well-documented effects.
This is what the current data (daily ETF bars since 2016) and broker (Alpaca) can test today.

## 2. Speed: being fast where the giants don't bother
Added 2026-10-12. Ledger hypothesis 4 (5-minute Bitcoin prediction markets) is the starting point.

We can't win a microsecond race against firms like Jane Street: our orders travel from a home
Mac over the internet. But "speed" also means reacting within seconds to minutes in places too
small or awkward for big firms:
- short-dated prediction markets (crypto up/down, economic data outcomes) where odds can lag the
  underlying price
- reacting to scheduled releases (CPI, FOMC, jobs) within minutes using sourced event calendars
- intraday bars (Alpaca provides minute bars) for effects that play out over minutes to hours,
  rather than daily bars
- execution quality: limit orders instead of market orders, timing within the day

Questions to answer before anything here can be tested:
- What is our real end-to-end delay (signal → order acknowledged), and how does it compare with
  how long the edge lasts? An edge that closes in 200 milliseconds is not ours.
- Which data do we need (tick or minute data, historical prediction-market odds), where does it
  come from, and what does it cost?
- What are the current fees, and is the venue legally usable from the US? Prediction markets have
  changed fees and access rules for exactly these short crypto markets.
- Is there any way to paper-trade or simulate it, or would testing need real money?

Status 2026-10-12: Kalshi KXBTC15M (15-minute Bitcoin) is the venue under study; Polymarket US is
reported restricted in Massachusetts and Kalshi's status there is being litigated. Data now exists:
`pm/` records order books every second and backfills history (see README). Prediction for
taker-v1 is locked in backtests/pm_taker-v1-prediction.md.

Until data exists for other venues, ideas there should be researched and recorded (papers, venue rules,
fee schedules, measured delays) but marked not testable rather than backtested on daily bars.

## 3. Stocks and crypto signals (added 2026-10-14, new free data)
- **S&P 500 stocks, 2016 onward, point-in-time**: `stocks.universe.members_on(day)` gives the ~500 members on
  any date (companies that later died included); `stocks.universe.prices(tickers)` gives their adjusted daily
  prices, cut at the day each left the index. Cross-sectional ideas (rank all members each month) are now
  testable: momentum, short-term reversal, low volatility, sector-relative strength, index additions/deletions.
  Fundamentals (SEC EDGAR, filing-dated) come later.
- **Crypto**: Coinbase daily prices for BTC, ETH, SOL, XRP, DOGE, and perpetual-futures funding rates
  (Coinbase International since 2023, Kraken for the last 12 months). Funding-rate and basis signals are among
  the better-documented crypto effects; most funding history is in the sealed period, so test designs must
  say how they handle that.
