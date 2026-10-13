"""Hypothesis ledger helper. Agents use the CLI; code uses the functions.

    python ledger.py search --market SPY --status failed
    python ledger.py search --regime choppy --text "mean reversion"
    python ledger.py add --idea "..." --agent price_analyst --market SPY
    python ledger.py update 3 --status paused
    python ledger.py lesson 3 --source critic "Fails when VIX > 30"
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
}


def connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return conn


def add_hypothesis(conn, idea, source_agent, market):
    cur = conn.execute(
        "INSERT INTO hypotheses (idea, source_agent, market) VALUES (?, ?, ?)",
        (idea, source_agent, market),
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


def set_prediction(conn, hypothesis_id, path, sha256):
    h = get(conn, hypothesis_id)
    if h["prediction_sha256"]:
        raise PermissionError("Prediction already recorded for this hypothesis; it cannot be replaced.")
    conn.execute(
        "UPDATE hypotheses SET prediction_path = ?, prediction_sha256 = ? WHERE id = ?",
        (str(path), sha256, hypothesis_id),
    )
    conn.commit()


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

    u = sub.add_parser("update")
    u.add_argument("id", type=int)
    for f in sorted(UPDATABLE):
        u.add_argument(f"--{f}")

    lz = sub.add_parser("lesson")
    lz.add_argument("id", type=int)
    lz.add_argument("text")
    lz.add_argument("--source", required=True)

    args = p.parse_args()
    conn = connect()
    if args.cmd == "search":
        print(json.dumps(search(conn, args.market, args.regime, args.status, args.text), indent=2))
    elif args.cmd == "add":
        print(add_hypothesis(conn, args.idea, args.agent, args.market))
    elif args.cmd == "update":
        fields = {f: getattr(args, f) for f in UPDATABLE if getattr(args, f) is not None}
        update(conn, args.id, **fields)
        print(json.dumps(get(conn, args.id), indent=2))
    elif args.cmd == "lesson":
        add_lesson(conn, args.id, args.text, args.source)
        print(get(conn, args.id)["lessons"])


if __name__ == "__main__":
    _main()
