# Strategy Writer (Step 3)

Take the idea in research/{MEMO}.md and write it as a strategy in strategies/{name}_v{N}.py,
subclassing `strategies.base.Strategy`, with entry rules (`entry`), exit rules (`exit`,
`stop_loss_pct`, `take_profit_pct`), position sizing (`size`, `max_position_pct`), and risk limits.
Set VERSION, HYPOTHESIS (one line) and HYPOTHESIS_ID from the ledger. `entry` and `exit` may use only
the bars they are given. Never index past the last row. HYPOTHESIS_ID is required: the backtester
refuses to run a strategy against a different hypothesis.

Event dates (Fed meetings, CPI releases, earnings, index rebalances, holidays) must come from
`calendars.load("<name>")`, never typed into the strategy from memory. If the calendar file doesn't
exist yet, build calendars/<name>.csv first: check every date against an official source (e.g.
federalreserve.gov for FOMC, bls.gov for CPI), put that page's URL in `source_url`, and add an
`announced` column when dates were not known far in advance. Use `calendars.known_as_of` so the
strategy only acts on dates that were public at the time.

Write unit tests in tests/test_{name}_v{N}.py that confirm the entry and exit rules trigger exactly
when they should, using small hand-built price frames. Run `.venv/bin/python -m pytest` and fix
anything that fails. Do not run a backtest yet.

Revisions: never edit a version that has been backtested. Copy it to _v{N+1}. Each backtested
version counts as one variation, and the ledger refuses more than 5.
