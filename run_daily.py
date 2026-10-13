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
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import backtest
import broker
import journal
import ledger

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


def promoted(conn):
    rows = conn.execute(
        "SELECT * FROM hypotheses WHERE status = 'passed_backtest' "
        "AND sealed_test_result IS NOT NULL AND strategy_file IS NOT NULL").fetchall()
    out, seen = [], {}
    for h in map(dict, rows):
        sym = h["market"].strip().upper()
        if sym in seen:   # Alpaca nets positions per symbol, so two strategies can't share one
            raise RuntimeError(f"Hypotheses {seen[sym]} and {h['id']} both trade {sym}. Pause one.")
        seen[sym] = h["id"]
        out.append((h, sym))
    return out


def bars_held(strategy, symbol, journal_dir=journal.JOURNAL_DIR):
    """Trading days since this strategy's last submitted opening order on this symbol."""
    opened = None
    for f in sorted(Path(journal_dir).glob("*.jsonl")):
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--today", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    a = p.parse_args()

    refresh_data(universe())
    conn = ledger.connect()
    strategies = promoted(conn)
    if not strategies:
        journal.log({"event": "daily_run", "note": "no strategies promoted to paper yet"})
        print("No strategies promoted to paper yet.")
        return

    client = broker.paper_client()
    positions = {p.symbol: p for p in client.get_all_positions()}
    pending = open_order_symbols(client)
    for h, sym in strategies:
        cls = backtest.load_strategy(ROOT / h["strategy_file"])
        strat = cls()
        if cls.VERSION != h["strategy_version"]:
            journal.log({"event": "skipped", "strategy": cls.NAME, "symbol": sym,
                         "reason": f"file is v{cls.VERSION}, ledger approved v{h['strategy_version']}"})
            continue
        bars = backtest.load_prices(DATA / f"{sym}.csv")
        if sym in pending:
            journal.log({"event": "skipped", "strategy": cls.NAME, "symbol": sym,
                         "reason": "an order for this symbol is still open (holiday or unfilled)"})
            continue
        if not is_fresh(bars, a.today):
            journal.log({"event": "skipped", "strategy": cls.NAME, "symbol": sym,
                         "reason": f"no bar for {a.today} (market closed?); last bar {bars['timestamp'].iloc[-1]}"})
            continue
        pos = positions.get(sym)
        qty = float(pos.qty) if pos else 0.0
        entry_px = float(pos.avg_entry_price) if pos else None
        action, side, why = decide(strat, bars, qty, entry_px, bars_held(cls.NAME, sym))
        cond = conditions(bars)
        if action is None:
            journal.log({"event": "no_action", "strategy": cls.NAME, "version": cls.VERSION,
                         "symbol": sym, "market_conditions": cond, "reasoning": why})
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


if __name__ == "__main__":
    main()
