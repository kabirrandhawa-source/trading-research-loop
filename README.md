# Trading research loop (paper trading only)

| Path | Purpose |
|---|---|
| `research/` | Idea memos, one per agent per day |
| `strategies/` | One file per strategy: `name_v1.py`, `name_v2.py`. Shape in `strategies/base.py` |
| `backtests/` | Locked predictions + results (`.json` and `.md`) |
| `journal/` | Every paper decision (`YYYY-MM-DD.jsonl`) and weekly reviews |
| `memory/ledger.db` | Hypothesis ledger. `python ledger.py --help` |
| `agents/` | Prompts for each agent role |
| `config/` | `.env` (paper keys), `risk.json` (kill-switch limits). Gitignored |
| `data/` | Historical prices. Gitignored. `python fetch_data.py SPY` |

## The loop
1. Research agents (`agents/price_analyst.md`, `fundamentals_reader.md`, `macro_watcher.md`) run
   separately, check the ledger first, and register ideas. Then `skeptic.md` attacks them.
2. `agents/strategy_writer.md`: idea → `strategies/name_vN.py` + unit tests.
3. `backtest.py predict` → `backtest.py run` → (with your approval, once) `backtest.py sealed`.
4. Paper trading goes through `broker.submit()` only. It runs `risk.check_order` and journals every decision.
5. `agents/critic.md` weekly → `journal/review-DATE.md` + ledger lessons.

## Rules enforced in code (not prompts)
- Paper only: `broker.py` hardcodes `paper=True`, requires `ALPACA_PAPER=true`, verifies the paper host.
- Kill switch: every order passes `risk.check_order`. Fails closed on missing data or limits.
  `touch config/HALT` blocks all new risk. Orders that shrink a position are always allowed.
- Prediction is saved read-only with a hash; any edit blocks further backtests.
- Sealed period: never loaded by `run`; `sealed` works once per hypothesis, same version only.
- Each backtested version is one variation; max 5 per idea; Deflated Sharpe uses all of them.
- Lessons are append-only.

`.venv/bin/python -m pytest` runs the guardrail tests.
