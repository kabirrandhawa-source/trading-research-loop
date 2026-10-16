"""A Claude sleeve's own book: cash, holdings, orders waiting to fill, and daily value vs SPY.

Kept in <sleeve folder>/book.json and updated only by code (sleeve.execute), never by Claude.
Each sleeve's book is built only from its OWN orders' fills (reconcile), so two sleeves may hold the
same ETF: the account's position in it is the sum of the sleeves' holdings. Non-sleeve strategies
must not trade a sleeve's symbols (execute.run pauses the sleeve if one does).

Sleeves (v1 is the default everywhere; its folder, name and version never change):
    v1: paper/claude_sleeve,    strategy "claude_sleeve" v1    (hypothesis 7)
    v2: paper/claude_sleeve_v2, strategy "claude_sleeve_v2" v1 (hypothesis 10)
    moby: paper/moby_sleeve,    strategy "moby_sleeve" v1      (hypothesis 13; picks rule in sleeve.picks, no Claude judgment)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "paper" / "claude_sleeve"

SLEEVES = {
    "v1": {"dir": DIR, "name": "claude_sleeve", "version": "1", "hypothesis": 7,
           "prediction_version": "claude-sleeve-v1", "label": "Claude sleeve"},
    "v2": {"dir": ROOT / "paper" / "claude_sleeve_v2", "name": "claude_sleeve_v2", "version": "1", "hypothesis": 10,
           "prediction_version": "claude-sleeve-v2", "label": "Claude sleeve v2"},
    "moby": {"dir": ROOT / "paper" / "moby_sleeve", "name": "moby_sleeve", "version": "1", "hypothesis": 13,
             "prediction_version": "moby-sleeve-v1", "label": "Moby picks"},
}
DEFAULT = "v1"
NAMES = {s["name"] for s in SLEEVES.values()}


def info(sleeve=None):
    sleeve = sleeve or DEFAULT
    if sleeve not in SLEEVES:
        raise ValueError(f"unknown sleeve {sleeve!r}; known: {', '.join(SLEEVES)}")
    return SLEEVES[sleeve]


def folder(sleeve=None):
    return info(sleeve)["dir"]


def by_hypothesis(hid):
    for k, s in SLEEVES.items():
        if s["hypothesis"] == hid:
            return k
    raise ValueError(f"no sleeve is registered for hypothesis {hid}")


def config(path=None, sleeve=None):
    return json.loads(Path(path or folder(sleeve) / "config.json").read_text())


def load(path=None, cfg=None, sleeve=None):
    p = Path(path or folder(sleeve) / "book.json")
    if p.exists():
        return json.loads(p.read_text())
    cfg = cfg or config(sleeve=sleeve)
    return {"cash": float(cfg["budget"]), "holdings": {}, "pending": [], "history": []}


def save(book, path=None, sleeve=None):
    p = Path(path or folder(sleeve) / "book.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(book, indent=1))


def value(book, prices):
    """Cash plus holdings at `prices` ({symbol: price}); None if a held symbol has no price."""
    total = book["cash"]
    for s, q in book["holdings"].items():
        if s not in prices:
            return None
        total += q * prices[s]
    return round(total, 2)
