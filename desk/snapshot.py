"""Desk snapshot for the Friday dashboard: desk.status flattened into rows. No keys or credentials.

    .venv/bin/python -m desk.snapshot      # writes data/desk/snapshot.json and prints its path

Every row has the same columns: section, key (unique), label, status, value, detail.
Sections: kpi, health, meta, hypothesis, alert.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from desk import status as desk_status

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "desk" / "snapshot.json"


def row(section, key, label, status=None, value=None, detail=None):
    return {"section": section, "key": f"{section}-{key}", "label": label, "status": status,
            "value": value, "detail": detail}


def lessons():
    import ledger
    conn = ledger.connect()
    out = {}
    for hid, text in conn.execute("SELECT id, lessons FROM hypotheses"):
        last = (text or "").strip().splitlines()[-1:] or [""]
        out[hid] = last[0].split("] ", 1)[-1][:220]
    return out


def build(s=None):
    s = s or desk_status.status()
    rows = []
    led = s.get("ledger", {})
    by = led.get("by_status", {}) if "error" not in led else {}
    tested = sum(v for k, v in by.items() if k != "untested")
    edges = by.get("passed_backtest", 0) + by.get("passed_paper", 0)
    waiting = led.get("waiting_for_your_sealed_test_decision", []) if "error" not in led else []
    pa = s.get("paper_account", {})
    rows += [
        row("kpi", "tested", "Ideas tested", value=tested, detail="Failed, dropped, or passed"),
        row("kpi", "edges", "Edges found", value=edges, detail="Passed a backtest or paper trading"),
        row("kpi", "waiting", "Decisions waiting", "attention" if waiting else "ok", len(waiting),
            ", ".join(f"#{i}" for i in waiting) or "None"),
        row("kpi", "equity", "Paper equity", value=pa.get("equity"),
            detail=f"{pa.get('day_change', 0):+,.2f} today, {len(pa.get('positions', []))} positions"
            if "error" not in pa else pa["error"]),
    ]

    jobs = s.get("jobs", {})
    if "error" not in jobs:
        down = [j for j in ("pm-stream", "pm-recorder") if not str(jobs.get(j, "")).startswith("running")]
        unloaded = [j for j, v in jobs.items() if v == "NOT LOADED"]
        rows.append(row("health", "jobs", "Background jobs", "bad" if down or unloaded else "ok",
                        detail="All running or scheduled" if not (down or unloaded)
                        else "Not running: " + ", ".join(down + unloaded)))
    rec = s.get("recorders", {})
    if "error" not in rec:
        hour = rec.get("stream_last_hour") or {}
        ago = rec.get("stream_last_write_s_ago")
        rows.append(row("health", "stream", "Kalshi stream", "ok" if ago is not None and ago < 120 else "bad",
                        hour.get("ws_tob"), f"price changes in the last hour; last write {ago}s ago, "
                        f"{rec.get('stream_reconnects_today', 0)} connects today"))
        rows.append(row("health", "data", "Recorded data", "ok", rec.get("data_pm_gb"),
                        f"GB on disk, {rec.get('archived_days', 0)} days compressed"))
    free = s.get("free_disk_gb")
    rows.append(row("health", "disk", "Free disk", "ok" if free and free > 25 else ("attention" if free and free > 15 else "bad"),
                    free, "GB free; recording pauses below 15"))
    g = s.get("git", {})
    if "error" not in g:
        synced = g.get("sync", "").endswith("origin/main") and "ahead" not in g.get("sync", "")
        rows.append(row("health", "git", "GitHub backup", "ok" if synced else "attention",
                        g.get("uncommitted_files"), f"uncommitted files; last commit {g.get('last_commit', '')[:60]}"))
    latest = s.get("latest", {})
    if "error" not in latest:
        rows.append(row("health", "summary", "Latest daily summary",
                        "ok" if latest.get("daily_summary") else "attention", None, latest.get("daily_summary") or "None yet"))

    rows.append(row("meta", "asof", "Snapshot taken", detail=s.get("as_of")))

    les = lessons()
    for h in led.get("hypotheses", []) if "error" not in led else []:
        rows.append(row("hypothesis", h["id"], h["idea"], h["status"], h.get("variations"),
                        f"{h['market']}: {les.get(h['id'], '')}"))

    for i, a in enumerate(reversed(s.get("alerts_last_24h") or [])):
        time_, rest = a.split(" UTC ", 1) if " UTC " in a else ("", a)
        prio = rest[1:rest.index("]")] if rest.startswith("[") else None
        rows.append(row("alert", i, rest.split("] ", 1)[-1], prio, None, f"{time_} UTC"))
    return rows


def main():
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, default=str))
    print(OUT)
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
