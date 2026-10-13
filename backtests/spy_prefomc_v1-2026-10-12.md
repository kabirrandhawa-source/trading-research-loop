# spy_prefomc_v1 (2026-10-12)

## Saved prediction (unedited)

# Prediction — spy_prefomc_v1 (ledger id 2), written 2026-10-12, before any backtest

Strategy: strategies/spy_prefomc_v1.py. Long 100% SPY from open(T-1) to open(T+1) around each
scheduled FOMC statement day T, flat otherwise. No stop, no filters, no fitted parameters.
Data: data/SPY.csv dev portion only (2016-01-04 .. 2024-01-29); walk-forward OOS covers roughly
mid-2017 .. Jan 2024 (~52 events). Costs 5 bp one-way (10 bp round trip per event).

Window choice: the engine fills at the next open, so the memo's close(T-1)->close(T) can't be
traded. open(T-1)->open(T+1) is the only window that contains the full published
2pm(T-1)->2pm(T) drift; it also carries the statement/presser reaction and one extra overnight.
Before writing this I checked only the trade count (63 events, all 2-bar holds), not any returns.

## Prior
Weak. The effect was published in 2015 and follow-up work reports it faded; all OOS data is
post-publication, and the 2022 hiking cycle had several bad FOMC days. My honest expectation is
a small positive edge that may not clear the bar below.

## Expected (walk-forward OOS)
- Mean per-event return: about +0.2% net (vs ~+0.1% for a random 2-day SPY hold)
- Annual return: about +1.5% per year (exposure ~16 trading days/year, ~6% of the time)
- Win rate: about 57%
- Max drawdown: about -6% (a handful of bad FOMC weeks at 100% notional)
- OOS annualized Sharpe (daily equity curve incl. flat days): about 0.4
- 2x costs: still positive. Delayed fills (delay=2) are a placebo (window moves post-event):
  I expect that result near zero; a strongly positive delay=2 result is a red flag that the
  edge is generic SPY drift, not FOMC.

## Counts as FAILURE (any one)
1. Walk-forward OOS total return <= 0 after costs.
2. OOS annualized return < 0.8%/yr (≈ what 16 random days of SPY's drift would give).
3. OOS annualized Sharpe < 0.3.
4. OOS win rate < 50%.
5. Return under 2x costs <= 0.

PASS (passed_backtest) only if none of the above trigger. Even then, n≈52 events is weak
evidence, and the sealed test is the human's decision.


## Results

```json
{
  "hypothesis_id": 2,
  "strategy": "spy_prefomc",
  "version": "1",
  "dev_period": [
    "2016-01-04 05:00:00+00:00",
    "2024-01-29 05:00:00+00:00"
  ],
  "sealed_pct": 25.0,
  "regime": "trending_up",
  "walk_forward_oos": {
    "total_return_pct": -8.134,
    "max_drawdown_pct": -12.447,
    "win_rate_pct": 46.16,
    "n_trades": 52,
    "sharpe_annual": -0.273,
    "sharpe_per_period": -0.01719433232888691,
    "skew": 0.11128365384965463,
    "kurtosis": 51.86279821264017,
    "n_obs": 1688
  },
  "folds": [
    {
      "fold": 1,
      "test_from": "2017-05-08 04:00:00+00:00",
      "test_to": "2018-09-10 04:00:00+00:00",
      "total_return_pct": -3.907,
      "max_drawdown_pct": -4.058,
      "win_rate_pct": 20.0,
      "n_trades": 10,
      "sharpe_annual": -1.922,
      "sharpe_per_period": -0.12105372093328663,
      "skew": -5.797828475983731,
      "kurtosis": 49.68963701992236,
      "n_obs": 338
    },
    {
      "fold": 2,
      "test_from": "2018-09-11 04:00:00+00:00",
      "test_to": "2020-01-14 05:00:00+00:00",
      "total_return_pct": -2.209,
      "max_drawdown_pct": -4.244,
      "win_rate_pct": 54.55,
      "n_trades": 11,
      "sharpe_annual": -0.556,
      "sharpe_per_period": -0.035021285995559696,
      "skew": -0.3627603038242409,
      "kurtosis": 44.38199892567672,
      "n_obs": 337
    },
    {
      "fold": 3,
      "test_from": "2020-01-15 05:00:00+00:00",
      "test_to": "2021-05-19 04:00:00+00:00",
      "total_return_pct": -4.665,
      "max_drawdown_pct": -5.992,
      "win_rate_pct": 40.0,
      "n_trades": 10,
      "sharpe_annual": -0.672,
      "sharpe_per_period": -0.04230420635630779,
      "skew": -1.0711742178273747,
      "kurtosis": 41.601408625952445,
      "n_obs": 338
    },
    {
      "fold": 4,
      "test_from": "2021-05-20 04:00:00+00:00",
      "test_to": "2022-09-21 04:00:00+00:00",
      "total_return_pct": 7.152,
      "max_drawdown_pct": -3.634,
      "win_rate_pct": 63.64,
      "n_trades": 11,
      "sharpe_annual": 0.937,
      "sharpe_per_period": 0.059000438855299514,
      "skew": 2.894611442185069,
      "kurtosis": 38.84653202710413,
      "n_obs": 337
    },
    {
      "fold": 5,
      "test_from": "2022-09-22 04:00:00+00:00",
      "test_to": "2024-01-29 05:00:00+00:00",
      "total_return_pct": -4.299,
      "max_drawdown_pct": -8.649,
      "win_rate_pct": 50.0,
      "n_trades": 10,
      "sharpe_annual": -0.657,
      "sharpe_per_period": -0.04139816822473926,
      "skew": -2.9811147517828807,
      "kurtosis": 30.875795229292216,
      "n_obs": 338
    }
  ],
  "stress": {
    "2x_costs": {
      "total_return_pct": -13.957,
      "max_drawdown_pct": -18.878,
      "win_rate_pct": 41.27,
      "n_trades": 63,
      "sharpe_annual": -0.437,
      "sharpe_per_period": -0.027525782832846277,
      "skew": -0.08539637143754353,
      "kurtosis": 55.1566601683913,
      "n_obs": 2030
    },
    "delayed_fills": {
      "total_return_pct": -20.974,
      "max_drawdown_pct": -25.877,
      "win_rate_pct": 39.68,
      "n_trades": 63,
      "sharpe_annual": -0.563,
      "sharpe_per_period": -0.03547383494309508,
      "skew": -3.8038449116700286,
      "kurtosis": 100.98452581143789,
      "n_obs": 2030
    },
    "2x_costs_and_delayed": {
      "total_return_pct": -25.809,
      "max_drawdown_pct": -30.063,
      "win_rate_pct": 39.68,
      "n_trades": 63,
      "sharpe_annual": -0.719,
      "sharpe_per_period": -0.04528035500652285,
      "skew": -3.9716172297589507,
      "kurtosis": 99.37813445293828,
      "n_obs": 2030
    },
    "worst_periods": [
      {
        "from": "2019-12-19 05:00:00+00:00",
        "to": "2020-03-20 04:00:00+00:00",
        "total_return_pct": -0.62,
        "max_drawdown_pct": -0.634,
        "win_rate_pct": 0.0,
        "n_trades": 1,
        "sharpe_annual": -1.634,
        "sharpe_per_period": -0.10290548517602142,
        "skew": -4.336877711906813,
        "kurtosis": 34.151622989054445,
        "n_obs": 62
      },
      {
        "from": "2018-09-24 04:00:00+00:00",
        "to": "2018-12-21 05:00:00+00:00",
        "total_return_pct": -4.639,
        "max_drawdown_pct": -4.956,
        "win_rate_pct": 0.0,
        "n_trades": 3,
        "sharpe_annual": -3.67,
        "sharpe_per_period": -0.23119146899964388,
        "skew": -3.9785572293275386,
        "kurtosis": 19.73741994390824,
        "n_obs": 62
      },
      {
        "from": "2022-03-30 04:00:00+00:00",
        "to": "2022-06-29 04:00:00+00:00",
        "total_return_pct": -4.49,
        "max_drawdown_pct": -7.078,
        "win_rate_pct": 0.0,
        "n_trades": 2,
        "sharpe_annual": -1.579,
        "sharpe_per_period": -0.09946082938315941,
        "skew": -2.4175673726744358,
        "kurtosis": 21.495391393879533,
        "n_obs": 62
      },
      {
        "from": "2021-12-10 05:00:00+00:00",
        "to": "2022-03-11 05:00:00+00:00",
        "total_return_pct": -2.267,
        "max_drawdown_pct": -3.884,
        "win_rate_pct": 0.0,
        "n_trades": 2,
        "sharpe_annual": -1.728,
        "sharpe_per_period": -0.1088665606225256,
        "skew": -1.3584753697525396,
        "kurtosis": 20.91540716242892,
        "n_obs": 62
      },
      {
        "from": "2022-08-11 04:00:00+00:00",
        "to": "2022-11-08 05:00:00+00:00",
        "total_return_pct": -6.113,
        "max_drawdown_pct": -7.51,
        "win_rate_pct": 0.0,
        "n_trades": 2,
        "sharpe_annual": -3.105,
        "sharpe_per_period": -0.19557407239016586,
        "skew": -2.776853289743907,
        "kurtosis": 16.66549712265985,
        "n_obs": 62
      }
    ]
  },
  "deflated_sharpe": {
    "dsr": 0.2406,
    "sr0": 0.0,
    "n_trials": 1
  }
}
```
