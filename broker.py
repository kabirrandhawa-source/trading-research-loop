"""Paper-only Alpaca access. Every order goes through submit(), which runs the kill switch
and journals the decision before anything reaches the broker."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

import journal
from risk import check_order

ROOT = Path(__file__).parent
PEAK_PATH = ROOT / "memory" / "peak_equity.json"
PAPER_HOST = "paper-api.alpaca.markets"

load_dotenv(ROOT / "config" / ".env")


def _keys():
    if os.getenv("ALPACA_PAPER", "").lower() != "true":
        raise RuntimeError("ALPACA_PAPER must be 'true'. Live trading is not supported.")
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Alpaca paper keys missing from config/.env")
    return key, secret


def paper_client():
    from alpaca.trading.client import TradingClient

    client = TradingClient(*_keys(), paper=True)
    base = getattr(client, "_base_url", "")
    if PAPER_HOST not in str(getattr(base, "value", base)):
        raise RuntimeError("Client is not pointed at the paper endpoint. Aborting.")
    return client


def data_client():
    from alpaca.data.historical import StockHistoricalDataClient

    return StockHistoricalDataClient(*_keys())


def latest_price(symbol, client=None):
    from alpaca.data.requests import StockLatestTradeRequest

    client = client or data_client()
    return float(client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))[symbol].price)


def account_snapshot(client, peak_path=PEAK_PATH):
    acct = client.get_account()
    equity, last_equity = float(acct.equity), float(acct.last_equity)
    peak_path = Path(peak_path)
    peak = json.loads(peak_path.read_text())["peak"] if peak_path.exists() else equity
    if equity > peak:
        peak = equity
    peak_path.write_text(json.dumps({"peak": peak}))
    positions = {p.symbol: float(p.qty) for p in client.get_all_positions()}
    return {
        "equity": equity,
        "daily_loss_pct": max(0.0, (last_equity - equity) / last_equity * 100) if last_equity else 0.0,
        "drawdown_pct": max(0.0, (peak - equity) / peak * 100) if peak else 0.0,
        "open_positions": len(positions),
        "positions": positions,
    }


def _reduces(positions, symbol, side, qty):
    held = positions.get(symbol, 0.0)
    signed = qty if side == "buy" else -qty
    return held != 0 and (held > 0) != (signed > 0) and abs(signed) <= abs(held)


def submit(strategy, version, symbol, side, qty, market_conditions, reasoning,
           client=None, price_fn=latest_price, peak_path=PEAK_PATH, journal_dir=journal.JOURNAL_DIR):
    """Check, journal, and (if allowed) place a market order on the paper account."""
    if side not in ("buy", "sell") or not qty or qty <= 0:
        raise ValueError("side must be 'buy' or 'sell' and qty must be positive")
    client = client or paper_client()
    entry = {"strategy": strategy, "version": version, "symbol": symbol, "side": side, "qty": qty,
             "market_conditions": market_conditions, "reasoning": reasoning}
    try:
        account = account_snapshot(client, peak_path)
        price = price_fn(symbol)
        order = {"value": qty * price, "reduces_position": _reduces(account["positions"], symbol, side, qty)}
        allowed, why = check_order(order, account)
    except Exception as e:
        allowed, why, account, order = False, f"Pre-trade check errored ({type(e).__name__}: {e}). Order blocked.", None, None

    entry.update({"account": account and {k: v for k, v in account.items() if k != "positions"},
                  "order": order, "risk_check": why})
    if not allowed:
        return journal.log({**entry, "decision": "blocked"}, journal_dir)

    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    try:
        placed = client.submit_order(MarketOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide(side), time_in_force=TimeInForce.DAY))
        return journal.log({**entry, "decision": "submitted", "order_id": str(placed.id)}, journal_dir)
    except Exception as e:
        return journal.log({**entry, "decision": "broker_error", "error": f"{type(e).__name__}: {e}"}, journal_dir)
