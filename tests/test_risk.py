"""Tests for the portfolio-risk leaf (E16-S3).

Reference values are hand-derived, not read back from the implementation:
- two identical close series have perfectly correlated returns (corr == 1.0);
- BTC's beta against itself is cov(BTC,BTC)/var(BTC) == 1.0 exactly;
- max_drawdown of a known path is the worst peak-to-trough decline;
- thin/absent data degrades to NaN/empty rather than raising.
"""
import math

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.portfolio import risk
from domdhi_crypto.shared import db

# id -> symbol; amounts/avg_entry give value weights for portfolio_vol.
COINS = {
    "coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 1.0, "avg_entry": 100.0, "stable": False},
        {"id": "ethereum", "symbol": "ETH", "amount": 10.0, "avg_entry": 50.0, "stable": False},
    ]
}

_DATES = [f"2024-01-0{d}" for d in range(1, 6)]  # 5 contiguous days


@pytest.fixture
def conn(tmp_path):
    path = db.init_db(tmp_path / "test.db")
    c = db.connect(path)
    yield c
    c.close()


def _seed(conn, coin_id, closes):
    rows = [(d, c, 1.0, 1.0) for d, c in zip(_DATES, closes, strict=False)]
    db.upsert_prices(conn, coin_id, rows)
    db.insert_snapshot(conn, coin_id, "2024-01-05T00:00:00Z", closes[-1], 1, 1, 1, 1)
    conn.commit()


def test_correlation_identical_series_is_one(conn):
    closes = [100.0, 110.0, 105.0, 120.0, 115.0]
    _seed(conn, "bitcoin", closes)
    _seed(conn, "ethereum", closes)  # identical path -> identical returns
    cm = risk.correlation_matrix(conn, COINS)
    assert cm.loc["BTC", "ETH"] == pytest.approx(1.0)
    assert cm.loc["BTC", "BTC"] == pytest.approx(1.0)


def test_beta_to_btc_self_is_one(conn):
    _seed(conn, "bitcoin", [100.0, 110.0, 105.0, 120.0, 115.0])
    _seed(conn, "ethereum", [50.0, 52.0, 49.0, 55.0, 60.0])
    betas = risk.beta_to_btc(conn, COINS)
    assert betas["BTC"] == pytest.approx(1.0)


def test_beta_empty_without_btc_benchmark(conn):
    eth_only = {"coins": [
        {"id": "ethereum", "symbol": "ETH", "amount": 10.0, "avg_entry": 50.0, "stable": False},
    ]}
    _seed(conn, "ethereum", [50.0, 52.0, 49.0, 55.0, 60.0])
    assert risk.beta_to_btc(conn, eth_only) == {}


def test_max_drawdown_known_path():
    # Running peak 120 -> trough 80 is the worst decline: (80-120)/120 = -1/3.
    s = pd.Series([100.0, 120.0, 90.0, 110.0, 80.0, 130.0])
    assert risk.max_drawdown(s) == pytest.approx(-1.0 / 3.0)


def test_max_drawdown_monotonic_is_zero():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert risk.max_drawdown(s) == pytest.approx(0.0)


def test_portfolio_vol_is_finite_and_positive(conn):
    _seed(conn, "bitcoin", [100.0, 110.0, 105.0, 120.0, 115.0])
    _seed(conn, "ethereum", [50.0, 52.0, 49.0, 55.0, 60.0])
    vol = risk.portfolio_vol(conn, COINS)
    assert math.isfinite(vol)
    assert vol > 0


def test_under_window_returns_nan(conn):
    # One price point per coin -> zero returns -> metrics undefined, not an error.
    db.upsert_prices(conn, "bitcoin", [("2024-01-01", 100.0, 1.0, 1.0)])
    db.upsert_prices(conn, "ethereum", [("2024-01-01", 50.0, 1.0, 1.0)])
    conn.commit()
    vol = risk.portfolio_vol(conn, COINS)
    assert math.isnan(vol)
    # correlation_matrix must not raise; off-diagonal is NaN (or the frame is empty).
    cm = risk.correlation_matrix(conn, COINS)
    if not cm.empty and {"BTC", "ETH"} <= set(cm.columns):
        assert np.isnan(cm.loc["BTC", "ETH"])
