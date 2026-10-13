# Strategy Writer (Step 3)

Take the idea in research/{MEMO}.md and write it as a strategy in strategies/{name}_v{N}.py,
subclassing `strategies.base.Strategy`, with entry rules (`entry`), exit rules (`exit`,
`stop_loss_pct`, `take_profit_pct`), position sizing (`size`, `max_position_pct`), and risk limits.
Set VERSION, HYPOTHESIS (one line) and HYPOTHESIS_ID from the ledger. `entry` and `exit` may use only
the bars they are given. Never index past the last row.

Write unit tests in tests/test_{name}_v{N}.py that confirm the entry and exit rules trigger exactly
when they should, using small hand-built price frames. Run `.venv/bin/python -m pytest` and fix
anything that fails. Do not run a backtest yet.

Revisions: never edit a version that has been backtested. Copy it to _v{N+1}. Each backtested
version counts as one variation, and the ledger refuses more than 5.
