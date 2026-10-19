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

Netting (approved by Kabir 2026-10-19). The daily job runs in two phases: every slice first PLANS
its orders (prepare: same targets, min_trade, sell caps and journal fields as before), then
execute_plans sends them. A symbol only one slice trades gets exactly the order it always did. A
symbol two or more slices trade gets ONE order ("slices_net") for the signed sum, through
broker.submit (kill switch), because Alpaca rejects opposite-side orders on one symbol as a
potential wash trade (Oct 16: v1 sold 1 QQQ, v2's buy of 2 was rejected). Each slice's intended
order is journaled (event "slice_intent") with the net order id. Books:
- The crossed part (sells matched against buys) is booked for both sides at ONE internal price:
  the net order's average fill price; if the net is zero (no order) or the net order fills nothing,
  the close price the slices used for their decision. Each slice gets its full crossed share.
- The remainder belongs to the net-side slices, pro rata (whole shares, largest remainder), booked
  at the net order's fill price as it fills. If the net order fills partly or is cancelled, the
  crossed part stays done and the unfilled remainder is shared pro rata by the net-side slices.
- A blocked or failed net order changes no book on that symbol.
Pending entries for net orders carry a "net" field; old entries (plain own order ids) reconcile
exactly as before.
"""
import json
import math
from fractions import Fraction
from pathlib import Path

import alerts
import broker
import journal
from sleeve import book as sleeve_book

NAME, VERSION = "claude_sleeve", "1"
NET_NAME, NET_VERSION = "slices_net", "1"
TERMINAL = ("filled", "canceled", "expired", "rejected", "done_for_day")
INTERNAL_PRICE_RULE = ("crossed shares are booked for every slice at the net order's average fill price; "
                       "if there is no order (net zero) or it fills nothing, at the decision close price")


def _order(client, oid, cache=None):
    if cache is None:
        return client.get_order_by_id(oid)
    if oid not in cache:
        cache[oid] = client.get_order_by_id(oid)
    return cache[oid]


def _apply(book, symbol, signed_qty, px):
    book["cash"] -= signed_qty * px
    h = book["holdings"].get(symbol, 0) + signed_qty
    if abs(h) < 1e-9:
        book["holdings"].pop(symbol, None)
    else:
        book["holdings"][symbol] = h


def allocate(total, weights):
    """Split `total` shares across [(key, weight)] pro rata: whole shares by largest remainder (ties go
    to the earlier key) when everything is whole, else exact fractions. Deterministic, so each book
    can work out its own share independently."""
    keys = [k for k, _ in weights]
    w_sum = sum(w for _, w in weights)
    if total <= 0 or w_sum <= 0:
        return {k: 0 for k in keys}
    if float(total).is_integer() and all(float(w).is_integer() for _, w in weights):
        total = int(total)
        exact = [Fraction(total * int(w), int(w_sum)) for _, w in weights]
        out = {k: math.floor(x) for k, x in zip(keys, exact)}
        left = total - sum(out.values())
        for i in sorted(range(len(keys)), key=lambda i: (-(exact[i] - math.floor(exact[i])), i))[:left]:
            out[keys[i]] += 1
        return out
    return {k: total * w / w_sum for k, w in weights}


def _reconcile_net(book, p, client, cache):
    """One slice's share of a net order. Returns True while it should stay pending."""
    n = p["net"]
    o = _order(client, p["order_id"], cache)
    status = str(getattr(o.status, "value", o.status))
    terminal = status in TERMINAL
    filled = float(o.filled_qty or 0)
    fpx = float(o.filled_avg_price) if filled > 0 and o.filled_avg_price else None
    sign = 1 if p["side"] == "buy" else -1
    if not n["crossed_done"]:
        px = fpx if fpx is not None else (n["fallback_price"] if terminal else None)
        if px is not None:
            _apply(book, p["symbol"], sign * n["crossed"], px)
            n["crossed_done"], n["internal_price"] = True, px
    if fpx is not None and p["qty"] > 1e-9:
        mine = allocate(filled, n["alloc"]).get(n["slice"], 0)
        new = min(mine - n["booked"], p["qty"])
        if new > 1e-9:
            _apply(book, p["symbol"], sign * new, fpx)
            n["booked"] += new
            p["qty"] -= new
    return not (n["crossed_done"] and (terminal or p["qty"] <= 1e-9))


def reconcile(book, client, cache=None):
    still = []
    for p in book["pending"]:
        if "net" in p:
            if _reconcile_net(book, p, client, cache):
                still.append(p)
            continue
        o = _order(client, p["order_id"], cache)
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
        if status in TERMINAL or p["qty"] <= 1e-9:
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


def prepare(client, today, prices, spy_close, decisions_dir=None, book_path=None, cfg=None, conflicts=(),
            sleeve=None, positions=None, committed_sells=None, order_cache=None):
    """Phase 1: reconcile, record value, and plan today's orders WITHOUT sending them. Returns a final
    result dict (paused / no decision; book already saved) or a plan with status "planned" for
    execute_plans. Planned sells count against `committed_sells` at once."""
    me = sleeve_book.info(sleeve)
    name, version = (NAME, VERSION) if me["name"] == NAME else (me["name"], me["version"])
    tag = {} if name == NAME else {"strategy": name}
    cfg = cfg or sleeve_book.config(sleeve=sleeve)
    book_path = book_path or me["dir"] / "book.json"
    book = reconcile(sleeve_book.load(book_path, cfg), client, order_cache)
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
    rows = []                                   # in plan order: final tuples (skipped) or intent dicts
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
                    rows.append((s, side, 0, "skipped: account has no shares to sell"))
                    continue
        if side == "sell":
            sold[s] = sold.get(s, 0.0) + qty
        rows.append({"symbol": s, "side": side, "qty": qty, "price": prices[s],
                     "cond": {"sleeve_value": val, "targets": d["targets"]},
                     "reasoning": d.get("per_symbol", {}).get(s) or d["reasoning"],
                     "extra": {"action": "rebalance", "decision_file": f.name}})
    return {"status": "planned", "sleeve": sleeve, "name": name, "version": version, "label": me["label"],
            "book": book, "book_path": book_path, "value": val, "rows": rows, "committed_sells": sold}


def _uncommit(pl, it):
    sold, s = pl["committed_sells"], it["symbol"]
    if it["side"] == "sell" and s in sold:
        sold[s] -= it["qty"]
        if abs(sold[s]) < 1e-9:
            sold.pop(s)


def _send_net(client, symbol, group):
    """One order for the signed sum of several slices' intents on `symbol`; returns the net record."""
    signed = [(pl, it, it["qty"] if it["side"] == "buy" else -it["qty"]) for pl, it in group]
    net = sum(q for _, _, q in signed)
    px = group[0][1]["price"]                  # the close every slice planned with
    desc = ", ".join(f"{pl['name']} {it['side']} {it['qty']:g}" for pl, it in group)
    slices = [{"strategy": pl["name"], "side": it["side"], "qty": it["qty"]} for pl, it in group]
    if abs(net) < 1e-9:
        rec = {"decision": "offset", "order_id": None}
        side, qty = None, 0
    else:
        side, qty = ("buy" if net > 0 else "sell"), abs(net)
        rec = broker.submit(NET_NAME, NET_VERSION, symbol, side, qty, {"close": px, "slices": slices},
                            f"One order for the net of the slices' orders on {symbol} ({desc}); opposite orders "
                            "on one symbol would be rejected as a potential wash trade.", client=client,
                            extra={"action": "net", "slices": slices, "internal_price_rule": INTERNAL_PRICE_RULE})
    dec = rec.get("decision")
    net_sign = 1 if net > 0 else -1
    net_side = [(pl, it) for pl, it, q in signed if qty and (q > 0) == (net_sign > 0)]
    opposite = sum(it["qty"] for pl, it, q in signed if not qty or (q > 0) != (net_sign > 0))
    crossed_alloc = allocate(opposite, [(pl["name"], it["qty"]) for pl, it in net_side])
    via_alloc = [[pl["name"], it["qty"] - crossed_alloc[pl["name"]]] for pl, it in net_side]
    for pl, it, q in signed:
        on_net = any(pl is x for x, _ in net_side)
        crossed = crossed_alloc[pl["name"]] if on_net else it["qty"]
        via = it["qty"] - crossed
        if dec == "offset":
            _apply(pl["book"], symbol, q, px)
        elif dec == "submitted":
            pl["book"]["pending"].append({"order_id": rec["order_id"], "symbol": symbol, "side": it["side"], "qty": via,
                                          "net": {"slice": pl["name"], "crossed": crossed, "crossed_done": crossed == 0,
                                                  "fallback_price": px, "alloc": via_alloc, "booked": 0, "net_qty": qty}})
        else:
            _uncommit(pl, it)
        it["decision"] = "netted" if dec in ("submitted", "offset") else f"netted_{dec}"
        journal.log({"event": "slice_intent", "strategy": pl["name"], "version": pl["version"], "symbol": symbol,
                     "side": it["side"], "qty": it["qty"], "market_conditions": it["cond"], "reasoning": it["reasoning"],
                     **it["extra"], "decision": "netted", "net_order_id": rec.get("order_id"), "net_decision": dec,
                     "net_side": side, "net_qty": qty, "crossed_qty": crossed, "via_net_order_qty": via,
                     "internal_price": px if dec == "offset" else None, "internal_price_rule": INTERNAL_PRICE_RULE})
    return {"symbol": symbol, "side": side, "qty": qty, "decision": dec, "order_id": rec.get("order_id"), "slices": desc}


def execute_plans(client, plans):
    """Phase 2: send the planned orders. A symbol only one slice trades gets that slice's own order,
    exactly as before; a symbol several slices trade gets one net order (see module doc). Saves every
    book and sets plan["result"] like run() returns. Returns the net records."""
    groups = {}
    for pl in plans:
        for it in pl["rows"]:
            if isinstance(it, dict):
                groups.setdefault(it["symbol"], []).append((pl, it))
    nets, done = [], set()
    try:
        for pl in plans:
            for it in pl["rows"]:
                if not isinstance(it, dict):
                    continue
                s = it["symbol"]
                if len(groups[s]) > 1:
                    if s not in done:
                        done.add(s)
                        nets.append(_send_net(client, s, groups[s]))
                    continue
                rec = broker.submit(pl["name"], pl["version"], s, it["side"], it["qty"], it["cond"], it["reasoning"],
                                    client=client, extra=it["extra"])
                if rec.get("decision") == "submitted":
                    pl["book"]["pending"].append({"order_id": rec["order_id"], "symbol": s, "side": it["side"], "qty": it["qty"]})
                else:
                    _uncommit(pl, it)
                it["decision"] = rec.get("decision")
    finally:
        for pl in plans:
            pl["book"]["cash"] = round(pl["book"]["cash"], 2)
            sleeve_book.save(pl["book"], pl["book_path"])
            orders = [r if not isinstance(r, dict) else (r["symbol"], r["side"], r["qty"], r.get("decision"))
                      for r in pl["rows"]]
            pl["result"] = {"status": "executed", "orders": orders, "value": pl["value"]}
    return nets


def run(client, today, prices, spy_close, decisions_dir=None, book_path=None, cfg=None, conflicts=(),
        sleeve=None, positions=None, committed_sells=None):
    """One slice on its own: plan, then send (no other slice to net against)."""
    pl = prepare(client, today, prices, spy_close, decisions_dir, book_path, cfg, conflicts, sleeve, positions,
                 committed_sells)
    if pl["status"] != "planned":
        return pl
    execute_plans(client, [pl])
    return pl["result"]
