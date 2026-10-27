# Open threads

What the desk is in the middle of. Friday reads this at the start of every /desk session and keeps it
current: add a line when something is started or promised, remove it when it's done. Dated entries,
newest first within each section. Results live in the ledger and journal, not here.

## Waiting on Kabir
- Nothing right now.

## Scheduled / in progress
- 2026-10-27: Evening run + critic recreated from a Kabir-typed turn and CONFIRMED saved in Auto mode:
  trading-loop-evening (weekdays 17:30) and trading-loop-sunday-review (Sun 10:00). Old ones paused, the Oct 21
  replacements deleted. Oct 22-26 runs (evening, critic, 2-week check-in) all froze in default mode: no
  summaries Oct 16-26, no weekly review since Oct 12. Critic re-run by hand Oct 27; h8 maker test next.
- 2026-10-21: Unattended runs stalled on inline-python permission prompts. Fix: desk.today (orders/decisions/
  summaries) + `alerts.py send` CLI, both allowlisted; daily run + critic prompts now forbid inline code.
  Kabir confirmed all three tasks are in Auto. Critic re-run Oct 21 got ~20 steps in, then hit one inline
  python call (pre-fix prompt). Check tonight's 17:33 daily run finishes unattended.
- 2026-10-19: Kabir set daily run, Sunday critic and 2-week check-in to Auto mode. Friday stopped the two frozen
  runs (Oct 16 daily, Oct 18 critic) and re-ran the Oct 19 daily run by hand (it ran without stalling).
  Oct 19 re-run stalled because the Mac slept (lid closed, unplugged). Oct 20: critic re-run by hand (Mac awake);
  critic prompt now scores Moby (h13) too and may never pause h7/h10/h13. Lesson: runs need the Mac awake + plugged in.
- 2026-10-19: Crypto forward recorder LIVE (Kabir yes): launchd crypto-forward, hourly, data/crypto/forward.db
  (Kraken funding/mark/index for 5 coins + Coinbase spot; Coinbase Intl frozen since Oct 1, kept as a check).
  h14 re-test needs ~3+ months of forward data (earliest ~2027-01); not sealed (recorded after the split).
- 2026-10-19: Same-symbol slice orders now netted into one "slices_net" order per symbol (eaf9f33, 179 tests).
  Crossed shares booked for both sides at the net fill price (decision close if no fill). First live use
  Oct 19 17:00: v1 +1 QQQ and v2 +2 QQQ sent as ONE "slices_net" buy of 3 (worked). Watch: v1 sold 1 QQQ Oct 16
  and bought it back Oct 19 (1-share rebalancing churn; flag to the Sunday critic, no mid-test change).
- 2026-10-16 to 2026-10-30: ALPHA SPRINT (Kabir yes). Replaces random daily ideas; evening run's research is
  paused until Oct 30. Four leads: Kalshi market making (h8, Oct 27), crypto funding carry, S&P 500 momentum
  (+quality), post-earnings drift from filed EPS. Flow per lead: skeptic -> locked prediction -> ONE dev
  backtest; a pass goes to Kabir for the sealed test. Registered: h14 funding carry, h15 momentum +
  cash profitability, h16 filing-date PEAD. Skeptic (Oct 16): h15 TEST (first); h12, h14, h16 NOT YET (h14 needs
  forward funding/basis recording + US venue; h16 needs EDGAR 8-K 2.02 dates). h15 v1 FAILED (ad63dca): excess vs SPY
  -0.2%/yr t -0.05, sector-neutral alpha -2.7%/yr. Screen dropped 23% of picks for missing fundamentals
  (dead firms unmatched to SEC, GOOGL/META stored as GOOG/FB, AAPL OCF gaps) = survivor bias. Next sprint
  steps (proposed to Kabir): fix stock-fundamentals ticker mapping + gaps; fetch free EDGAR 8-K 2.02 dates
  (unblocks h16); forward-record crypto funding/basis (h14: LIVE since Oct 19); h8 on Oct 27.
  latest() stale-year bug is minor (0.1-0.5%) and v2 doesn't call it: no decision needed.
  Kabir has many ideas of his own: queue them in the ledger, test after the sprint unless one fits it.
- 2026-10-16: Texts work: high/urgent alerts also go by iMessage to SMS_TO (config/.env), test text received.
  The 17:00 launchd job may trigger its own macOS "control Messages" prompt the first time; Kabir to allow it.
- 2026-10-16: Kabir raised max_open_positions 5 -> 14 in config/risk.json (verified: kill switch passes a
  6th position). Oct 15 v2 orders were blocked, so v2 starts trading with tonight's decision (fills Oct 19);
  note the lost day when scoring h10. Blocked orders now send a high alert (13f0764).
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

## Kabir's go-live plan (his decision, not before a strategy passes sealed + paper tests)
- 2026-10-20: First real-money allocation: $1,000 total. Size limits to that when the time comes.

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
