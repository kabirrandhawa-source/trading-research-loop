-- Hypothesis ledger (Step 7). Failed ideas are kept forever; never DELETE rows.
CREATE TABLE IF NOT EXISTS hypotheses (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    idea               TEXT NOT NULL,          -- one sentence
    source_agent       TEXT NOT NULL,          -- price_analyst, fundamentals_reader, ...
    market             TEXT NOT NULL,          -- e.g. SPY, US large caps
    date_tested        TEXT,
    strategy_file      TEXT,
    strategy_version   TEXT,
    variations_tried   INTEGER NOT NULL DEFAULT 0,   -- kept in sync with trials table
    regime             TEXT CHECK (regime IS NULL OR regime IN
                           ('trending_up','trending_down','choppy','high_volatility')),
    backtest_result    TEXT,                   -- JSON summary
    sealed_test_result TEXT,                   -- JSON summary
    paper_result       TEXT,                   -- JSON summary / critic notes
    status             TEXT NOT NULL DEFAULT 'untested' CHECK (status IN
                           ('untested','failed','passed_backtest','passed_paper','paused','retired')),
    lessons            TEXT,
    -- Integrity fields enforced by code:
    prediction_path    TEXT,                   -- written before any backtest, read-only after
    prediction_sha256  TEXT,
    sealed_used_at     TEXT                    -- set once; sealed test can never run again
);

-- One row per strategy version backtested for a hypothesis. Each row is one "variation".
-- Per-trial Sharpe values are needed to compute the Deflated Sharpe Ratio honestly.
CREATE TABLE IF NOT EXISTS trials (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_id     INTEGER NOT NULL REFERENCES hypotheses(id),
    run_at            TEXT NOT NULL DEFAULT (datetime('now')),
    strategy_version  TEXT NOT NULL,
    sharpe_per_period REAL NOT NULL,           -- non-annualized
    n_obs             INTEGER NOT NULL,
    UNIQUE (hypothesis_id, strategy_version)
);
