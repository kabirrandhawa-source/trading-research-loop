# Literature scout 2026-10-15
Ledger check: no prior momentum/reversal/52-week/funding ideas (searched). Prior paper: Gatev et al (pairs, hyp 11 failed).
Papers (read at abstract/secondary-summary level only):
- Barroso & Santa-Clara, Momentum has its moments, JFE 2015. https://doi.org/10.1016/j.jfineco.2014.11.010
- George & Hwang, The 52-Week High and Momentum Investing, JF 2004. https://doi.org/10.1111/j.1540-6261.2004.00695.x (weak, not registered)

## Idea registered: hypothesis 12, market S&P 500
Monthly 12-1 momentum long top decile / short bottom decile, exposure scaled by target vol / trailing 6-month realised vol of the L/S return.
- Why: momentum crash risk is predictable; paper reports roughly doubled Sharpe 1927-2011. Structural (crash/vol clustering), not speed.
- Conditions: needs dispersion in trends; hurts at sharp market rebounds after bear markets (2009, 2020 style), which scaling should dampen.
- Proven wrong if: scaled Sharpe not above unscaled, or max drawdown not lower, or both near zero after costs and borrow; 2016-Jan2024 dev only.
- Testable: yes, stocks.universe.prices with point-in-time members; no fundamentals needed. Dev window only; sealed data untouched. Caveat: 2016-2024 has few crash episodes (2020 only), so low power; short leg borrow cost unmodelled; a long-only variant is the alternative.
