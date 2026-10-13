import math

import numpy as np
import pandas as pd
import pytest

import ledger
from pm import analyze, model, store
from pm.sources import best_quotes, parse_ts


def test_parse_ts_handles_z_and_fraction_lengths():
    assert parse_ts("2026-10-13T03:45:00Z") == 1791863100.0
    assert abs(parse_ts("2026-10-13T03:45:04.639007Z") - 1791863104.639007) < 1e-6
    assert abs(parse_ts("2026-10-13T03:45:55.553786531Z") - 1791863155.553786) < 1e-5
    assert abs(parse_ts("2026-10-13T03:45:04.6Z") - 1791863104.6) < 1e-6


def test_best_quotes_derives_yes_ask_from_no_bids():
    q = best_quotes([(0.84, 100), (0.83, 50)], [(0.15, 200), (0.14, 10)])
    assert q == {"yes_bid": 0.84, "yes_bid_size": 100, "yes_ask": 0.85, "yes_ask_size": 200}
    assert best_quotes([], [])["yes_ask"] is None


def test_fair_prob_basics():
    s = 1e-4
    assert model.fair_prob(100_000, 100_000, 600, s) == pytest.approx(0.5)
    up = model.fair_prob(100_100, 100_000, 600, s)
    assert 0.5 < up < model.fair_prob(100_100, 100_000, 120, s)        # less time, more certain
    assert model.fair_prob(99_000, 100_000, 600, s) < 0.05
    # final seconds: mostly decided by the average already observed
    assert model.fair_prob(99_990, 100_000, 5, s, known_avg=100_050) > 0.95
    assert model.fair_prob(100_000, 100_000, 0, s, known_avg=100_001) == 1.0


def test_fees_match_published_formula():
    assert model.taker_fee(0.5, 100) == pytest.approx(0.0175)          # $1.75 on 100 contracts
    assert model.taker_fee(0.9, 100) == pytest.approx(0.0063)          # 0.63 -> rounds up to $0.63
    assert model.taker_fee(0.5, 1) == pytest.approx(0.02)              # 1.75c rounds up to 2c
    assert model.maker_fee(0.5) == 0.0 and model.maker_fee(0.5, 100, 0.0175) == pytest.approx(0.0044)


def test_spot_series_forward_fills_without_lookahead():
    s = model.spot_series([(10.5, 100.0), (12.2, 101.0)], 10, 14)
    assert np.isnan(s[10.0]) and s[11.0] == 100.0 and s[12.0] == 100.0 and s[13.0] == 101.0


# ---------- synthetic history: a market that follows spot with a known delay ----------

def build_history(tmp_path, n_windows=6, lag_s=3, seed=1):
    rng = np.random.default_rng(seed)
    conn = store.connect("t", tmp_path)
    t0 = 1_800_000_000.0
    start = t0 - 2400
    secs = np.arange(start, t0 + n_windows * 900 + 60)
    price = 80_000 * np.exp(np.cumsum(rng.normal(0, 2e-4, len(secs))))
    conn.executemany("INSERT INTO spot_trades VALUES ('kraken', ?, ?, ?, 1)",
                     [(i, float(t) + 0.5, float(p)) for i, (t, p) in enumerate(zip(secs, price))])
    S = pd.Series(price, index=secs + 0.5)
    for k in range(n_windows):
        o, c = t0 + 900 * k, t0 + 900 * (k + 1)
        strike = float(S.loc[o - 60:o].mean())
        settle = float(S.loc[c - 60:c].mean())
        conn.execute("INSERT INTO markets VALUES (?, ?, ?, ?, ?, ?, '{}')",
                     (f"W{k}", o, c, strike, settle, "yes" if settle >= strike else "no"))
    conn.commit()
    # market trades = model probability delayed by lag_s seconds
    for w in analyze.windows(conn, "dev", 0.0).itertuples():
        p = analyze.window_model(conn, w)
        lagged = p.shift(lag_s).dropna()
        conn.executemany("INSERT INTO kalshi_trades VALUES (?, ?, ?, ?, 1, 'yes')",
                         [(f"{w.ticker}-{t}", w.ticker, float(t) - 0.1, float(v)) for t, v in lagged.items()])
        mids = p[(p.index % 60 == 0) & (p > 0.03) & (p < 0.97)]
        conn.executemany("INSERT INTO candles VALUES (?, ?, ?, ?, NULL, 0)",
                         [(w.ticker, float(t), v - 0.01, v + 0.01) for t, v in mids.items()])
    conn.commit()
    return conn


def test_lag_analysis_finds_planted_delay(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "SEALED_FRAC", 0.0)
    conn = build_history(tmp_path, lag_s=3)
    r = analyze.lag_analysis(conn, max_lag=8, part="dev")
    assert r["windows"] > 0 and r["peak_lag_s"] == 3


def test_split_keeps_sealed_windows_out(tmp_path):
    conn = build_history(tmp_path, n_windows=10)
    dev, sealed = analyze.windows(conn, "dev"), analyze.windows(conn, "sealed")
    assert len(dev) == 7 and len(sealed) == 3 and dev.close_ts.max() < sealed.open_ts.min() + 1


def test_sim_charges_fees_and_never_trades_on_a_fair_market(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "SEALED_FRAC", 0.0)
    conn = build_history(tmp_path, lag_s=0)   # market == model: no edge beyond the 1c spread
    r = analyze.simulate(conn, edge=0.0, fill="same", part="dev")
    assert r["trades"] == 0


def test_prediction_lock_and_single_sealed_run(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "RESULTS", tmp_path)
    lconn = ledger.connect(tmp_path / "l.db")
    h = ledger.add_hypothesis(lconn, "lag", "human", "BTC")
    memo = tmp_path / "m.md"; memo.write_text("expect no edge after fees")
    analyze.lock_prediction(lconn, h, "taker-v1", memo)
    assert "no edge" in analyze.verify_prediction(lconn, h, "taker-v1")
    with pytest.raises(PermissionError):
        analyze.lock_prediction(lconn, h, "taker-v1", memo)
    with pytest.raises(PermissionError, match="No locked prediction"):
        analyze.verify_prediction(lconn, h, "taker-v2")
