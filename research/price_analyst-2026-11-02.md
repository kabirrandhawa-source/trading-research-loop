# Price analyst memo, 2026-11-02

Market: S&P 500 (point-in-time, stocks/universe.py). Registered: hypothesis 17.

## Ledger check
Searched the ledger by market "S&P 500" and by text (reversal, low vol, turn-of-month, index addition, 52-week, overnight, industry).
- Failed: 11 (distance pairs), 15 (momentum + cash profitability, long-only).
- Untested: 12 (vol-scaled 12-1 momentum, long-short), 14 (funding carry), 16 (filing-date PEAD).
- Dropped or failed on ETFs only: 1, 2, 3, 6.
- No entry on 52-week-high proximity, low volatility, short-term reversal, industry momentum or index additions.

## Idea (id 17)
- Idea: each month-end rank point-in-time S&P 500 members by close divided by trailing 252-day maximum close, hold the top decile equal-weight long-only for one month.
- Why it might work: George and Hwang (2004) find that nearness to the 52-week high predicts returns, and it carries information not in 12-1 momentum. Anchoring makes investors under-react to good news when the price is near its high. I have not read the paper in this session, so it is not recorded as a paper read. The Scout should confirm the citation.
- Conditions it needs: broad cross-section, monthly rebalance, no regime requirement. It is expected to lag in sharp momentum reversals such as 2020 and 2022.
- Proves it wrong: top-decile excess return vs SPY and vs the equal-weight S&P 500 has t < 2 after costs on the development window, or CAPM or sector-neutral alpha is not positive. It also fails if it is just a duplicate of failed idea 15 (holdings overlap above about 70% with the 12-1 top decile and the same result).
- Can our data test it: yes. stocks.universe.prices gives adjusted closes, and nothing from fundamentals is needed. Use only the backtest.split() development part, and say that survivorship is handled by the dead companies being in the universe.
- Difference from the failed idea 15: it uses no fundamentals, so there is no coverage problem, and the ranking signal is different. The momentum signal is also not skip-month based.

## Caveats
- Dev window is about 7 years, so power is low. A pass would be weak evidence.
- Overlaps with untested idea 12 (momentum). The Skeptic should decide whether it is separate enough.
- A prediction must be locked before any backtest. No backtest was run here.
