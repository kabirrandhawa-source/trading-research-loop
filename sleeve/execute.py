"""Turn today's validated sleeve decision into orders. Called by run_daily.py at 17:00; code only.

1. Reconcile: orders placed earlier that have filled update the book (cash, shares) at their
   actual fill price; cancelled or expired ones are dropped.
2. Record today's sleeve value next to SPY's close, for the comparison.
3. If a decision dated today exists: work out the whole-share orders that move the sleeve to its
   targets (sells first, then buys within the cash the sells free up plus existing cash), skip
   changes under min_trade_dollars, and send each through broker.submit (kill switch + journal).

More than one sleeve (sleeve.book.SLEEVES) may run; v1 is the default. Sleeves may share ETFs because
each book comes only from its own orders' fills. Non-sleeve strategies still may not trade a sleeve's
symbols. broker._reduces looks at the ACCOUNT position, not the sleeve's, so when `positions`
(account shares per symbol) is given, a sell is capped at what the account holds minus what other
sleeves already sold this run (`committed_sells`, shared across the run): one sleeve can never sell
shares that would leave the account short.
"""
import json
import math
from pathlib import Path

import alerts
import broker
import journal
from sleeve import book as sleeve_book

NAME, VERSION = "claude_sleeve", "1"


def reconcile(book, client):
    still = []
    for p in book["pending"]:
        o = client.get_order_by_id(p["order_id"])
        status = str(getattr(o.status, "value", o.status))
        filled = float(o.filled_qty or 0)
        if filled > 0 and o.filled_avg_price:
            px = float(o.filled_avg_price)
            sign = 1 if p["side"] == "buy" else -1
            book["cash"] -= sign * filled * px
            h = book["holdings"].get(p["symbol"], 0) + sign * filled
            if abs(h) < 1e-9:
                book["holdings"].pop(p["symbol"], None)
            else:
                book["holdings"][p["symbol"]] = h
            p["qty"] = p["qty"] - filled
        if status in ("filled", "canceled", "expired", "rejected", "done_for_day") or p["qty"] <= 1e-9:
            continue
        still.append(p)
    book["pending"] = still
    book["cash"] = round(book["cash"], 2)
    return book


def plan(book, targets, prices, cfg):
    """[(symbol, side, qty, reason)] moving holdings to `targets` (percent of sleeve value)."""
    total = sleeve_book.value(book, prices)
    orders, cash = [], book["cash"]
    syms = sorted(set(book["holdings"]) | set(targets))
    desired = {s: math.floor(total * targets.get(s, 0) / 100 / prices[s]) for s in syms}
    for s in syms:                                                  # sells first
        diff = desired[s] - book["holdings"].get(s, 0)
        if diff < 0 and -diff * prices[s] >= cfg["min_trade_dollars"] or (diff < 0 and desired[s] == 0):
            orders.append((s, "sell", -diff))
            cash += -diff * prices[s]
    for s in syms:                                                  # then buys, within cash
        diff = desired[s] - book["holdings"].get(s, 0)
        if diff > 0 and diff * prices[s] >= cfg["min_trade_dollars"]:
            qty = min(diff, math.floor(cash * 0.995 / prices[s]))
            if qty > 0:
                orders.append((s, "buy", qty))
                cash -= qty * prices[s]
    return orders


def conflicting_symbols(conflicts):
    """Symbols traded by NON-sleeve strategies. `conflicts` is either a list of symbols (all treated as
    non-sleeve) or {strategy name: [symbols]}, in which case sibling sleeves are ignored."""
    if isinstance(conflicts, dict):
        return {s for owner, syms in conflicts.items() if owner not in sleeve_book.NAMES for s in syms}
    return set(conflicts)


def run(client, today, prices, spy_close, decisions_dir=None, book_path=None, cfg=None, conflicts=(),
        sleeve=None, positions=None, committed_sells=None):
    me = sleeve_book.info(sleeve)
    name, version = (NAME, VERSION) if me["name"] == NAME else (me["name"], me["version"])
    tag = {} if name == NAME else {"strategy": name}
    cfg = cfg or sleeve_book.config(sleeve=sleeve)
    book_path = book_path or me["dir"] / "book.json"
    book = reconcile(sleeve_book.load(book_path, cfg), client)
    clash = set(cfg["universe"]) & conflicting_symbols(conflicts)
    if clash:
        alerts.send(f"{me['label']} paused", f"Another strategy trades {', '.join(sorted(clash))}; the sleeve can't share symbols.", "high", ["warning"])
        sleeve_book.save(book, book_path)
        return {"status": "paused", "reason": f"symbol clash {sorted(clash)}"}
    val = sleeve_book.value(book, prices)
    if val is not None and not any(h["day"] == today for h in book["history"]):
        book["history"].append({"day": today, "value": val, "spy_close": spy_close})
    f = Path(decisions_dir or me["dir"] / "decisions") / f"{today}.json"
    if not f.exists():
        sleeve_book.save(book, book_path)
        journal.log({"event": "sleeve", **tag, "note": "no decision for today; holding", "value": val})
        return {"status": "no decision", "value": val}
    d = json.loads(f.read_text())
    waiting = {p["symbol"] for p in book["pending"]}
    sold = committed_sells if committed_sells is not None else {}
    sent = []
    for s, side, qty in plan(book, d["targets"], prices, cfg):
        if s in waiting:
            continue
        if side == "sell" and positions is not None:
            room = max(0.0, float(positions.get(s, 0.0)) - sold.get(s, 0.0))
            if qty > room:
                alerts.send(f"{me['label']}: sell capped", f"Book says sell {qty:g} {s} but the account has only {room:g} "
                            "not already being sold. Books and account disagree; check by hand.", "high", ["warning"])
                journal.log({"event": "sleeve_sell_capped", "strategy": name, "symbol": s, "wanted": qty, "room": room})
                qty = math.floor(room)
                if qty <= 0:
                    sent.append((s, side, 0, "skipped: account has no shares to sell"))
                    continue
        rec = broker.submit(name, version, s, side, qty, {"sleeve_value": val, "targets": d["targets"]},
                            d.get("per_symbol", {}).get(s) or d["reasoning"], client=client,
                            extra={"action": "rebalance", "decision_file": f.name})
        if rec.get("decision") == "submitted":
            book["pending"].append({"order_id": rec["order_id"], "symbol": s, "side": side, "qty": qty})
            if side == "sell":
                sold[s] = sold.get(s, 0.0) + qty
        sent.append((s, side, qty, rec.get("decision")))
    sleeve_book.save(book, book_path)
    return {"status": "executed", "orders": sent, "value": val}
