# Macro Watcher — 2026-10-12

Watchlist: SPY QQQ IWM DIA TLT IEF GLD XLK XLF XLE XLV XLY XLP XLU XLI
Focus: interest rates / scheduled macro events. Override in force: at most 1 idea.

## Ledger check

    .venv/bin/python ledger.py search --market "SPY"                  -> []
    .venv/bin/python ledger.py search --market "SPY" --status failed  -> []
    .venv/bin/python ledger.py search --text "FOMC"                   -> []

No prior SPY or FOMC idea has been tested, so this is not a repeat.

## Idea 1 — Pre-FOMC drift in SPY (ledger id: 2, market: SPY)

**One sentence:** Hold SPY only from the close of the trading day before each scheduled
FOMC announcement to the close of announcement day (pre-FOMC drift), flat otherwise.

**Why it might work:** Lucca & Moench (2015) documented that a large share of US equity
excess returns from 1994-2011 accrued in the 24 hours before scheduled FOMC statements.
Proposed explanations: resolution of rate uncertainty releases a risk premium, dealers and
investors de-risk ahead of the event and re-lever into it, and the Fed was on average
accommodative in that period. The event is pre-scheduled, so dates are known in advance
with no lookahead.

**Exact conditions it needs:**
- Scheduled FOMC meetings continue to carry real uncertainty about rates/guidance (true
  2016-2023: hiking cycle 2016-18, cuts 2019, ZIRP/QE 2020-21, aggressive hiking 2022-23).
- Equity reaction is not systematically negative on decision days; the 2022 hiking cycle is
  the obvious stress test, since several statements/pressers sold off.
- Costs per round trip small relative to the edge (~8 trades/year, ~64 total).

**Data constraint and its implications (honest):**
- Only daily SPY OHLCV + calendar is available, no rates/macro feed. The rule therefore
  cannot condition on rate expectations, surprise size, or VIX; it is a pure calendar rule.
- The original effect is measured 2pm(T-1) -> 2pm(T), i.e. *before* the 2:00pm ET
  statement. Daily bars force close(T-1) -> close(T), which *includes* the statement and
  press-conference reaction. That adds noise and may hide or flip the effect; it is a
  test of "pre-FOMC drift + announcement-day reaction," not the pure pre-announcement drift.
- Follow-up literature (e.g. post-2015 studies) reports the drift weakened after
  publication. A null result is a plausible prior; this is a cheap, clean test of it.
- ~64 events is a small sample; a single large day (e.g. a crash or rally) can dominate.
  The sealed final 25% of data (roughly mid-2022 onward) will cover only ~12 events.

**Concrete rule parameters:**
- Instrument: SPY, long only, 100% notional when in, cash otherwise.
- Event dates T (scheduled FOMC statement days; unscheduled meetings excluded; the
  scheduled March 2020 meeting was replaced by emergency actions and is excluded):
  - 2016: 01-27, 03-16, 04-27, 06-15, 07-27, 09-21, 11-02, 12-14
  - 2017: 02-01, 03-15, 05-03, 06-14, 07-26, 09-20, 11-01, 12-13
  - 2018: 01-31, 03-21, 05-02, 06-13, 08-01, 09-26, 11-08, 12-19
  - 2019: 01-30, 03-20, 05-01, 06-19, 07-31, 09-18, 10-30, 12-11
  - 2020: 01-29, 04-29, 06-10, 07-29, 09-16, 11-05, 12-16
  - 2021: 01-27, 03-17, 04-28, 06-16, 07-28, 09-22, 11-03, 12-15
  - 2022: 01-26, 03-16, 05-04, 06-15, 07-27, 09-21, 11-02, 12-14
  - 2023: 02-01, 03-22, 05-03, 06-14, 07-26, 09-20, 11-01, 12-13
  - 2024: 01-31 (only if inside the data window)
  (Dates hard-coded from the public Fed calendar; verify against federalreserve.gov
  before coding.)
- Entry: buy at the close of the last trading day before T (T-1).
- Exit: sell at the close of T. Holding period = 1 trading day.
- No stop, no sizing tweaks, no filters (keeps degrees of freedom near zero).
- Optional single robustness variant (pre-declared, not to be tuned): enter close T-2,
  exit close T.

**What proves it wrong:**
- Mean per-event return <= 0, or t-stat of per-event returns < 1.5 over 2016-2023
  in-sample, or
- Mean per-event return not higher than SPY's unconditional mean daily return over the
  same period (i.e. no better than holding a random day), or
- Result driven by 1-2 events (removing the best two events turns the mean <= 0), or
- Holdout (sealed final 25%) mean per-event return <= 0 after costs.
