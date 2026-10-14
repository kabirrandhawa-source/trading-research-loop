"""Benchmark, not a research result: hold SPY at 9.5% of the paper account.

Exercises the whole paper-trading path every day (orders, fills, the kill switch, journal, alerts,
dashboard) and gives future strategies a yardstick to beat on paper. Listed in paper/benchmarks.json,
never in the hypothesis ledger. 9.5% stays under the 10% per-position limit even if the price moves
between sizing and the order check.
"""
from strategies.base import Strategy


class BenchmarkSPY(Strategy):
    NAME = "benchmark_spy"
    VERSION = "1"
    HYPOTHESIS = "Benchmark: buy and hold SPY at 9.5% of equity."
    HYPOTHESIS_ID = None
    stop_loss_pct = None
    take_profit_pct = None
    max_position_pct = 9.5

    def entry(self, bars):
        return 1

    def exit(self, bars, position):
        return False
