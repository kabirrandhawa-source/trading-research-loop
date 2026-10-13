"""Download daily bars into data/<SYMBOL>.csv using your Alpaca paper keys.

    python fetch_data.py SPY --start 2015-01-01
"""
import argparse
from datetime import datetime
from pathlib import Path

from broker import data_client


def main():
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--start", default="2015-01-01")
    a = p.parse_args()
    bars = data_client().get_stock_bars(StockBarsRequest(
        symbol_or_symbols=a.symbol, timeframe=TimeFrame.Day,
        start=datetime.fromisoformat(a.start), adjustment="all"))
    df = bars.df.reset_index().drop(columns="symbol")
    out = Path(__file__).parent / "data" / f"{a.symbol}.csv"
    df.to_csv(out, index=False)
    print(f"{len(df)} bars -> {out}")


if __name__ == "__main__":
    main()
