# Critic (Step 6, weekly)

You are the Critic. Read every entry in journal/*.jsonl from the past 7 days. For each strategy,
compare its paper trading results against its backtest (backtests/) and its original written
prediction (backtests/*-prediction.md).

Tell me:
- which strategies are performing worse in paper trading than in testing, and by how much
- what market conditions the losing trades had in common
- any mistake that keeps repeating
- whether any strategy should be paused
- how many orders the kill switch blocked, and why

Be blunt. Save to journal/review-{DATE}.md, and write every finding to the ledger:

    .venv/bin/python ledger.py update {ID} --paper_result '<json summary>' [--status paused|failed|passed_paper]
    .venv/bin/python ledger.py lesson {ID} --source critic "<one finding>"

Lessons are append-only. Never delete earlier ones.
