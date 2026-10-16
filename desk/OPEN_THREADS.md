# Open threads

What the desk is in the middle of. Friday reads this at the start of every /desk session and keeps it
current: add a line when something is started or promised, remove it when it's done. Dated entries,
newest first within each section. Results live in the ledger and journal, not here.

## Waiting on Kabir
- 2026-10-15: Switch the scheduled tasks "Trading loop: daily run", "Trading loop: Sunday critic" and
  "Trading loop: 2-week check-in" to Auto mode (Scheduled sidebar > task > edit). The Oct 14 daily run
  sat waiting for a permission approval on its first command (desk.status) for 26 hours, which blocked
  the Oct 15 run; Friday stopped it on Oct 15. Then click Run now on the daily run once.

## Scheduled / in progress
- 2026-10-15 onward: Moby picks slice (hypothesis 13, forward_test, prediction locked), $10k, 20% per pick,
  newest 5, held to Moby sell / target / 26 weeks; score ~2027-04-15. First pick CDE (Coeur Mining), buys at the
  Oct 16 17:00 run, fills Oct 19 open. When Kabir forwards a new Moby pick or sell, record it:
  `.venv/bin/python -m sleeve.picks add <SYM> --date <pick date> [--target <price>] --note "..."` (or `close`).
- 2026-10-15: Learning loop added (Kabir yes): daily summary carries a v1/v2/SPY SCOREBOARD line and stages
  paper/claude_sleeve_v2/; Sunday critic scores both sleeves, reviews each decision (right for the reason /
  luck / wrong) and writes one ledger lesson per sleeve (h7, h10). Improvements go to a future v3, never
  mid-test. ~2027-01-06: Friday brings Kabir a model recommendation with evidence.
- 2026-10-15: Claude sleeve v2 BUILT (hypothesis 10, forward_test, prediction locked; commit 99ed27f). Scheduled
  (Kabir yes 2026-10-15): task trading-loop-claude-sleeve-v2, weekdays 16:25 ET; first decision Oct 15.
  Score after 12 weeks with sleeve.evaluate --hypothesis 10. Caveats: sector holdings typed from
  memory (approximate); context_v2 reads post-2024-01-30 crypto/fundamentals as live inputs: Kabir OK'd this 2026-10-15
  (live decision inputs only; research and backtests still never use sealed data).
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
- 2026-10-15: keep-awake launchd job (`caffeinate -s`) installed: no idle sleep while on AC power. On battery
  the Mac still naps and the Kalshi stream gets gaps; a closed lid always sleeps.
- Stock fundamentals coverage 72% (2016) to 96% (2025); dead/re-registered companies missing.
- Coinbase International funding data stopped updating at 2026-10-01; Kraken is current.
- Kalshi stream gaps whenever the Mac sleeps.
- 2026-10-14: Kalshi 15-min stock-index series (KXINX15M, KXNDQ15M, KXDJIA15M) record nothing (0 rows
  today, no log lines). All 5 crypto series + gold/silver/oil/FX record fine. Unchecked: are those
  markets even listed? (desk-ops if Kabir wants it looked at.)
