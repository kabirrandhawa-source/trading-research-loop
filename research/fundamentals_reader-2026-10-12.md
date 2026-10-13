# Fundamentals Reader — 2026-10-12

Universe: SPY QQQ IWM DIA TLT IEF GLD XLK XLF XLE XLV XLY XLP XLU XLI (ETFs, sector-level view).
Ledger check: `ledger.py search --market "XLF"` (all and `--status failed`) returned `[]`. SPY/XLK were also
empty, and a text search for "earnings" found nothing. Nothing has been tested yet, so this is not a repeat.

Override in force: at most 1 idea today.

## Idea 1: XLF big-bank earnings-window premium (ledger id **1**, market `XLF`)

**One sentence:** Hold XLF long only during the big-bank earnings window (from the close of the 7th calendar day
to the close of the 20th of Jan/Apr/Jul/Oct), and only when XLF closes above its 100-day SMA at entry. The aim
is to capture the earnings-announcement premium that is concentrated in its top holdings.

**Why it might work**
- Academic literature reports an "earnings announcement premium": stocks tend to earn abnormal returns in the
  weeks they report (Beaver 1968; Frazzini & Lamont 2007; Barber et al. 2013). The usual explanations are
  attention and buying pressure from retail traders, plus the cost of bearing announcement risk.
- XLF suits this test better than any other sector ETF in the universe. It is concentrated: JPM, BRK.B, BAC, WFC,
  GS, MS, C and other large banks and brokers make up a large share of its weight. The money-center banks also
  report on a very regular calendar, kicking off each earnings season in roughly the 2nd–3rd week of the month
  after quarter-end (about the 10th–17th of Jan/Apr/Jul/Oct). So a calendar window can stand in for "the
  announcement period" for most of the ETF's weight, even without an earnings feed.
- Bank filings and earnings calls in this window also give the first read on credit costs, net interest
  income and capital-markets activity. That draws macro attention to the sector, which supports the
  attention-driven premium.
- The trend filter (close > 100d SMA) is a crude, price-only proxy for "the earnings backdrop is not
  deteriorating". When estimates are being cut hard, as in 2020 Q1 and March 2023, announcement weeks tend to
  carry downside surprises rather than a premium.

**Exact conditions it needs**
- The big banks keep reporting inside the fixed calendar window. This held through 2016–2023: JPM reported
  between roughly the 10th and the 17th of the month.
- A normal credit and rates regime. The premium should be weakest or negative in stress regimes such as COVID
  in 2020 and the regional-bank crisis in 2023. The SMA filter is meant to sit those out.
- Enough liquidity that close-to-close fills are realistic. XLF meets this easily.

**What proves it wrong**
- Over 2016-01 to 2024-01 (about 32 windows, fewer after the filter), the mean window return is not higher than
  the mean return of all other same-length XLF holding periods. A direct test is to compare against the same
  rule applied to the 7th–20th of non-earnings months (Feb/Mar/May/Jun/Aug/Sep/Nov/Dec).
- Or: the strategy's Sharpe ratio (on days invested, or annualised on exposure) is not better than buy-and-hold
  XLF.
- Or: the result depends on 1–2 windows. If removing the single best window turns the mean excess return
  negative, treat the idea as failed.
- Or: the unfiltered version (no SMA) does as well or better. That would mean the filter adds nothing and is
  likely curve-fit.

**Concrete rule parameters (expressible from daily OHLCV + calendar only)**
- Instrument: XLF only. Long or flat, no shorts.
- Entry: the close of the first trading day on or after calendar day **7** of January, April, July and October.
  The trade is taken only if XLF's close that day is above its **100-day simple moving average** of closes.
- Exit: the close of the last trading day on or before calendar day **20** of the same month.
- Position size: 100% of strategy capital while in. Cash otherwise, at zero return.
- Costs: apply the backtester's default commission and slippage. There are about 8 round trips a year at
  most, so cost drag is small.
- Variants allowed for robustness: entry day 5–9 and exit day 18–22. A parameter sweep beyond that counts as
  data-mining and does not rescue a failed base case.

**Honest limitations of the price-only constraint**
- The strategy cannot see actual report dates, earnings surprises, guidance or estimate revisions. It tests
  only the calendar-timed announcement premium, not any fundamental signal. A "fundamentals" edge such as
  trading on beats and misses is not testable with this data.
- The calendar window is an approximation. Some holdings, like BRK.B and insurers, report outside it, which
  dilutes the effect.
- The sample is small: at most about 32 trades over 2016–2023. Statistical power is low, so even a positive
  result should be treated as weak evidence and requires the out-of-sample check on the sealed period.
- The 2016–2024 period includes unusual rate regimes: ZIRP, the 2022 hiking cycle and the 2023 bank failures.
  The premium may be regime-dependent in ways one 100-day SMA cannot capture.
- No data in `data/` was viewed and no post-2024 prices were consulted.
