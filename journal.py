"""Append-only decision journal: journal/YYYY-MM-DD.jsonl, one JSON object per line."""
import json
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_DIR = Path(__file__).parent / "journal"


def log(entry, journal_dir=None):
    """journal_dir defaults to JOURNAL_DIR, looked up at call time so tests can redirect it."""
    now = datetime.now(timezone.utc)
    record = {"timestamp": now.isoformat(), **entry}
    path = Path(journal_dir or JOURNAL_DIR) / f"{now.date().isoformat()}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record
