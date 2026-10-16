"""Moby picks slice: a paper forward test of Moby's stock picks (no Claude judgment involved).

Kabir (or Friday, from a pick Kabir forwards) records each pick; code does the rest:
- Each ACTIVE pick gets a fixed SLOT_PCT of the slice (20% of $10,000), newest 5 picks at most.
- A pick stays active until Moby says sell (`close`), its price target is reached, or HOLD_WEEKS pass.
- Every trading day run_daily writes that day's target weights as a validated decision
  (sleeve.decide) and executes it like any slice, through the kill switch.

    .venv/bin/python -m sleeve.picks add CDE --date 2026-10-15 [--target 22.50] [--note "..."]
    .venv/bin/python -m sleeve.picks close CDE --date YYYY-MM-DD --note "Moby: sell"
    .venv/bin/python -m sleeve.picks list
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sleeve import book as sleeve_book  # noqa: E402
from sleeve import decide  # noqa: E402

SLEEVE = "moby"
SLOT_PCT, MAX_ACTIVE, HOLD_WEEKS = 20, 5, 26


def path():
    return sleeve_book.folder(SLEEVE) / "picks.json"


def load(p=None):
    p = Path(p or path())
    return json.loads(p.read_text()) if p.exists() else []


def save(picks, p=None):
    Path(p or path()).write_text(json.dumps(picks, indent=1))


def active(picks, today, prices):
    """Picks still held on `today`: not closed, younger than HOLD_WEEKS, target not yet reached."""
    out = []
    for k in picks:
        if k.get("closed") or k["date"] > today:
            continue
        if date.fromisoformat(today) - date.fromisoformat(k["date"]) > timedelta(weeks=HOLD_WEEKS):
            continue
        if k.get("target") and prices.get(k["symbol"]) is not None and prices[k["symbol"]] >= k["target"]:
            continue
        out.append(k)
    return sorted(out, key=lambda k: k["date"])[-MAX_ACTIVE:]


def decision_for(today, picks, prices):
    act = active(picks, today, prices)
    targets = {k["symbol"]: SLOT_PCT for k in act}
    reasoning = (f"Moby picks rule (code, not judgment): {SLOT_PCT}% of the slice in each active pick; "
                 f"active: {', '.join(k['symbol'] + ' since ' + k['date'] for k in act) or 'none (all cash)'}.")
    return {"date": today, "targets": targets, "reasoning": reasoning,
            "per_symbol": {k["symbol"]: (k.get("note") or "Moby pick")[:300] for k in act}}


def write_today_decision(today, prices, cfg=None, decisions_dir=None, picks=None):
    """Write today's decision for the Moby slice unless one exists. Returns the saved path or None."""
    cfg = cfg or sleeve_book.config(sleeve=SLEEVE)
    d = decision_for(today, load() if picks is None else picks, prices)
    try:
        clean = decide.validate(d, cfg, today=today)
        return decide.save(clean, decisions_dir, sleeve=SLEEVE)
    except decide.Invalid as e:
        if "already exists" in str(e):
            return None
        raise


def add(symbol, day, target=None, note=None):
    picks, symbol = load(), symbol.upper().strip()
    if any(k["symbol"] == symbol and not k.get("closed") for k in picks):
        raise SystemExit(f"{symbol} is already an open pick")
    picks.append({"symbol": symbol, "date": day, "target": target, "note": note, "added": date.today().isoformat()})
    save(picks)
    cfg_path = sleeve_book.folder(SLEEVE) / "config.json"
    cfg = json.loads(cfg_path.read_text())
    if symbol not in cfg["universe"]:
        cfg["universe"].append(symbol)
        cfg_path.write_text(json.dumps(cfg, indent=2))
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "fetch_data.py"), symbol, "--start", "2016-01-01"], check=True)
    return picks[-1]


def close(symbol, day, note=None):
    picks, symbol = load(), symbol.upper().strip()
    for k in picks:
        if k["symbol"] == symbol and not k.get("closed"):
            k["closed"], k["close_note"] = day, note
            save(picks)
            return k
    raise SystemExit(f"no open pick for {symbol}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("symbol"); a.add_argument("--date", required=True)
    a.add_argument("--target", type=float); a.add_argument("--note")
    c = sub.add_parser("close"); c.add_argument("symbol"); c.add_argument("--date", required=True); c.add_argument("--note")
    sub.add_parser("list")
    args = p.parse_args()
    if args.cmd == "add":
        print(add(args.symbol, args.date, args.target, args.note))
    elif args.cmd == "close":
        print(close(args.symbol, args.date, args.note))
    else:
        print(json.dumps(load(), indent=1))


if __name__ == "__main__":
    main()
