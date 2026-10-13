"""Pre-FOMC drift in SPY (ledger id 2, research/macro_watcher-2026-10-12.md).

The engine decides on a bar's close and fills at the next open, so the memo's close(T-1) ->
close(T) window can't be traded exactly. This version signals at the close of T-2 and exits on
the close of T, i.e. holds open(T-1) -> open(T+1): the only engine window that contains the whole
Lucca-Moench 2pm(T-1) -> 2pm(T) drift. It also includes the statement reaction and one overnight.
"""
from datetime import date

import numpy as np
import pandas as pd

from strategies.base import Strategy

# Scheduled FOMC statement days (T). Unscheduled meetings excluded; March 2020 was replaced by
# emergency actions and is excluded. 2016-2025 checked against the Fed calendar; 2026 should be
# re-checked against federalreserve.gov before any paper use.
FOMC_DATES = [date.fromisoformat(d) for d in """
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28 2026-12-09
""".split()]
_FOMC = np.array(FOMC_DATES, dtype="datetime64[D]")


def _bar_date(bars):
    return pd.Timestamp(bars["timestamp"].iloc[-1]).date()


def weekdays_to_next_fomc(d):
    """Weekdays from d to the next FOMC day on or after d (0 = d is FOMC day). None if none left."""
    later = _FOMC[_FOMC >= np.datetime64(d)]
    if not len(later):
        return None
    return int(np.busday_count(np.datetime64(d), later[0]))


class SpyPreFomc(Strategy):
    NAME = "spy_prefomc"
    VERSION = "1"
    HYPOTHESIS = ("Hold SPY around each scheduled FOMC announcement (open T-1 to open T+1), "
                  "flat otherwise: pre-FOMC drift.")
    HYPOTHESIS_ID = 2

    stop_loss_pct = None      # memo: no stop
    take_profit_pct = None
    max_position_pct = 100.0  # memo: 100% notional when in
    warmup = 0

    def entry(self, bars):
        # Signal at the close of T-2 so the fill lands at the open of T-1.
        return 1 if weekdays_to_next_fomc(_bar_date(bars)) == 2 else 0

    def exit(self, bars, position):
        # Close on the FOMC day itself (fills at the open of T+1); safety cap of 3 bars.
        return weekdays_to_next_fomc(_bar_date(bars)) == 0 or position["bars_held"] >= 3
