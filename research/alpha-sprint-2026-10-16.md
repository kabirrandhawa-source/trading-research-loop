# Alpha sprint: three structural leads (2026-10-16)

Researcher memo. Three hypotheses registered: **14** (crypto funding carry), **15** (long-only momentum
plus cash profitability), **16** (filing-date PEAD). No backtests were run, no predictions were locked,
and no sealed rows were read. The only crypto query counted rows dated before 2024-01-30.

Ledger check: searches for funding, carry, basis, momentum, quality, profitability, earnings, drift,
SUE and PEAD found nothing failed or dropped that these repeat. Related items:
- H12 (risk-managed long-short momentum, untested). H15 differs because it is long-only, has no
  volatility scaling, and adds a quality screen. It reuses the same momentum sample, so it should count
  as a related trial when computing the Deflated Sharpe.
- H1 (XLF earnings window, dropped) and H2 (pre-FOMC drift, failed) are event-calendar ETF ideas,
  not stock-level earnings drift.

---

## H14: Crypto funding carry, delta-neutral (research only)

**Idea.** For BTC and ETH, hold spot long and an equal-notional Coinbase International perpetual short
while the trailing 7-day mean funding rate, annualized, is above 10%. Exit when it falls below 0%.

**Why it might work.** Perpetual funding pays shorts when leveraged longs crowd in. Schmeling, Schrimpf
& Todorov (BIS WP 1087, 2023) find BTC/ETH carry averages above 10% a year, sometimes 40-60%. They
attribute it to trend-chasing retail demand for leverage and scarce arbitrage capital. Both are
structural, not prediction-based.

**Conditions needed.** Bullish, leveraged markets where funding stays positive and persistent.
Funding near zero (most of 2023) means no trade.

**Data and sealing (plain statement).** Most of our funding history is sealed. Coinbase Intl funding
starts 2023-03-22 for BTC/ETH. That leaves **about 10.3 usable development months**
(2023-03-22 to 2024-01-29, 7,532 hourly rows per coin). XRP has about 6 months, SOL about 2.5 and
DOGE about 2, too short to use. The db has no perp mark price or basis history, so the test must
assume a perfect hedge. It also needs a 10 bps adverse-basis stress on every entry and exit.

**Can a threshold version be tested honestly?** Only as a single pre-registered rule (in above 10%,
out below 0%) with no grid search. Ten months of strongly autocorrelated funding hold a few regimes at
most, so any tuned threshold would be fitted to noise. Treat development as a plumbing and cost
check. Real evidence has to come from funding recorded forward from today (Coinbase Intl plus Kraken).

**Costs.** Coinbase Advanced spot taker fee is 0.60% at the entry tier (maker 0.40%). The Coinbase
Intl perp taker fee is about 0.03-0.05% (promotional and unverified). Half-spread is about 1-2 bps.
One round trip of both legs costs about 1.3% of notional. At 10% annualized funding that is about
7 weeks of carry just to break even. Rebalancing when the legs drift more than 5% apart is charged at
the same rates. Stress the result at 2x costs.

**Benchmark.** T-bills, since this is a market-neutral carry trade. SPY is shown for context only.

**Proved wrong if** net return on gross capital (spot plus 100% perp margin) is at or below T-bills
in development, or turns negative at 2x costs. A pass would still be weak evidence.

**Tradability.** Alpaca cannot trade this. It offers spot crypto only (taker 0.25% at tier 1), with
no crypto shorting and no perps. Coinbase International is not open to US retail. Coinbase's
CFTC-regulated US perpetual-style futures (2025) would be the legal venue, but we have no history for
them. **Research only.**

**Main weakness.** The large funding years (2024-25) are sealed, and 2023 was a low-funding year, so
the development result says little either way. A funding-only P&L also hides the real risk: the short
perp leg can be liquidated in a fast rally, because spot and perp sit on separate venues with no
cross-margin.

---

## H15: S&P 500 long-only momentum plus cash profitability

**Idea.** Each month-end, take the top decile of point-in-time S&P 500 members by 12-1 month return.
Keep the names in the top half of members by profitability, measured as latest 10-K operating cash
flow / total assets, filed by the formation date. Hold them equal weight for one month. The pure
top-decile momentum basket is the single pre-specified comparison.

**Sources.** Jegadeesh & Titman (1993) for momentum. Novy-Marx (2010 WP, JFE 2013) for gross
profitability. Ball, Gerakos, Linnainmaa & Nikolaev (JFE 2016) show that cash-based operating
profitability predicts returns at least as well as accrual-based measures.
**We have no gross-profit or COGS tag in our EDGAR pull, so the screen is OCF/assets, not Novy-Marx GP.**
Quality tends to do well when momentum crashes (junk rallies hurt both less when combined), which is
the reason for pairing them.

**Conditions needed.** Persistent trends across sectors. Momentum loses in sharp reversals
(2009, Nov 2020, 2022).

**Data and window.** Prices start in 2016, so the first formation is 2016-12-30. Holdings run from
Jan 2017 to 2024-01-29, about 85 monthly returns, with the last month truncated at the sealed boundary.
OCF in 10-Qs is year-to-date, so only use 10-K annual figures. Report per-rebalance fundamentals
coverage: usable coverage is 72% of members in 2016, rising to 96%. Uncovered names are dropped, and
the gap skews toward later-dead firms. Names leaving the index are sold at their last price; report how
many.

**Costs and turnover.** 10 bps per side, stressed at 20 bps. Report one-sided monthly turnover
(expect 40-60%). Alpaca can paper-trade it: about 25 names with fractional shares.

**Benchmark.** SPY over the same months. Report beta and alpha, because long-only momentum is mostly
market exposure.

**Proved wrong if** the screened basket does not beat SPY after costs, or has a deeper max drawdown
than the pure-momentum basket.

**Main weakness.** 85 months covering about two regimes. Results vs SPY will be dominated by the
2020-21 tech concentration and the 2022 reversal. The top-half cutoff is a second knob on a momentum
sample H12 already uses.

---

## H16: Post-earnings drift from filed EPS (no paid estimates)

**Idea.** For each 10-Q (fiscal Q1-Q3; Q4 is skipped in v1), compute SUE as diluted EPS minus the
same quarter a year earlier (as originally filed), divided by the standard deviation of that seasonal
difference over the prior 8 quarters (minimum 4). Breakpoints come from all member 10-Qs filed in the
prior 91 days. Buy events at the 90th percentile or above at the close of the first trading day after
filing, hold 60 trading days, equal weight.

**Sources.** Bernard & Thomas (1989): the top-minus-bottom seasonal-random-walk SUE decile drifted
for about 60 trading days, positive in 41 of 48 quarters from 1974 to 1985. Decay evidence: Martineau
(CFR 2022) finds no drift for large stocks since 2006. The UCLA Anderson Review notes two 2025 papers
that dispute this.

**Conditions needed.** Investors slow to absorb earnings news. That is weakest in liquid large caps,
which is exactly our universe.

**Filing date vs announcement date.** The filed date is the 10-Q date, not the earnings release.
Large accelerated filers have 40 days after quarter end and usually release earnings (8-K item 2.02)
days to weeks earlier. That avoids look-ahead, but we enter after the announcement-day reaction and
after part of the drift, so the test measures only residual drift. A null result therefore does not
refute PEAD; a positive one would be notable. A possible v2 is a separate trial that uses free EDGAR
8-K item 2.02 dates.

**Data and window.** Events filed 2016 to 2024-01-29. XBRL starts around 2009, so 8-quarter histories
exist. Every position is closed or truncated at 2024-01-29. Report coverage (events vs members) per
quarter. Guard against tag and split artifacts by dropping events where the share count changed more
than 20%.

**Costs and benchmark.** 10 bps per side, stressed at 20 bps. SPY over the same days, plus the daily
alpha t-stat and the top-minus-bottom spread as a diagnostic. Tradable long-only on Alpaca paper.

**Proved wrong if** the long basket fails to beat SPY after costs, or the top-minus-bottom spread is
at or below zero.

**Main weakness.** The prior is close to zero. Large-cap PEAD appears gone, and the filing lag
removes most of what is left.

---

## Sources
- Schmeling, Schrimpf, Todorov, "Crypto carry", BIS WP 1087 (2023): https://www.bis.org/publ/work1087.pdf
- Novy-Marx, "The Other Side of Value" (NBER w15940, 2010; JFE 2013): https://www.nber.org/papers/w15940
- Ball, Gerakos, Linnainmaa, Nikolaev, JFE 2016: https://doi.org/10.1016/j.jfineco.2016.04.004
- Jegadeesh, Titman, JF 1993: https://ideas.repec.org/a/bla/jfinan/v48y1993i1p65-91.html
- Bernard, Thomas, JAR 1989: https://doi.org/10.2307/2491062
- Martineau, "Rest in Peace PEAD", CFR 2022: https://ideas.repec.org/a/now/jnlcfr/104.00000122.html
- UCLA Anderson Review on PEAD dispute: https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again
- Alpaca crypto fees: https://docs.alpaca.markets/docs/crypto-fees ; crypto shorting not supported: https://forum.alpaca.markets/t/unable-to-short-sell-crypto-on-tradingview/14583
- Coinbase perps (promo 0%/0.03%, non-US): https://www.coinbase.com/fr/perpetuals ; US CFTC perps: https://cryptoslate.com/coinbase-starts-cftc-regulated-perpetuals-for-us-traders-offering-10x-leverage-and-0-02-fees/
- Coinbase Advanced fees: https://www.coinbase.com/advanced-markets

Caveat: every paper was read from its abstract or secondary summaries only (noted in the ledger).
Effect sizes quoted here are unverified against the papers' own tables.
