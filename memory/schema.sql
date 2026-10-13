-- Hypothesis ledger (Step 7), schema version 2. Failed ideas are kept forever; never DELETE rows.
CREATE TABLE IF NOT EXISTS hypotheses (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    idea               TEXT NOT NULL,          -- one sentence
    source_agent       TEXT NOT NULL,          -- price_analyst, literature_scout, ...
    market             TEXT NOT NULL,          -- ticker, e.g. SPY
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
                           ('untested','dropped','failed','passed_backtest','passed_paper',
                            'paused','retired')),  -- dropped = rejected before any test
    lessons            TEXT,
    source_url         TEXT,                   -- paper the idea came from, if any
    published_date     TEXT,                   -- paper's first public date (YYYY-MM-DD)
    sealed_used_at     TEXT                    -- set once; sealed test can never run again
);

-- One locked prediction per strategy version, written before that version is backtested.
CREATE TABLE IF NOT EXISTS predictions (
    hypothesis_id     INTEGER NOT NULL REFERENCES hypotheses(id),
    strategy_version  TEXT NOT NULL,
    path              TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (hypothesis_id, strategy_version)
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

-- Every paper the literature scout has read, so it never re-reads one.
CREATE TABLE IF NOT EXISTS papers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    read_at        TEXT NOT NULL DEFAULT (datetime('now')),
    url            TEXT NOT NULL UNIQUE,
    title          TEXT NOT NULL,
    authors        TEXT,
    published_date TEXT,                       -- first public version (working paper date)
    claim          TEXT,                       -- the testable claim, one sentence
    verdict        TEXT NOT NULL CHECK (verdict IN ('testable','not_testable_with_our_data','weak')),
    notes          TEXT,
    hypothesis_id  INTEGER REFERENCES hypotheses(id)
);
