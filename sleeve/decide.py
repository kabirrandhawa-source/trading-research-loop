"""Validate and save the Claude sleeve's daily decision. Claude writes a draft JSON; only a decision
that passes every check here is saved for the 17:00 trading job to execute.

    .venv/bin/python -m sleeve.decide path/to/draft.json

Draft format:
{
  "date": "YYYY-MM-DD",                       # today, US Eastern
  "targets": {"QQQ": 30, "GLD": 20},          # percent of the sleeve to hold in each symbol; the rest is cash
  "reasoning": "why, in plain words",
  "per_symbol": {"QQQ": "why this one", ...}  # optional
}
An empty `targets` means: hold all cash.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sleeve import book as sleeve_book


class Invalid(ValueError):
    pass


def today_et():
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def validate(d, cfg, today=None):
    """Return a clean decision or raise Invalid with every problem found."""
    errs = []
    today = today or today_et()
    if d.get("date") != today:
        errs.append(f"date must be today ({today}), got {d.get('date')!r}")
    t = d.get("targets")
    if not isinstance(t, dict):
        errs.append("targets must be an object of symbol -> percent of sleeve")
        t = {}
    clean = {}
    for s, pct in t.items():
        s2 = str(s).upper().strip()
        if s2 not in cfg["universe"]:
            errs.append(f"{s2} is not in the sleeve's universe")
        if not isinstance(pct, (int, float)) or pct != pct:
            errs.append(f"{s2}: percent must be a number")
            continue
        if pct < 0:
            errs.append(f"{s2}: no short positions (long only)")
        if pct > cfg["max_position_pct_of_sleeve"]:
            errs.append(f"{s2}: {pct}% is over the {cfg['max_position_pct_of_sleeve']}% per-position limit")
        if pct > 0:
            clean[s2] = float(pct)
    if len(clean) > cfg["max_positions"]:
        errs.append(f"{len(clean)} positions is over the limit of {cfg['max_positions']}")
    if sum(clean.values()) > 100.0001:
        errs.append(f"targets add up to {sum(clean.values()):.1f}% (max 100%)")
    reasoning = str(d.get("reasoning") or "").strip()
    if len(reasoning) < 20:
        errs.append("reasoning is required (at least a sentence)")
    if errs:
        raise Invalid("; ".join(errs))
    per = {k.upper(): str(v)[:500] for k, v in (d.get("per_symbol") or {}).items()}
    return {"date": today, "targets": clean, "reasoning": reasoning[:2000], "per_symbol": per}


def save(decision, decisions_dir=None):
    out = Path(decisions_dir or sleeve_book.DIR / "decisions") / f"{decision['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise Invalid(f"a decision for {decision['date']} already exists; one decision per day")
    out.write_text(json.dumps(decision, indent=1))
    return out


def main():
    draft = json.loads(Path(sys.argv[1]).read_text())
    try:
        d = validate(draft, sleeve_book.config())
        print(f"saved {save(d)}: {d['targets'] or 'all cash'}")
    except Invalid as e:
        print(f"REJECTED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
