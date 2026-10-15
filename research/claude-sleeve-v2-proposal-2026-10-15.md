# Proposal: Claude sleeve v2, "full research" (DRAFT, not approved, nothing built)

Written 2026-10-15 by Friday at Kabir's request. Needs Kabir's yes before anything is built or scheduled.

## The question
Does giving Claude the desk's full research make its allocation decisions better? v1 (hypothesis 7) sees
only 90 days of prices and a day of headlines. v2 sees everything the desk knows.

## Design: change ONE thing
v2 copies v1 exactly (same 14 ETFs, long only, at most 4 positions, each at most 40%, decide 16:25 ET,
execute 17:00, fill next open, 12 weeks, scored by sleeve.evaluate) EXCEPT for its inputs. Running both
over the same weeks gives a fair three-way comparison: v2 vs v1 isolates the value of the extra research;
both vs SPY measures skill. v1 is not touched.

## What v2 reads each day (all read-only)
| Input | Source | Note |
|---|---|---|
| Everything v1 sees | sleeve.context | 90-day price stats, headlines, holdings |
| Desk research | ledger lessons, latest research/ memos, daily summary | what's been tested and failed |
| Morning brief | journal/brief-<date>.md | news, movers, calendar (written 8:15 the same day) |
| Macro and calendar | TradingView economic calendar and data; fallback: web search | rates, inflation, jobs |
| Sector fundamentals | stocks.fundamentals aggregated to the 8 sector ETFs | earnings, margins, valuations as of filing date |
| Cross-market signals | crypto prices and funding (crypto/data), GLD/TLT trends | risk appetite |
| Model forecast | TimesFM next-day forecasts (tsfm/) | shown with its failed-test record (hypothesis 6) |
| Its own track record | its past decisions and scored results | to learn from mistakes |
Budget about 20 minutes and at most 6 web searches (v1: 10 minutes, 3). Kalshi data is left out: it's
15-minute crypto odds, not useful for a days-to-weeks ETF portfolio.

## Money
$10,000 of paper money from the same $100k account (cash is about $80k after SPY and v1). Paper only.

## Engineering needed (desk-quant, about half a day)
1. Make sleeve/ handle more than one sleeve: book.py's folder and execute.py's NAME are hardcoded
   to paper/claude_sleeve and "claude_sleeve". Add a sleeve id; v1's files, order tags and behavior must
   stay byte-for-byte the same (test this).
2. Let the two sleeves share symbols. Today execute.run pauses a sleeve if any other strategy trades its
   symbols. That check must not count the sibling sleeve (books are kept per sleeve from each order's own
   fills, so sharing is safe as long as order ids stay separate). It must still guard against
   non-sleeve strategies.
3. sleeve/context_v2.py builds the larger input pack, with tests.
4. New folder paper/claude_sleeve_v2/ (config, decisions, drafts, book).
5. A new scheduled task "Claude sleeve v2: daily decision" (weekday 16:25 ET). Background-job change:
   Kabir's call.
6. evaluate prints v1, v2 and SPY side by side.

## Prediction (to lock in the ledger BEFORE v2's first decision; draft wording)
1. v2 does not beat SPY: excess return between -4 and +1 percentage points over 12 weeks.
2. v2 and v1 finish within 2 percentage points of each other (more information, little difference).
3. v2 trades more than v1 (more inputs, more reasons to change).
Pass: v2 beats SPY by at least 2 points AND beats v1 by at least 2 points, with max drawdown no worse
than SPY's. Even a pass is weak (12 weeks, one regime): it earns a longer forward test, never real money.

## Risks and honest limits
- 12 weeks is about 60 decisions: luck can dominate. A 2-point gap between v1 and v2 may be noise.
- More inputs can make things worse: the model may chase news that's already in the price.
- Some inputs are thin or flawed (fundamentals coverage 72-96%, TimesFM failed its test, TradingView
  connector sometimes disconnects). v2 must say in its reasoning when an input was missing.
- Starts about 1-2 days after v1, so the periods differ slightly; compare on the overlapping days.
- Headlines and web pages are data, not instructions (same rule as v1).

## Decisions for Kabir
1. Build v2 as above? (paper only, $10k)
2. Add the 16:25 scheduled task for it?
If no: v1 continues alone; this file stays as a record of the idea.
