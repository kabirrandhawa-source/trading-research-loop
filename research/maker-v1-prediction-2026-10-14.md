# Prediction: Kalshi BTC 15-minute market making, maker-v1 (hypothesis 8)

Written 2026-10-14, after building pm/maker.py and before computing any profit or loss on real data.
(Only a structural check ran: 30 development / 13 sealed windows available so far.) Hypothesis 4, lead (a).

## The test (fixed in advance)
- pm/maker.py rules: from open+60s to close-180s, every 30 s, join the best YES and best NO bid for 10
  contracts each, only if they sum to at most 0.98; join the back of the queue; never chase a filled side;
  cancel at close-180s; unmatched legs ride to settlement. Maker fee 0 (pessimistic variant 0.0175 formula).
- Data: the authenticated stream from 2026-10-13 on, KXBTC15M windows with outcomes and full coverage,
  first 70% by time = development. Run around 2026-10-27, when there should be several hundred windows.

## What I expect
1. Most windows with any fill are ONE-SIDED: fully matched pairs in under 30% of filled windows.
2. Matched pairs earn about 2-4c per contract (10 contracts: /bin/zsh.20-0.40 per pair).
3. One-sided legs lose on average (adverse selection): about -.00 to -.50 per one-sided window.
4. Overall: loses money, about -/bin/zsh.10 to -/bin/zsh.60 per window at zero maker fee; worse with the fee.

## What counts as a pass
Positive profit per window with t-stat above 3 over at least 300 development windows, at zero maker
fee AND still positive under the pessimistic maker fee. A pass earns the sealed test, then a live
simulation (orders computed but not sent), never real money directly.
