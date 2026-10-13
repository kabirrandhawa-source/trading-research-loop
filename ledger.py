"""Hypothesis ledger helper. Agents use the CLI; code uses the functions.

    python ledger.py search --market SPY --status failed
    python ledger.py search --regime choppy --text "mean reversion"
    python ledger.py add --idea "..." --agent price_analyst --market SPY
    python ledger.py update 3 --status paused
    python ledger.py lesson 3 --source critic "Fails when VIX > 30"
    python ledger.py drop 3 --source skeptic "Only ~20 trades; trend filter chosen in hindsight"
    python ledger.py papers --text "momentum"        # papers already read
    python ledger.py paper --url URL --title "..." --published 2019-05-01 --verdict testable --claim "..."
"""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "memory" / "ledger.db"
SCHEMA = ROOT / "memory" / "schema.sql"

MAX_VARIATIONS = 5  # rewrite cap per idea (guide: 3 to 5)

UPDATABLE = {
    "status", "regime", "paper_result", "strategy_file",
    "strategy_version", "date_tested", "backtest_result",
    "source_url", "published_date",
}
SCHEMA_VERSION = 2

_V1_COLUMNS = ("id, created_at, idea, source_agent, market, date_tested, strategy_file, "
               "strategy_version, variations_tried, regime, backtest_result, sealed_test_result, "
               "paper_result, status, lessons, sealed_used_at")


def _migrate_v1(conn):
    """v1 -> v2: allow status 'dropped', add paper fields, move predictions to their own
    per-version table. Rebuilds the hypotheses table because SQLite can't alter a CHECK."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(f"""
        BEGIN;
        ALTER TABLE hypotheses RENAME TO hypotheses_v1;
        {SCHEMA.read_text()}
        INSERT INTO hypotheses ({_V1_COLUMNS}) SELECT {_V1_COLUMNS} FROM hypotheses_v1;
        INSERT INTO predictions (hypothesis_id, strategy_version, path, sha256)
            SELECT id, strategy_version, prediction_path, prediction_sha256 FROM hypotheses_v1
            WHERE prediction_path IS NOT NULL;
        DROP TABLE hypotheses_v1;
        PRAGMA user_version = {SCHEMA_VERSION};
        COMMIT;
    """)
    conn.execute("PRAGMA foreign_keys = ON")


def connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='hypotheses'").fetchone()
    if version < SCHEMA_VERSION and has_table:
        _migrate_v1(conn)
    conn.executescript(SCHEMA.read_text())
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def add_hypothesis(conn, idea, source_agent, market, source_url=None, published_date=None):
    cur = conn.execute(
        "INSERT INTO hypotheses (idea, source_agent, market, source_url, published_date) "
        "VALUES (?, ?, ?, ?, ?)",
        (idea, source_agent, market, source_url, published_date),
    )
    conn.commit()
    return cur.lastrowid


def get(conn, hypothesis_id):
    row = conn.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone()
    if row is None:
        raise KeyError(f"No hypothesis with id {hypothesis_id}")
    return dict(row)


def search(conn, market=None, regime=None, status=None, text=None):
    clauses, params = [], []
    if market:
        clauses.append("market LIKE ?")
        params.append(f"%{market}%")
    if regime:
        clauses.append("regime = ?")
        params.append(regime)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if text:
        clauses.append("(idea LIKE ? OR lessons LIKE ?)")
        params += [f"%{text}%", f"%{text}%"]
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM hypotheses {where} ORDER BY id", params).fetchall()
    return [dict(r) for r in rows]


def update(conn, hypothesis_id, **fields):
    bad = set(fields) - UPDATABLE
    if bad:
        raise ValueError(f"Fields not updatable through this helper: {sorted(bad)}")
    get(conn, hypothesis_id)
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE hypotheses SET {sets} WHERE id = ?", (*fields.values(), hypothesis_id))
    conn.commit()


def add_lesson(conn, hypothesis_id, lesson, source):
    """Append a dated lesson. Earlier lessons are never overwritten."""
    h = get(conn, hypothesis_id)
    line = f"[{datetime.now().date().isoformat()} {source}] {lesson}"
    lessons = f"{h['lessons']}\n{line}" if h["lessons"] else line
    conn.execute("UPDATE hypotheses SET lessons = ? WHERE id = ?", (lessons, hypothesis_id))
    conn.commit()


def drop(conn, hypothesis_id, reason, source):
    """Reject an idea before testing it. It stays in the ledger so nobody proposes it again."""
    if get(conn, hypothesis_id)["status"] != "untested":
        raise PermissionError("Only untested ideas can be dropped.")
    update(conn, hypothesis_id, status="dropped")
    add_lesson(conn, hypothesis_id, f"Dropped before testing: {reason}", source)


def set_prediction(conn, hypothesis_id, strategy_version, path, sha256):
    get(conn, hypothesis_id)
    try:
        conn.execute(
            "INSERT INTO predictions (hypothesis_id, strategy_version, path, sha256) "
            "VALUES (?, ?, ?, ?)",
            (hypothesis_id, strategy_version, str(path), sha256),
        )
    except sqlite3.IntegrityError:
        raise PermissionError(
            f"A prediction for version {strategy_version} is already locked; it cannot be replaced.")
    conn.commit()


def get_prediction(conn, hypothesis_id, strategy_version):
    row = conn.execute(
        "SELECT * FROM predictions WHERE hypothesis_id = ? AND strategy_version = ?",
        (hypothesis_id, strategy_version)).fetchone()
    return dict(row) if row else None


def add_paper(conn, url, title, verdict, authors=None, published_date=None, claim=None,
              notes=None, hypothesis_id=None):
    try:
        cur = conn.execute(
            "INSERT INTO papers (url, title, authors, published_date, claim, verdict, notes, "
            "hypothesis_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (url, title, authors, published_date, claim, verdict, notes, hypothesis_id))
    except sqlite3.IntegrityError as e:
        raise PermissionError(f"Paper already in the ledger or invalid: {e}")
    conn.commit()
    return cur.lastrowid


def search_papers(conn, text=None):
    if text:
        rows = conn.execute(
            "SELECT * FROM papers WHERE title LIKE ? OR claim LIKE ? OR notes LIKE ? OR url LIKE ? "
            "ORDER BY id", [f"%{text}%"] * 4).fetchall()
    else:
        rows = conn.execute("SELECT * FROM papers ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def record_trial(conn, hypothesis_id, strategy_version, sharpe_per_period, n_obs):
    """Count one variation. A new version beyond MAX_VARIATIONS is refused."""
    get(conn, hypothesis_id)
    existing = conn.execute(
        "SELECT strategy_version FROM trials WHERE hypothesis_id = ?", (hypothesis_id,)
    ).fetchall()
    versions = {r["strategy_version"] for r in existing}
    if strategy_version in versions:
        raise PermissionError(
            f"Version {strategy_version} was already backtested for hypothesis {hypothesis_id}. "
            "Any change to the strategy needs a new version number, which counts as a new variation."
        )
    if len(versions) >= MAX_VARIATIONS:
        raise PermissionError(
            f"Hypothesis {hypothesis_id} has used all {MAX_VARIATIONS} variations. Mark it failed."
        )
    conn.execute(
        "INSERT INTO trials (hypothesis_id, strategy_version, sharpe_per_period, n_obs) "
        "VALUES (?, ?, ?, ?)",
        (hypothesis_id, strategy_version, sharpe_per_period, n_obs),
    )
    conn.execute(
        "UPDATE hypotheses SET variations_tried = "
        "(SELECT COUNT(*) FROM trials WHERE hypothesis_id = ?) WHERE id = ?",
        (hypothesis_id, hypothesis_id),
    )
    conn.commit()


def trial_sharpes(conn, hypothesis_id):
    rows = conn.execute(
        "SELECT sharpe_per_period FROM trials WHERE hypothesis_id = ?", (hypothesis_id,)
    ).fetchall()
    return [r["sharpe_per_period"] for r in rows]


def claim_sealed_test(conn, hypothesis_id):
    """Atomically mark the sealed period as used. Raises if it was already used."""
    cur = conn.execute(
        "UPDATE hypotheses SET sealed_used_at = datetime('now') "
        "WHERE id = ? AND sealed_used_at IS NULL",
        (hypothesis_id,),
    )
    conn.commit()
    if cur.rowcount != 1:
        raise PermissionError(f"Sealed test period already used for hypothesis {hypothesis_id}.")


def record_sealed_result(conn, hypothesis_id, result):
    conn.execute(
        "UPDATE hypotheses SET sealed_test_result = ? WHERE id = ?",
        (json.dumps(result), hypothesis_id),
    )
    conn.commit()


def _main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("--market")
    s.add_argument("--regime")
    s.add_argument("--status")
    s.add_argument("--text")

    a = sub.add_parser("add")
    a.add_argument("--idea", required=True)
    a.add_argument("--agent", required=True)
    a.add_argument("--market", required=True)
    a.add_argument("--source-url")
    a.add_argument("--published", help="paper's first public date, YYYY-MM-DD")

    u = sub.add_parser("update")
    u.add_argument("id", type=int)
    for f in sorted(UPDATABLE):
        u.add_argument(f"--{f}")

    lz = sub.add_parser("lesson")
    lz.add_argument("id", type=int)
    lz.add_argument("text")
    lz.add_argument("--source", required=True)

    d = sub.add_parser("drop")
    d.add_argument("id", type=int)
    d.add_argument("reason")
    d.add_argument("--source", required=True)

    ps = sub.add_parser("papers")
    ps.add_argument("--text")

    pa = sub.add_parser("paper")
    pa.add_argument("--url", required=True)
    pa.add_argument("--title", required=True)
    pa.add_argument("--verdict", required=True,
                    choices=["testable", "not_testable_with_our_data", "weak"])
    pa.add_argument("--authors")
    pa.add_argument("--published")
    pa.add_argument("--claim")
    pa.add_argument("--notes")
    pa.add_argument("--hypothesis", type=int)

    args = p.parse_args()
    conn = connect()
    if args.cmd == "search":
        print(json.dumps(search(conn, args.market, args.regime, args.status, args.text), indent=2))
    elif args.cmd == "add":
        print(add_hypothesis(conn, args.idea, args.agent, args.market, args.source_url, args.published))
    elif args.cmd == "update":
        fields = {f: getattr(args, f) for f in UPDATABLE if getattr(args, f) is not None}
        update(conn, args.id, **fields)
        print(json.dumps(get(conn, args.id), indent=2))
    elif args.cmd == "drop":
        drop(conn, args.id, args.reason, args.source)
        print(json.dumps(get(conn, args.id), indent=2))
    elif args.cmd == "papers":
        print(json.dumps(search_papers(conn, args.text), indent=2))
    elif args.cmd == "paper":
        print(add_paper(conn, args.url, args.title, args.verdict, args.authors, args.published,
                        args.claim, args.notes, args.hypothesis))
    elif args.cmd == "lesson":
        add_lesson(conn, args.id, args.text, args.source)
        print(get(conn, args.id)["lessons"])


if __name__ == "__main__":
    _main()
