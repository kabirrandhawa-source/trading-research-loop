"""Lock the sleeve's prediction before it starts, and score it against SPY when the period ends.

    .venv/bin/python -m sleeve.evaluate predict --hypothesis 7 --from research/<memo>.md
    .venv/bin/python -m sleeve.evaluate score   --hypothesis 7
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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["predict", "score"])
    p.add_argument("--hypothesis", type=int, required=True)
    p.add_argument("--from", dest="source")
    a = p.parse_args()
    conn = ledger.connect()
    if a.cmd == "predict":
        print(lock_prediction(conn, a.hypothesis, VERSION, a.source))
    else:
        verify_prediction(conn, a.hypothesis, VERSION)
        print(json.dumps(score(sleeve_book.load()), indent=2))


if __name__ == "__main__":
    main()
