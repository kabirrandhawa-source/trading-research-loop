"""Lock the sleeve's prediction before it starts, and score it against SPY when the period ends.

    .venv/bin/python -m sleeve.evaluate predict --hypothesis 7 --from research/<memo>.md
    .venv/bin/python -m sleeve.evaluate score   --hypothesis 7
    .venv/bin/python -m sleeve.evaluate score   --hypothesis 10      # sleeve v2
    .venv/bin/python -m sleeve.evaluate compare                      # v1, v2 and SPY side by side

The hypothesis id picks the sleeve (sleeve.book.SLEEVES) and its prediction version.
"""
import argparse
import json
import math

import ledger
from pm.analyze import RESULTS, lock_prediction, verify_prediction
from sleeve import book as sleeve_book

VERSION = "claude-sleeve-v1"


def score(book):
    h = book["history"]
    if len(h) < 2:
        return {"days": len(h), "note": "not enough history yet"}
    v0, v1, s0, s1 = h[0]["value"], h[-1]["value"], h[0]["spy_close"], h[-1]["spy_close"]
    vals = [x["value"] for x in h]
    peak, dd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v); dd = min(dd, v / peak - 1)
    spy = [x["spy_close"] for x in h]
    speak, sdd = spy[0], 0.0
    for v in spy:
        speak = max(speak, v); sdd = min(sdd, v / speak - 1)
    return {"days": len(h), "from": h[0]["day"], "to": h[-1]["day"],
            "sleeve_return_pct": round((v1 / v0 - 1) * 100, 2), "spy_return_pct": round((s1 / s0 - 1) * 100, 2),
            "excess_pct": round(((v1 / v0) - (s1 / s0)) * 100, 2),
            "sleeve_max_drawdown_pct": round(dd * 100, 2), "spy_max_drawdown_pct": round(sdd * 100, 2)}


def overlap(books):
    """Restrict each book's history to the days every book has, so the comparison is like for like."""
    days = None
    for b in books.values():
        d = {h["day"] for h in b["history"]}
        days = d if days is None else days & d
    return {k: {**b, "history": [h for h in b["history"] if h["day"] in (days or set())]} for k, b in books.items()}


def compare(books=None):
    """Side by side: each sleeve on its own full history, and all of them over their common days."""
    if books is None:
        books = {}
        for k in sleeve_book.SLEEVES:
            if (sleeve_book.folder(k) / "config.json").exists():
                books[k] = sleeve_book.load(sleeve=k)
    own = {k: score(b) for k, b in books.items()}
    common = {k: score(b) for k, b in overlap(books).items()}
    rows = {}
    for k, sc in common.items():
        rows[k] = {"sleeve_return_pct": sc.get("sleeve_return_pct"), "excess_vs_spy_pct": sc.get("excess_pct"),
                   "max_drawdown_pct": sc.get("sleeve_max_drawdown_pct")}
    any_sc = next((sc for sc in common.values() if "spy_return_pct" in sc), None)
    if any_sc:
        rows["SPY"] = {"sleeve_return_pct": any_sc["spy_return_pct"], "excess_vs_spy_pct": 0.0,
                       "max_drawdown_pct": any_sc["spy_max_drawdown_pct"]}
    return {"common_days": next(iter(common.values()), {}).get("days", 0), "side_by_side": rows, "own_history": own}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["predict", "score", "compare"])
    p.add_argument("--hypothesis", type=int)
    p.add_argument("--from", dest="source")
    a = p.parse_args()
    if a.cmd == "compare":
        print(json.dumps(compare(), indent=2))
        return
    if a.hypothesis is None:
        p.error("--hypothesis is required for predict and score")
    sleeve = sleeve_book.by_hypothesis(a.hypothesis)
    version = sleeve_book.info(sleeve)["prediction_version"]
    conn = ledger.connect()
    if a.cmd == "predict":
        print(lock_prediction(conn, a.hypothesis, version, a.source))
    else:
        verify_prediction(conn, a.hypothesis, version)
        print(json.dumps(score(sleeve_book.load(sleeve=sleeve)), indent=2))
        print(json.dumps(compare(), indent=2))


if __name__ == "__main__":
    main()
