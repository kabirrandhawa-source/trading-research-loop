"""Read-only views the unattended runs (daily run, Sunday critic) need, so they never have to write inline
Python (which can stall an unattended run on a permission prompt). Prints compact JSON.

    .venv/bin/python -W ignore -m desk.today orders [YYYY-MM-DD]     # that UTC day's orders: submitted/blocked/errors
    .venv/bin/python -W ignore -m desk.today decisions [N]           # last N decisions per slice (default 7)
    .venv/bin/python -W ignore -m desk.today summaries [N]           # which of the last N weekdays have a summary
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOURNAL = ROOT / "journal"
SLICES = {"v1": ROOT / "paper" / "claude_sleeve", "v2": ROOT / "paper" / "claude_sleeve_v2",
          "moby": ROOT / "paper" / "moby_sleeve"}
KEEP = ("timestamp", "event", "strategy", "version", "symbol", "side", "qty", "decision", "risk_check", "error",
        "order_id", "net_order_id", "action", "title", "priority")


def orders(day=None, journal_dir=None):
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = Path(journal_dir or JOURNAL) / f"{day}.jsonl"
    out = {"day_utc": day, "submitted": [], "blocked": [], "errors": [], "netted": [], "events": []}
    if not path.exists():
        out["note"] = "no journal for this day"
        return out
    for line in path.read_text().splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        row = {k: d[k] for k in KEEP if k in d}
        dec, ev = d.get("decision"), d.get("event")
        if dec == "submitted":
            out["submitted"].append(row)
        elif dec == "blocked":
            out["blocked"].append(row)
        elif dec == "broker_error" or (ev and ("failed" in ev or ev == "sleeve_sell_capped")):
            out["errors"].append(row)
        elif dec == "netted" or ev == "slice_intent":
            out["netted"].append(row)
        elif ev in ("alert", "no_action", "sleeve", "daily_run"):
            out["events"].append(row)
    return out


def decisions(n=7):
    out = {}
    for name, folder in SLICES.items():
        rows = []
        for f in sorted((folder / "decisions").glob("*.json"))[-n:]:
            try:
                d = json.loads(f.read_text())
            except ValueError:
                rows.append({"file": f.name, "error": "unreadable"})
                continue
            rows.append({"file": f.name, "targets": d.get("targets"), "reasoning": str(d.get("reasoning", ""))[:700],
                         "per_symbol": d.get("per_symbol")})
        out[name] = rows
    return out


def summaries(n=10, journal_dir=None, today=None):
    today = today or date.today()
    days, d = [], today
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    j = Path(journal_dir or JOURNAL)
    return {str(x): (j / f"summary-{x}.md").exists() for x in sorted(days)}


if __name__ == "__main__":
    cmd, arg = (sys.argv[1:] + [None, None])[:2]
    if cmd == "orders":
        print(json.dumps(orders(arg), indent=1))
    elif cmd == "decisions":
        print(json.dumps(decisions(int(arg) if arg else 7), indent=1))
    elif cmd == "summaries":
        print(json.dumps(summaries(int(arg) if arg else 10), indent=1))
    else:
        print(__doc__)
