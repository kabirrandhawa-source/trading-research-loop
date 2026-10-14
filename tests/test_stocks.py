import numpy as np
import pandas as pd
import pytest

from stocks import universe as u


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "DIR", tmp_path)
    monkeypatch.setattr(u, "DB", tmp_path / "bars.db")
    members = pd.DataFrame({
        "ticker": ["OLD", "NEW", "GONE", "SWAP", "KEEP"],
        "start_date": pd.to_datetime(["2016-01-01", "2018-01-02", "2016-01-01", "2018-01-02", "2016-01-01"]),
        "end_date": pd.to_datetime(["2018-01-02", None, "2018-01-02", None, None]),
    })
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2016-01-04", "2019-12-31")
    walk = lambda: 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
    same = walk()
    series = {"OLD": same, "NEW": same * 1.02, "GONE": walk(), "SWAP": walk() * 0 + same.mean(), "KEEP": walk()}
    series["SWAP"] = series["GONE"] * 1.01 + rng.normal(0, 5, len(days))   # similar price level, different moves
    conn = u.connect()
    rows = [(s, d.strftime("%Y-%m-%d"), v, v, v, v, 1.0) for s, vals in series.items() for d, v in zip(days, vals)]
    rows += [("GONE", "2019-06-03", 5.0, 5.0, 5.0, 5.0, 1.0)]  # ticker reused by another company later
    conn.executemany("INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return conn, members


def test_members_on_respects_entry_and_exit(setup):
    _, m = setup
    assert u.members_on("2017-06-01", m) == {"OLD", "GONE", "KEEP"}
    assert u.members_on("2018-06-01", m) == {"NEW", "SWAP", "KEEP"}


def test_rename_linked_only_for_the_same_company(setup):
    conn, m = setup
    links = {r[0]: r[1] for r in u.resolve_aliases(conn, m)}
    assert links == {"OLD": "NEW"}          # GONE -> SWAP is an unrelated swap at a similar price: not linked


def test_prices_stop_when_a_stock_leaves_the_index(setup):
    conn, m = setup
    p = u.prices(["GONE"], conn=conn, m=m)
    assert p.day.max() < "2018-01-02"        # the 2019 bar from the ticker's later reuse never appears
    p = u.prices(["OLD"], conn=conn, m=m)
    assert len(p) > 0 and p.day.max() < "2018-01-02"
