"""The Claude sleeve's own book: cash, holdings, orders waiting to fill, and daily value vs SPY.

Kept in paper/claude_sleeve/book.json and updated only by code (sleeve.execute), never by Claude.
The sleeve's symbols are traded by nothing else, so its holdings match the account's positions in them.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "paper" / "claude_sleeve"


def config(path=None):
    return json.loads(Path(path or DIR / "config.json").read_text())


def load(path=None, cfg=None):
    p = Path(path or DIR / "book.json")
    if p.exists():
        return json.loads(p.read_text())
    cfg = cfg or config()
    return {"cash": float(cfg["budget"]), "holdings": {}, "pending": [], "history": []}


def save(book, path=None):
    p = Path(path or DIR / "book.json")
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
