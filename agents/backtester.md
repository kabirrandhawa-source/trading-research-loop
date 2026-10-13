# Backtester (Step 4)

1. Lock the prediction first, for this exact version. Every version (v1, v2, ...) gets its own
   prediction, written before that version is backtested. The memo must state expected return,
   win rate, max drawdown, and what counts as failure. For an idea from a paper, also predict how
   much of the published effect survives after its publication date:

       .venv/bin/python backtest.py predict --hypothesis {ID} --strategy strategies/{STRATEGY}.py --from research/{PREDICTION}.md

   The file is saved read-only with its hash in the ledger; if it's edited, backtests are refused.
   A version's prediction can't be replaced, so write it carefully.

2. Run the development backtest (walk-forward, 2x costs, delayed fills, 5 worst periods, Deflated Sharpe):

       .venv/bin/python backtest.py run --hypothesis {ID} --strategy strategies/{STRATEGY}.py --data data/{SYMBOL}.csv --sealed-pct {X}

   The final {X}% of the data is never loaded. Do not read, plot, or summarize it by any other means.

3. Compare the results against the saved prediction in the report, line by line. If the report
   has a `publication_split`, compare the before- and after-publication results: an effect that
   mostly disappears after publication was probably arbitraged away or never real. Set status:
   `.venv/bin/python ledger.py update {ID} --status failed|passed_backtest` and `.venv/bin/python ledger.py lesson {ID} --source backtester "..."`

4. If it failed, you may explain where it loses money and propose one change, written as a new
   version file with its own new prediction (step 1). Do not run `backtest.py sealed` during revisions.

The sealed test (`backtest.py sealed`) is run once per idea, only after the human approves it.
