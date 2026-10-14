"""Daily paper-trading run. Schedule after the US close.

1. Refresh daily bars for every symbol in universe.txt.
2. For each strategy promoted to paper (status passed_backtest AND a sealed result on file),
   evaluate entry/exit on the latest bars exactly as the backtester does, and send any order
   through broker.submit (kill switch + journal). Orders queue for the next open, matching
   the backtest's next-open fills.

    python run_daily.py            # refresh data + trade
    python run_daily.py --dry-run  # refresh data, log what it would do, place nothing
"""
import argparse
import fcntl
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import alerts
import backtest
import broker
import journal
import ledger
import risk

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def universe():
    return [s.strip() for s in (ROOT / "universe.txt").read_text().split() if s.strip()]


def refresh_data(symbols, client=None):
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = client or broker.data_client()
    bars = client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day,
        start=datetime(2016, 1, 1), adjustment="all")).df.reset_index()
    for sym, df in bars.groupby("symbol"):
        df.drop(columns="symbol").to_csv(DATA / f"{sym}.csv", index=False)


BENCHMARKS = ROOT / "paper" / "benchmarks.json"


def benchmarks(path=None):
    """Human-approved benchmark strategies (not research results), shaped like ledger rows."""
    path = Path(path or BENCHMARKS)
    if not path.exists():
        return []
    return [{"id": None, "market": b["symbol"], "strategy_file": b["strategy_file"],
             "strategy_version": b["strategy_version"], "benchmark": b["name"]}
            for b in json.loads(path.read_text())]


def promoted(conn, benchmarks_path=None):
    """Strategies the daily job trades: hypotheses that passed the development backtest AND the
    sealed test (promotion is the human's decision), plus the approved benchmarks."""
    rows = conn.execute(
        "SELECT * FROM hypotheses WHERE status = 'passed_backtest' "
        "AND sealed_test_result IS NOT NULL AND strategy_file IS NOT NULL").fetchall()
    out, seen = [], {}
    for h in list(map(dict, rows)) + benchmarks(benchmarks_path):
        sym = h["market"].strip().upper()
        if sym in seen:   # Alpaca nets positions per symbol, so two strategies can't share one
            raise RuntimeError(f"{seen[sym]} and {h.get('benchmark') or h['id']} both trade {sym}. Pause one.")
        seen[sym] = h.get("benchmark") or h["id"]
        out.append((h, sym))
    return out


def bars_held(strategy, symbol, journal_dir=None):
    """Trading days since this strategy's last submitted opening order on this symbol."""
    opened = None
    for f in sorted(Path(journal_dir or journal.JOURNAL_DIR).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            e = json.loads(line)
            if e.get("strategy") == strategy and e.get("symbol") == symbol \
                    and e.get("decision") == "submitted" and e.get("action") == "open":
                opened = e["timestamp"][:10]
    return opened


def decide(strat, bars, held_qty, entry_price, opened_date):
    """Return (action, side, reasoning) using the same rules as backtest.run."""
    if held_qty == 0:
        side = strat.entry(bars)
        if side in (1, -1):
            return "open", side, f"entry() returned {side}"
        return None, 0, "no entry signal"
    side = 1 if held_qty > 0 else -1
    held = int((bars["timestamp"].dt.strftime("%Y-%m-%d") > opened_date).sum()) if opened_date else 0
    move = side * (bars["close"].iloc[-1] / entry_price - 1) * 100
    if strat.stop_loss_pct is not None and move <= -strat.stop_loss_pct:
        return "close", side, f"stop loss: {move:.2f}% <= -{strat.stop_loss_pct}%"
    if strat.take_profit_pct is not None and move >= strat.take_profit_pct:
        return "close", side, f"take profit: {move:.2f}% >= {strat.take_profit_pct}%"
    if strat.exit(bars, {"side": side, "entry_price": entry_price, "bars_held": held}):
        return "close", side, "exit() returned True"
    return None, side, f"holding, move {move:.2f}%"


def open_order_symbols(client):
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    return {o.symbol for o in client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))}


def is_fresh(bars, today):
    """True if the latest bar is today's session (bars are stamped in UTC at the ET session date)."""
    last = bars["timestamp"].iloc[-1].tz_convert("America/New_York").date().isoformat()
    return last == today


def conditions(bars):
    c = bars["close"]
    return {"close": float(c.iloc[-1]), "ret_1d_pct": round(float(c.pct_change().iloc[-1]) * 100, 3),
            "ret_20d_pct": round(float(c.pct_change(20).iloc[-1]) * 100, 3),
            "vol_20d_ann_pct": round(float(c.pct_change().tail(20).std() * 252 ** 0.5) * 100, 2),
            "regime_63d": backtest.classify_regime(bars.tail(63)), "bar_date": str(bars["timestamp"].iloc[-1])}


LOCK_PATH = ROOT / "memory" / "run_daily.lock"


def order_alert(rec):
    """Alert for one broker.submit result."""
    what = f"{rec['side'].upper()} {rec['qty']:g} {rec['symbol']} ({rec['strategy']} v{rec['version']})"
    if rec["decision"] == "submitted":
        alerts.send(f"Paper order: {what}", f"{rec.get('reasoning', '')}\nOrder id {rec.get('order_id')}",
                    "default", ["chart_with_upwards_trend"])
    elif rec["decision"] == "blocked":
        alerts.send(f"BLOCKED by kill switch: {what}", rec.get("risk_check", ""), "high", ["no_entry"])
    else:
        alerts.send(f"Broker error: {what}", rec.get("error", ""), "urgent", ["rotating_light"])


def run(a):
    """One daily pass. Returns a summary dict."""
    summary = {"date": a.today, "strategies": 0, "orders": [], "skipped": [], "no_action": 0}
    refresh_data(universe())
    conn = ledger.connect()
    strategies = promoted(conn)
    summary["strategies"] = len(strategies)
    if not strategies:
        journal.log({"event": "daily_run", "note": "no strategies promoted to paper yet"})
        print("No strategies promoted to paper yet.")
        return summary

    client = broker.paper_client()
    positions = {p.symbol: p for p in client.get_all_positions()}
    pending = open_order_symbols(client)
    for h, sym in strategies:
        cls = backtest.load_strategy(ROOT / h["strategy_file"])
        strat = cls()
        if cls.VERSION != h["strategy_version"]:
            reason = f"file is v{cls.VERSION}, ledger approved v{h['strategy_version']}"
            journal.log({"event": "skipped", "strategy": cls.NAME, "symbol": sym, "reason": reason})
            summary["skipped"].append(f"{sym}: {reason}")
            alerts.send(f"Strategy skipped: {cls.NAME} on {sym}", reason, "high", ["warning"])
            continue
        bars = backtest.load_prices(DATA / f"{sym}.csv")
        if sym in pending:
            journal.log({"event": "skipped", "strategy": cls.NAME, "symbol": sym,
                         "reason": "an order for this symbol is still open (holiday or unfilled)"})
            summary["skipped"].append(f"{sym}: order still open")
            continue
        if not is_fresh(bars, a.today):
            journal.log({"event": "skipped", "strategy": cls.NAME, "symbol": sym,
                         "reason": f"no bar for {a.today} (market closed?); last bar {bars['timestamp'].iloc[-1]}"})
            summary["skipped"].append(f"{sym}: no bar for {a.today}")
            continue
        pos = positions.get(sym)
        qty = float(pos.qty) if pos else 0.0
        entry_px = float(pos.avg_entry_price) if pos else None
        action, side, why = decide(strat, bars, qty, entry_px, bars_held(cls.NAME, sym))
        cond = conditions(bars)
        if action is None:
            journal.log({"event": "no_action", "strategy": cls.NAME, "version": cls.VERSION,
                         "symbol": sym, "market_conditions": cond, "reasoning": why})
            summary["no_action"] += 1
            continue
        if action == "open":
            n = strat.size(float(client.get_account().equity), cond["close"])
            order_side = "buy" if side == 1 else "sell"
        else:
            n, order_side = abs(qty), ("sell" if qty > 0 else "buy")
        if a.dry_run or n <= 0:
            journal.log({"event": "dry_run" if a.dry_run else "zero_size", "strategy": cls.NAME,
                         "version": cls.VERSION, "symbol": sym, "action": action, "side": order_side,
                         "qty": n, "market_conditions": cond, "reasoning": why})
            continue
        rec = broker.submit(cls.NAME, cls.VERSION, sym, order_side, n, cond, why,
                            client=client, extra={"action": action, "hypothesis_id": h["id"]})
        print(sym, action, order_side, n, rec["decision"], rec.get("risk_check"))
        summary["orders"].append(rec["decision"])
        order_alert(rec)
    summary["sleeve"] = run_sleeve(client, a, [s for _, s in strategies], summary)
    return summary


def run_sleeve(client, a, taken_symbols, summary):
    """The Claude discretionary sleeve (hypothesis 7): code executes Claude's validated decision."""
    from sleeve import book as sleeve_book
    from sleeve import execute as sleeve_exec
    try:
        cfg = sleeve_book.config()
    except FileNotFoundError:
        return None
    try:
        prices, fresh = {}, True
        for s in cfg["universe"] + [cfg["benchmark"]]:
            bars = backtest.load_prices(DATA / f"{s}.csv")
            prices[s] = float(bars["close"].iloc[-1])
            fresh = fresh and is_fresh(bars, a.today)
        if not fresh:
            journal.log({"event": "sleeve", "note": f"no bar for {a.today}; sleeve not traded today"})
            return {"status": "stale prices"}
        if a.dry_run:
            return {"status": "dry run"}
        res = sleeve_exec.run(client, a.today, prices, prices[cfg["benchmark"]], conflicts=taken_symbols)
        for _, _, _, decision in res.get("orders", []):
            summary["orders"].append(decision)
        return res
    except Exception as e:
        journal.log({"event": "sleeve_failed", "error": f"{type(e).__name__}: {e}"})
        alerts.send("Claude sleeve failed", f"{type(e).__name__}: {e}"[:300], "high", ["warning"])
        return {"status": "failed"}


def heartbeat(summary):
    """End-of-run message, so silence never has to be interpreted."""
    orders = summary["orders"]
    parts = [f"{summary['strategies']} strategies promoted"]
    if summary["strategies"]:
        parts += [f"{orders.count('submitted')} orders sent", f"{orders.count('blocked')} blocked",
                  f"{summary['no_action']} no signal", f"{len(summary['skipped'])} skipped"]
    sl = summary.get("sleeve")
    if sl:
        parts.append(f"Claude sleeve: {sl.get('status')}" + (f", value ${sl['value']:,.2f}" if sl.get("value") else ""))
    if risk.HALT_PATH.exists():
        parts.append("HALT file is ON: new positions are blocked")
    msg = ", ".join(parts)
    if summary["skipped"]:
        msg += "\nSkipped: " + "; ".join(summary["skipped"])
    alerts.send(f"Daily run OK {summary['date']}", msg, "low", ["white_check_mark"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--today", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    a = p.parse_args()

    LOCK_PATH.parent.mkdir(exist_ok=True)
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        journal.log({"event": "daily_run", "note": "another run is in progress; exiting"})
        print("Another run_daily.py is already running.")
        return 0

    try:
        heartbeat(run(a))
        return 0
    except Exception as e:
        tb = traceback.format_exc()
        journal.log({"event": "daily_run_failed", "error": f"{type(e).__name__}: {e}", "traceback": tb})
        alerts.send("Daily run FAILED", f"{type(e).__name__}: {e}"[:400], "urgent", ["rotating_light"])
        print(tb, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
