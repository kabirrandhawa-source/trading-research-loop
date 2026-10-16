# momo_quality_v1-2026-10-16

## Saved prediction (unedited)

# Prediction: S&P 500 long-only momentum + cash profitability, v1 (hypothesis 15)

Written 2026-10-16 by desk-quant, after writing strategies/momo_quality_v1.py, stocks/momo_quality.py
and their tests (hand-built frames only), BEFORE running the strategy on any real price data. The only
real-data query run so far is the fundamentals.latest() stale-year count (filings only, no prices or
returns). Version 1; counts against the 5-variation limit. No parameter will be changed after results.

## The test (fixed in advance; full rules in the strategy docstring)
- Universe: point-in-time S&P 500 members on each month-end (stocks.universe.members_on), dead companies
  included; Alpaca daily bars adjusted for splits and dividends (so stock and SPY returns are both
  total-return-like). Only rows before 2024-01-30.
- Formation each month-end close 2016-12-30 .. 2023-12-29 (85 formations); hold to the next month-end
  close; last holding ends 2024-01-29. 12-1 momentum (t-12 anchor for the first formation = 2016-01-04).
- Top decile = round(N/10) by 12-1 return; keep names with 10-K OCF / total assets at or above the median
  of all members that have it (newest fiscal year in a 10-K filed by t and within 15 months, via the new
  fundamentals.latest_annual; assets from the same filing). Uncovered names dropped. Equal weight.
- Index exits sold at their last close (cash at 0% to month-end). Costs 10 bps per side on traded weight
  and exit sales; 20 bps also reported. One-sided monthly turnover reported.
- Benchmark: SPY over the same month-end to month-end windows. CAPM with risk-free = 0 (no T-bill series).
- Comparison basket: pure top decile, equal weight (pre-specified, not a variation).
- Robustness: sector-neutral weights (return-based sectors from 8 SPDRs, rules in the docstring) and a
  25% tech cap, same costs.
- Deflated Sharpe on monthly excess vs SPY; trials = h15 trials + the pure-momentum basket as a
  stand-in for hypothesis 12's related momentum sample (h12 is untested, no recorded Sharpe) + any h12
  recorded trials.

## The bar (all three must hold for passed_backtest; anything else = failed)
Net of 10 bps per side:
1. Monthly excess return vs SPY has t-stat > 2 (plain t on 85 monthly differences).
2. CAPM alpha vs SPY (monthly, OLS) is positive.
3. CAPM alpha of the SECTOR-NEUTRAL weighting is also positive.

Also reported, not part of the pass/fail bar (they are the memo's original claim): screened CAGR above
SPY's, and screened max drawdown shallower than the pure-momentum basket's.

## What I honestly expect (central guess, with a rough range)
- Screened basket CAGR net 10 bps: about 14% a year (range 9% to 19%); SPY about 13-14% over these months.
- Monthly excess vs SPY: about +0.5% a year (range -4% to +5%); tracking error 10-14% a year;
  excess t-stat about 0.2 (range -1 to 1.5). t > 2 would need an information ratio near 0.75: unlikely.
- CAPM beta 0.95 to 1.15; alpha about +0.5% a year with t well below 2. Sign could go either way.
- Sector-neutral alpha: smaller than the equal-weight alpha (momentum's 2020-21 tech and 2022 energy tilts
  are removed); sign a coin flip.
- Win rate: beats SPY in about 50% of months (range 42% to 58%); positive in about 63% of months.
- Max drawdown on monthly marks: about -25% (range -18% to -35%), similar to SPY's (about -24%, 2022).
  Pure momentum about -28%. I give roughly even odds that the screen gives a shallower drawdown.
- Turnover: one-sided about 40-60% a month; costs at 10 bps cost about 1% a year, at 20 bps about 2%.
- Coverage: about 5-15% of top-decile names dropped for missing 10-K OCF/assets, more in 2017.
  Index exits from held names: a handful (under 15 in total).
- Worst months: March 2020 and one of 2022 (or Jan 2023 momentum reversal) for excess.
- Deflated Sharpe on excess vs SPY: well under 0.95.
- Probability the bar passes: about 10%.

## What would make me suspicious of a pass
Excess t > 2 driven by one or two months (check the worst/best months and by-year table); a big gap
between sector-neutral and equal-weight alpha (a sector bet, not momentum/quality); coverage gaps that
skew toward later-dead firms (survivorship in the screen); any position marked after 2024-01-29.

A pass earns Skeptic review and then the sealed test (2024-01-30 onward) only with Kabir's explicit yes.
Never real money directly.


## Results (summary; full in momo_quality_v1-2026-10-16.json)

```json
{
  "months": 85,
  "first_month_end": "2017-01-31",
  "last_hold_end": "2024-01-29",
  "spy": {
    "cagr": 0.1359296722913792,
    "max_drawdown": -0.23927137312964097,
    "vol_annual": 0.16689591199878942
  },
  "screened": {
    "net10": {
      "cagr": 0.12854249348488467,
      "mean_monthly": 0.011665583638975975,
      "vol_annual": 0.19391838174427728,
      "sharpe_annual_rf0": 0.7218861997946867,
      "excess_mean_monthly": -0.0001654452166110049,
      "excess_annualized": -0.0019853425993320586,
      "excess_t": -0.05007362513287595,
      "tracking_error_annual": 0.10552254752371179,
      "info_ratio_annual": -0.01881439224053926,
      "months_beating_spy_pct": 52.94117647058824,
      "positive_months_pct": 57.647058823529406,
      "capm": {
        "alpha_monthly": 0.0001286745039586139,
        "beta": 0.9751399709898658,
        "alpha_t": 0.037611515928889165,
        "alpha_t_newey_west": 0.038794070501633686,
        "beta_t": 14.061848080217898,
        "r2": 0.7043481181352106
      },
      "alpha_annualized": 0.0015440940475033667,
      "max_drawdown": -0.2450245327435795
    },
    "net20": {
      "cagr": 0.1190521349215301,
      "mean_monthly": 0.010957936696232072,
      "vol_annual": 0.194045210864875,
      "sharpe_annual_rf0": 0.6776525932729803,
      "excess_mean_monthly": -0.0008730921593549082,
      "excess_annualized": -0.010477105912258897,
      "excess_t": -0.2639481638755424,
      "tracking_error_annual": 0.10564319537715601,
      "info_ratio_annual": -0.09917445108371303,
      "months_beating_spy_pct": 52.94117647058824,
      "positive_months_pct": 57.647058823529406,
      "capm": {
        "alpha_monthly": -0.0005840117287534259,
        "beta": 0.9755659094293417,
        "alpha_t": -0.17050671182355126,
        "alpha_t_newey_west": -0.17583707870597715,
        "beta_t": 14.051530605181464,
        "r2": 0.7040423314140869
      },
      "alpha_annualized": -0.007008140745041112,
      "max_drawdown": -0.24970578460894954
    },
    "gross": {
      "cagr": 0.13810578932490358,
      "mean_monthly": 0.012373230581719876,
      "vol_annual": 0.19379498103480014,
      "sharpe_annual_rf0": 0.7661641503191244,
      "excess_mean_monthly": 0.0005422017261328999,
      "excess_annualized": 0.0065064207135947984,
      "excess_t": 0.16428068777343668,
      "tracking_error_annual": 0.10540821751422379,
      "info_ratio_annual": 0.061725934343940705,
      "months_beating_spy_pct": 52.94117647058824,
      "positive_months_pct": 57.647058823529406,
      "capm": {
        "alpha_monthly": 0.0008413607366706703,
        "beta": 0.9747140325503901,
        "alpha_t": 0.24620323208692096,
        "alpha_t_newey_west": 0.25397936712756686,
        "beta_t": 14.071352254886175,
        "r2": 0.7046294398849124
      },
      "alpha_annualized": 0.010096328840048043,
      "max_drawdown": -0.2403179367639886
    },
    "turnover_one_sided_monthly_mean": 0.35208327460257055,
    "exit_sales_total": 0,
    "names_per_month_mean": 23.529411764705884,
    "names_min": 6,
    "relative_drawdown_vs_spy": -0.2644168034252463
  },
  "pure": {
    "net10": {
      "cagr": 0.10261353929170158,
      "mean_monthly": 0.009523055556188847,
      "vol_annual": 0.181037042063973,
      "sharpe_annual_rf0": 0.6312336159021216,
      "excess_mean_monthly": -0.00230797329939813,
      "excess_annualized": -0.02769567959277756,
      "excess_t": -0.8455426233297403,
      "tracking_error_annual": 0.08717568348705951,
      "info_ratio_annual": -0.3176995979261665,
      "months_beating_spy_pct": 45.88235294117647,
      "positive_months_pct": 58.82352941176471,
      "capm": {
        "alpha_monthly": -0.0017389313460186061,
        "beta": 0.9519025808891663,
        "alpha_t": -0.6174101321626132,
        "alpha_t_newey_west": -0.7035588951285611,
        "beta_t": 16.6736594993941,
        "r2": 0.7700900578112703
      },
      "alpha_annualized": -0.020867176152223273,
      "max_drawdown": -0.21308675745346262
    },
    "net20": {
      "cagr": 0.09421682368373285,
      "mean_monthly": 0.00888262694691171,
      "vol_annual": 0.18109485861435956,
      "sharpe_annual_rf0": 0.5885949727039271,
      "excess_mean_monthly": -0.0029484019086752668,
      "excess_annualized": -0.0353808229041032,
      "excess_t": -1.0786403314261694,
      "tracking_error_annual": 0.08729916998866934,
      "info_ratio_annual": -0.4052824661299222,
      "months_beating_spy_pct": 44.70588235294118,
      "positive_months_pct": 57.647058823529406,
      "capm": {
        "alpha_monthly": -0.002379230816681953,
        "beta": 0.9518916656411888,
        "alpha_t": -0.8435459214382603,
        "alpha_t_newey_west": -0.9597162916213461,
        "beta_t": 16.64971430462749,
        "r2": 0.7695807671356232
      },
      "alpha_annualized": -0.028550769800183437,
      "max_drawdown": -0.2240707994500769
    },
    "gross": {
      "cagr": 0.11106889672161668,
      "mean_monthly": 0.010163484165465985,
      "vol_annual": 0.18098109884361357,
      "sharpe_annual_rf0": 0.6738925267051199,
      "excess_mean_monthly": -0.0016675446901209929,
      "excess_annualized": -0.020010536281451913,
      "excess_t": -0.6117571935281229,
      "tracking_error_annual": 0.08705595475791779,
      "info_ratio_annual": -0.2298583289000336,
      "months_beating_spy_pct": 48.23529411764706,
      "positive_months_pct": 58.82352941176471,
      "capm": {
        "alpha_monthly": -0.0010986318753552573,
        "beta": 0.951913496137144,
        "alpha_t": -0.39061116786308253,
        "alpha_t_newey_west": -0.44581610922583154,
        "beta_t": 16.696946387217636,
        "r2": 0.770583889682241
      },
      "alpha_annualized": -0.013183582504263089,
      "max_drawdown": -0.20195564610910133
    },
    "turnover_one_sided_monthly_mean": 0.31665272974877245,
    "exit_sales_total": 13,
    "names_per_month_mean": 49.98823529411764,
    "names_min": 49
  },
  "sector_neutral": {
    "net10": {
      "cagr": 0.09992226579643337,
      "mean_monthly": 0.0095367410296873,
      "vol_annual": 0.19536503644070227,
      "sharpe_annual_rf0": 0.5857798019605366,
      "excess_mean_monthly": -0.002294287825899678,
      "excess_annualized": -0.027531453910796137,
      "excess_t": -0.7101525470426315,
      "tracking_error_annual": 0.10318019338017852,
      "info_ratio_annual": -0.2668288652004511,
      "months_beating_spy_pct": 47.05882352941176,
      "positive_months_pct": 58.82352941176471,
      "capm": {
        "alpha_monthly": -0.002223588497874362,
        "beta": 0.9940242451532916,
        "alpha_t": -0.6642262085790229,
        "alpha_t_newey_west": -0.6527094070146874,
        "beta_t": 14.648922252445924,
        "r2": 0.7210936438546027
      },
      "alpha_annualized": -0.026683061974492342,
      "max_drawdown": -0.27082072020734926
    },
    "net20": {
      "cagr": 0.08678655410521396,
      "mean_monthly": 0.008530337579563806,
      "vol_annual": 0.19539819592555607,
      "sharpe_annual_rf0": 0.5238740842508336,
      "excess_mean_monthly": -0.0033006912760231745,
      "excess_annualized": -0.039608295312278094,
      "excess_t": -1.0218473211351313,
      "tracking_error_annual": 0.1031618164426402,
      "info_ratio_annual": -0.383943368565064,
      "months_beating_spy_pct": 47.05882352941176,
      "positive_months_pct": 57.647058823529406,
      "capm": {
        "alpha_monthly": -0.0032335490920715007,
        "beta": 0.9943249074301795,
        "alpha_t": -0.9660874065022248,
        "alpha_t_newey_west": -0.9486934096719641,
        "beta_t": 14.655896465831571,
        "r2": 0.721285058358022
      },
      "alpha_annualized": -0.03880258910485801,
      "max_drawdown": -0.2861007736377206
    },
    "gross": {
      "cagr": 0.11320273358153687,
      "mean_monthly": 0.010543144479810796,
      "vol_annual": 0.19533463640710136,
      "sharpe_annual_rf0": 0.6476973878511287,
      "excess_mean_monthly": -0.0012878843757761834,
      "excess_annualized": -0.015454612509314201,
      "excess_t": -0.39854858290193007,
      "tracking_error_annual": 0.10320380063011114,
      "info_ratio_annual": -0.14974848227445126,
      "months_beating_spy_pct": 47.05882352941176,
      "positive_months_pct": 61.1764705882353,
      "capm": {
        "alpha_monthly": -0.0012136279036772228,
        "beta": 0.9937235828764032,
        "alpha_t": -0.3624514748107999,
        "alpha_t_newey_west": -0.3564101232490428,
        "beta_t": 14.641211775118933,
        "r2": 0.7208818218544965
      },
      "alpha_annualized": -0.014563534844126674,
      "max_drawdown": -0.2556488115720722
    },
    "turnover_one_sided_monthly_mean": 0.5032398408362925,
    "exit_sales_total": 0,
    "names_per_month_mean": 23.529411764705884,
    "names_min": 6
  },
  "tech_capped": {
    "net10": {
      "cagr": 0.10138862587876818,
      "mean_monthly": 0.009501169995103571,
      "vol_annual": 0.1859988444261434,
      "sharpe_annual_rf0": 0.6129825176764238,
      "excess_mean_monthly": -0.0023298588604834056,
      "excess_annualized": -0.027958306325800868,
      "excess_t": -0.7659993673113785,
      "tracking_error_annual": 0.09714071323079942,
      "info_ratio_annual": -0.28781244645974463,
      "months_beating_spy_pct": 50.588235294117645,
      "positive_months_pct": 56.470588235294116,
      "capm": {
        "alpha_monthly": -0.0017575126142667177,
        "beta": 0.9516232904844609,
        "alpha_t": -0.5595515336980642,
        "alpha_t_newey_west": -0.5644615222778193,
        "beta_t": 14.946992277747949,
        "r2": 0.7291233914063338
      },
      "alpha_annualized": -0.021090151371200613,
      "max_drawdown": -0.2276661786383295
    },
    "net20": {
      "cagr": 0.09132361566921143,
      "mean_monthly": 0.008732710798078925,
      "vol_annual": 0.18609771536708386,
      "sharpe_annual_rf0": 0.5631048686989003,
      "excess_mean_monthly": -0.0030983180575080527,
      "excess_annualized": -0.03717981669009663,
      "excess_t": -1.017628488615961,
      "tracking_error_annual": 0.09723818131277516,
      "info_ratio_annual": -0.38235820732294934,
      "months_beating_spy_pct": 50.588235294117645,
      "positive_months_pct": 56.470588235294116,
      "capm": {
        "alpha_monthly": -0.002529761368269786,
        "beta": 0.9519435971141442,
        "alpha_t": -0.8045679610795531,
        "alpha_t_newey_west": -0.8110536389133349,
        "beta_t": 14.936247558304713,
        "r2": 0.7288392444510746
      },
      "alpha_annualized": -0.03035713641923743,
      "max_drawdown": -0.23244556562368723
    },
    "gross": {
      "cagr": 0.1115378761085426,
      "mean_monthly": 0.010269629192128222,
      "vol_annual": 0.1859036799715281,
      "sharpe_annual_rf0": 0.6629000045852383,
      "excess_mean_monthly": -0.001561399663458759,
      "excess_annualized": -0.01873679596150511,
      "excess_t": -0.5138271757343714,
      "tracking_error_annual": 0.09705034809336752,
      "info_ratio_annual": -0.19306263531872475,
      "months_beating_spy_pct": 50.588235294117645,
      "positive_months_pct": 56.470588235294116,
      "capm": {
        "alpha_monthly": -0.0009852638602636523,
        "beta": 0.9513029838547774,
        "alpha_t": -0.31399396776125105,
        "alpha_t_newey_west": -0.3169556726049082,
        "beta_t": 14.956663351130368,
        "r2": 0.7293788109768136
      },
      "alpha_annualized": -0.011823166323163829,
      "max_drawdown": -0.222860951137537
    },
    "turnover_one_sided_monthly_mean": 0.38285137944699404,
    "exit_sales_total": 0,
    "names_per_month_mean": 23.529411764705884,
    "names_min": 6
  },
  "worst_3_months": [
    {
      "month_end": "2018-10-31",
      "net": -0.1169,
      "spy": -0.0684,
      "excess": -0.0485
    },
    {
      "month_end": "2020-03-31",
      "net": -0.113,
      "spy": -0.1262,
      "excess": 0.0131
    },
    {
      "month_end": "2022-01-31",
      "net": -0.1042,
      "spy": -0.0527,
      "excess": -0.0514
    }
  ],
  "worst_3_excess_months": [
    {
      "month_end": "2021-12-31",
      "excess": -0.0606
    },
    {
      "month_end": "2023-10-31",
      "excess": -0.0576
    },
    {
      "month_end": "2021-03-31",
      "excess": -0.0518
    }
  ],
  "by_year": {
    "2017": {
      "screened_net": 0.3677,
      "pure_net": 0.2025,
      "spy": 0.2175,
      "months": 12
    },
    "2018": {
      "screened_net": -0.0322,
      "pure_net": -0.0882,
      "spy": -0.0496,
      "months": 12
    },
    "2019": {
      "screened_net": 0.2569,
      "pure_net": 0.2191,
      "spy": 0.3114,
      "months": 12
    },
    "2020": {
      "screened_net": 0.2024,
      "pure_net": 0.1462,
      "spy": 0.1845,
      "months": 12
    },
    "2021": {
      "screened_net": 0.1433,
      "pure_net": 0.157,
      "spy": 0.286,
      "months": 12
    },
    "2022": {
      "screened_net": -0.0718,
      "pure_net": -0.0168,
      "spy": -0.1818,
      "months": 12
    },
    "2023": {
      "screened_net": 0.0594,
      "pure_net": 0.0882,
      "spy": 0.2618,
      "months": 12
    },
    "2024": {
      "screened_net": 0.0471,
      "pure_net": 0.0532,
      "spy": 0.0336,
      "months": 1
    }
  },
  "deflated_sharpe": {
    "series": "monthly excess return vs SPY, net 10 bps",
    "trials": "h15 trials + pure-momentum basket (stand-in for untested h12's related momentum sample) + h12 recorded trials (0)",
    "sharpe_per_month": -0.005431247212357274,
    "pure_momentum_sharpe_per_month": -0.09171197419205405,
    "dsr": 0.3669,
    "sr0": 0.03171011094020484,
    "n_trials": 2
  },
  "verdict": {
    "checks": {
      "excess_t_gt_2": false,
      "capm_alpha_positive": true,
      "sector_neutral_alpha_positive": false
    },
    "pass": false,
    "claim_beats_spy_after_costs": false,
    "claim_lower_max_dd_than_pure": false
  },
  "exits": {
    "screened_exit_sales": 0,
    "names": []
  },
  "data": {
    "prices": "Alpaca daily bars adjustment=all (splits+dividends) for stocks and SPY: total-return-like",
    "risk_free": "taken as 0 in CAPM (no T-bill series in repo)",
    "sealed_start": "2024-01-30",
    "params": {
      "decile": 0.1,
      "prof_quantile": 0.5,
      "max_age_months": 15,
      "anchor_ffill_days": 5,
      "cost_bps": 10.0,
      "stress_cost_bps": 20.0,
      "sector_lookback": 252,
      "sector_min_days": 126,
      "sector_min_corr": 0.1,
      "tech_cap": 0.25,
      "sector_etfs": [
        "XLK",
        "XLF",
        "XLE",
        "XLV",
        "XLY",
        "XLP",
        "XLU",
        "XLI"
      ],
      "first_formation": "2016-12-30",
      "last_hold_end": "2024-01-29"
    }
  }
}
```
