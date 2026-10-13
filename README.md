# Trading research loop (paper trading only)

| Path | Purpose |
|---|---|
| `research/` | Idea memos, one per agent per day |
| `strategies/` | One file per strategy: `name_v1.py`, `name_v2.py`. Shape in `strategies/base.py` |
| `backtests/` | Locked predictions + results (`.json` and `.md`) |
| `journal/` | Every paper decision (`YYYY-MM-DD.jsonl`) and weekly reviews |
| `memory/ledger.db` | Hypothesis ledger. `python ledger.py --help` |
| `agents/` | Prompts for each agent role, including the paper-reading `literature_scout.md` |
| `calendars/` | Sourced event dates (FOMC, CPI...). Loaded with `calendars.py`, never typed from memory |
| `config/` | `.env` (paper keys), `risk.json` (kill-switch limits). Gitignored |
| `data/` | Historical prices. Gitignored. `python fetch_data.py SPY` |
| `pm/` | Prediction-market research (Kalshi 15-min Bitcoin): read-only data, model, lag test, simulator |

## The loop
1. Research agents (`price_analyst`, `fundamentals_reader`, `macro_watcher`, `literature_scout`) run
   separately, check the ledger first, and register ideas. Then `skeptic.md` attacks them and
   records rejects as `dropped`.
2. `agents/strategy_writer.md`: idea → `strategies/name_vN.py` + unit tests.
3. `backtest.py predict` → `backtest.py run` → (with your approval, once) `backtest.py sealed`.
4. Paper trading: a launchd job (`launchd/`, weekdays 17:00) runs `run_daily.py`, plain Python with no AI.
   Orders go through `broker.submit()` only, which runs `risk.check_order` and journals every decision.
   The Claude research run at 17:33 only checks that the job ran; it never trades.
5. `agents/critic.md` weekly → `journal/review-DATE.md` + ledger lessons.

## Rules enforced in code (not prompts)
- Paper only: `broker.py` hardcodes `paper=True`, requires `ALPACA_PAPER=true`, verifies the paper host.
- Kill switch: every order passes `risk.check_order`. Fails closed on missing data or limits.
  `touch config/HALT` blocks all new risk. Orders that shrink a position are always allowed.
- Each strategy version locks its own prediction (read-only, hashed) before it is backtested.
- Ideas from papers get a before/after-publication comparison in the backtest report.
- Sealed period: never loaded by `run`; `sealed` works once per hypothesis, same version only.
- Each backtested version is one variation; max 5 per idea; Deflated Sharpe uses all of them.
- Lessons are append-only.

`.venv/bin/python -m pytest` runs the guardrail tests.

## Trading job (launchd)
- Install or reinstall: `./launchd/install.sh`. Remove: `./launchd/uninstall.sh`.
- Run now: `launchctl kickstart gui/$(id -u)/com.kabirrandhawa.trading-loop.daily`
- Log: `logs/run_daily.log`. Decisions: `journal/*.jsonl` (UTC dates).
- If the Mac is asleep at 17:00, launchd runs the job when it wakes. Trading is skipped if
  that day's bar isn't available, so a late run never trades on stale prices.

## Alerts
`alerts.py` sends a Mac notification and, if `NTFY_TOPIC` is set in `config/.env`, a phone push via
ntfy.sh. You get alerts for every order sent (normal), every kill-switch block (high), broker errors and
failed runs (urgent), and a low-priority "Daily run OK" after each run. Test: `.venv/bin/python alerts.py test`.

## Prediction-market research (`pm/`, hypothesis 4)
Read-only: no Kalshi account, keys or orders anywhere in this code.
- `pm/record.py`: always-on launchd job saving Kalshi's order book and BTC spot (Coinbase, Kraken,
  Bitstamp) every second to `data/pm/live-YYYY-MM.db`. Alerts if it stalls. Log: `logs/pm_record.log`.
- `pm/backfill.py`: downloads settled windows, 1-minute odds, Kalshi trades and Kraken trades to
  `data/pm/history.db`. Resumable: `.venv/bin/python -m pm.backfill --days 14`.
- `pm/model.py`: fair probability of YES from spot (random walk, 60-second settlement average), and
  Kalshi's published fee formulas.
- `pm/analyze.py`: `lag` (does the market trail spot?), `calibration` (market vs model vs outcomes),
  `predict` / `sim` / `sealed` with the same locked-prediction and sealed-holdout rules as the ETF side.
  Windows are split by time: first 70% development, last 30% sealed.
