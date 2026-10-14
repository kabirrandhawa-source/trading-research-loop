# Open threads

What the desk is in the middle of. Friday reads this at the start of every /desk session and keeps it
current: add a line when something is started or promised, remove it when it's done. Dated entries,
newest first within each section. Results live in the ledger and journal, not here.

## Waiting on Kabir
- Nothing right now.

## Scheduled / in progress
- 2026-10-14: Market-making simulator built (pm/maker.py, hypothesis 8, prediction locked: expects a loss
  from one-sided fills). Run around 2026-10-27 on development windows only:
  `.venv/bin/python -m pm.maker run --hypothesis 8 --version maker-v1`. Needs ~300+ windows; had 30 dev on Oct 14.
  Note (Friday, Oct 14): the locked prediction file lost its dollar amounts to a shell typo ("$0" became
  "/bin/zsh"). Pass rule is intact; expected-$ figures 2-4 are unreadable. Hash-locked, so NOT edited.
- 2026-10-27 10:00 ET: 2-week check-in task fires. Then lock predictions and test, on post-Oct-13 Kalshi
  windows only: (a) resting limit orders / market making, (b) buying 90c+ favorites (hypothesis 5 watch list),
  (c) BTC "Up" overpriced at mid prices (hypothesis 4 lead b). Aim for ~3x the development sample.
- 2026-10-14 onward: Claude discretionary sleeve (hypothesis 7, forward_test), $10k, decisions 16:27 ET,
  executed 17:00. Score after 12 weeks (~2027-01-06): `.venv/bin/python -m sleeve.evaluate score --hypothesis 7`.
- 2026-10-14 onward: SPY benchmark (paper/benchmarks.json), 9.5% of equity, first fill at the Oct 14 open.
- Research run is slim since 2026-10-14: one rotating agent per weekday (Mon price, Tue fundamentals,
  Wed macro, Thu literature, Fri test the week's untested idea).

## Built but not yet used
- Portfolio paper trading (many stocks, rebalancing) is NOT built: build it when the first cross-sectional
  stock strategy passes its backtest. Same for crypto paper trading on Alpaca.
- Kalshi trading bot: deliberately not built (no edge yet; MA legality unsettled).

## Known data limits
- Stock fundamentals coverage 72% (2016) to 96% (2025); dead/re-registered companies missing.
- Coinbase International funding data stopped updating at 2026-10-01; Kraken is current.
- Kalshi stream gaps whenever the Mac sleeps.
