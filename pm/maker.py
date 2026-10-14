"""Market-making simulator for Kalshi 15-minute markets (ledger hypothesis 8; hypothesis 4, lead a).

The idea: rest bids on BOTH YES and NO so that one of each costs under $1. A matched pair pays $1 at
settlement whatever happens; the risk is getting filled on only one side, usually right when the
price is moving against it (adverse selection).

Rules (fixed before any run on real data):
- From open+60s to close-180s, every 30 s: join the best YES bid and the best NO bid (NO bid = 1 - YES ask)
  for SIZE contracts each, only if they add up to at most 1 - MARGIN. Re-quote at the new best price when
  the book moves (a moved order goes to the back of the queue).
- Queue: a new order joins BEHIND everything displayed at its price. It fills only from trades that hit our
  side: at our price after the displayed size ahead has traded, or immediately if the price trades through.
  (Cancellations ahead of us are ignored, so fills are, if anything, understated.)
- Once a side is filled, stop quoting that side; keep quoting the other until matched.
  One cycle per window. Unfilled orders are cancelled at close-180s; unmatched legs ride to settlement.
- Fees: maker fee 0 on this series as far as checked; the pessimistic variant charges 0.0175 x C x P x (1-P).

Data: the authenticated stream (data/pm/stream-YYYY-MM-DD.db, ws_tob + ws_trades; finished days are .db.xz)
and settled outcomes (data/pm/live-*.db markets table). Kalshi trade records: taker_side "no" hits the YES
bid, taker_side "yes" hits the NO bid (checked on 20,000 recorded trades: 86% at the touch).

    .venv/bin/python -m pm.maker predict --hypothesis 8 --version maker-v1 --from research/<memo>.md
    .venv/bin/python -m pm.maker run --hypothesis 8 --version maker-v1      # development windows only
"""
import argparse
import json
import math
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from pm import archive, store
from pm.model import maker_fee

SIZE, MARGIN, STEP_S, START_S, STOP_S = 10, 0.02, 30, 60, 180
SEALED_FRAC = 0.30


@dataclass
class Order:
    side: str           # "yes" or "no"
    price: float        # price paid per contract for that side
    qty: float
    ahead: float        # displayed contracts ahead of us at our price


@dataclass
class Leg:
    qty: float = 0.0
    cost: float = 0.0


@dataclass
class WindowResult:
    ticker: str
    yes: Leg = field(default_factory=Leg)
    no: Leg = field(default_factory=Leg)
    result: str = ""

    def pnl(self, fee_rate=0.0):
        y = 1.0 if self.result == "yes" else 0.0
        fees = sum(maker_fee(l.cost / l.qty, 100, fee_rate) * l.qty for l in (self.yes, self.no) if l.qty)
        return self.yes.qty * y + self.no.qty * (1 - y) - self.yes.cost - self.no.cost - fees


def fill(order, trade_price, count, leg):
    """Apply one trade that hit our side of the book. trade_price is in our side's terms."""
    if order is None or order.qty <= 0:
        return
    if trade_price < order.price - 1e-9:                     # traded through our price: we were filled first
        got = order.qty
    elif abs(trade_price - order.price) < 1e-9:
        order.ahead -= count
        got = min(order.qty, -order.ahead) if order.ahead < 0 else 0.0
        order.ahead = max(order.ahead, 0.0)
    else:
        return
    if got > 0:
        leg.qty += got
        leg.cost += got * order.price
        order.qty -= got


def simulate_window(ticker, open_ts, close_ts, result, tob, trades, size=SIZE, margin=MARGIN):
    """tob: rows (ts, yes_bid, yes_bid_size, yes_ask, yes_ask_size) sorted; trades: (ts, yes_price, count, taker_side)."""
    res = WindowResult(ticker, result=result)
    tts = np.array([t[0] for t in tob]) if tob else np.array([])
    orders = {"yes": None, "no": None}
    legs = {"yes": res.yes, "no": res.no}
    ti = 0
    decisions = np.arange(open_ts + START_S, close_ts - STOP_S, STEP_S)
    end = close_ts - STOP_S
    for k, d in enumerate(list(decisions) + [end]):
        while ti < len(trades) and trades[ti][0] <= d:        # fills from trades since the last decision
            _, p, cnt, taker = trades[ti]
            if taker == "no":
                fill(orders["yes"], p, cnt, res.yes)
            elif taker == "yes":
                fill(orders["no"], 1 - p, cnt, res.no)
            ti += 1
        if d >= end:
            break
        i = int(np.searchsorted(tts, d, side="right")) - 1
        if i < 0:
            continue
        _, yb, yb_sz, ya, ya_sz = tob[i]
        if yb is None or ya is None:
            continue
        nb, nb_sz = round(1 - ya, 4), ya_sz
        if yb + nb > 1 - margin + 1e-9:
            continue
        for side, px, shown in (("yes", yb, yb_sz), ("no", nb, nb_sz)):
            want = size - legs[side].qty
            if want <= 0:
                orders[side] = None                           # this side is done: never chase it
                continue
            o = orders[side]
            if o is None or abs(o.price - px) > 1e-9:
                orders[side] = Order(side, px, want, float(shown or 0))
    return res


def _open_db(path, tmp):
    p = Path(path)
    if p.suffix == ".xz":
        p = archive.restore(p, tmp)
    return sqlite3.connect(p)


def load_windows(series="KXBTC15M", data_dir=None, part="dev", sealed_frac=None):
    """Settled windows of `series` covered by the stream, split by time (first 70% development)."""
    d = Path(data_dir or store.DATA)
    outcomes = {}
    for f in sorted(d.glob("live-*.db")):
        for t, o, c, r in sqlite3.connect(f).execute(
                "SELECT ticker, open_ts, close_ts, result FROM markets WHERE result IN ('yes','no') AND ticker LIKE ?",
                (f"{series}-%",)):
            outcomes[t] = (o, c, r)
    streams = sorted(d.glob("stream-????-??-??.db")) + sorted(d.glob("stream-????-??-??.db.xz"))
    tmp = tempfile.mkdtemp(prefix="maker-")
    tob, trades = {}, {}
    for f in streams:
        c = _open_db(f, tmp)
        for row in c.execute("SELECT ticker, ts, yes_bid, yes_bid_size, yes_ask, yes_ask_size FROM ws_tob "
                             "WHERE ticker LIKE ? ORDER BY ts", (f"{series}-%",)):
            tob.setdefault(row[0], []).append(row[1:])
        for row in c.execute("SELECT ticker, ts, yes_price, count, taker_side FROM ws_trades WHERE ticker LIKE ? "
                             "ORDER BY ts", (f"{series}-%",)):
            trades.setdefault(row[0], []).append(row[1:])
    wins = sorted(((t, *outcomes[t]) for t in outcomes if t in tob and tob[t][0][0] <= outcomes[t][0] + START_S),
                  key=lambda w: w[2])
    frac = SEALED_FRAC if sealed_frac is None else sealed_frac
    cut = int(len(wins) * (1 - frac))
    chosen = wins[:cut] if part == "dev" else wins[cut:]
    return [(t, o, c, r, tob[t], trades.get(t, [])) for t, o, c, r in chosen]


def summarize(results, fee_rate=0.0):
    pnl = np.array([r.pnl(fee_rate) for r in results])
    matched = [r for r in results if r.yes.qty > 0 and r.no.qty > 0 and abs(r.yes.qty - r.no.qty) < 1e-9]
    one_sided = [r for r in results if (r.yes.qty > 0) != (r.no.qty > 0)]
    traded = [r for r in results if r.yes.qty > 0 or r.no.qty > 0]
    sd = pnl.std(ddof=1) if len(pnl) > 1 else 0.0
    return {
        "windows": len(results), "windows_with_fills": len(traded), "fully_matched": len(matched),
        "one_sided": len(one_sided),
        "avg_pair_margin_c": round(float(np.mean([100 * (1 - (r.yes.cost + r.no.cost) / r.yes.qty) for r in matched])), 2) if matched else None,
        "one_sided_avg_pnl_dollars": round(float(np.mean([r.pnl(fee_rate) for r in one_sided])), 3) if one_sided else None,
        "total_pnl_dollars": round(float(pnl.sum()), 2),
        "pnl_per_window_dollars": round(float(pnl.mean()), 4) if len(pnl) else None,
        "t_stat": round(float(pnl.mean() / (sd / math.sqrt(len(pnl)))), 2) if sd > 0 else 0.0,
        "contracts_per_side": SIZE,
    }


def main():
    from pm import analyze
    import ledger
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["predict", "run"])
    p.add_argument("--hypothesis", type=int, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--from", dest="source")
    p.add_argument("--series", default="KXBTC15M")
    a = p.parse_args()
    conn = ledger.connect()
    if a.cmd == "predict":
        print(analyze.lock_prediction(conn, a.hypothesis, a.version, a.source)); return
    prediction = analyze.verify_prediction(conn, a.hypothesis, a.version)
    wins = load_windows(a.series, part="dev")
    results = [simulate_window(t, o, c, r, tob, tr) for t, o, c, r, tob, tr in wins]
    out = {"series": a.series, "part": "dev", "zero_maker_fee": summarize(results, 0.0),
           "pessimistic_maker_fee": summarize(results, 0.0175)}
    s = out["zero_maker_fee"]
    ledger.record_trial(conn, a.hypothesis, a.version, (s["t_stat"] or 0) / math.sqrt(max(s["windows"], 1)), s["windows"])
    ledger.update(conn, a.hypothesis, date_tested=date.today().isoformat(), strategy_file="pm/maker.py",
                  strategy_version=a.version, backtest_result=json.dumps(out))
    print(*analyze.write_report(f"pm_{a.version}", out, prediction), sep="\n")


if __name__ == "__main__":
    main()
