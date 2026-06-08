"""Tests for the thin ledger (E16-S2): NAV-over-time + average-cost P/L.

All reference values are hand-computed, not read back from the implementation.

NAV = sum over coins of holding_amount * daily_close (stables at amount * 1).
Average-cost P/L, fee-aware:
  buy : total_cost += amount*price + fee ;          total_amount += amount
  sell: avg = total_cost/total_amount
        realized += amount*price - amount*avg - fee
        total_cost -= amount*avg ;                   total_amount -= amount
  unrealized = remaining_amount * (latest_snapshot_price - avg)
"""
import pandas as pd
import pytest

from domdhi_crypto.portfolio import ledger
from domdhi_crypto.shared import db


@pytest.fixture
def conn(tmp_path):
    path = db.init_db(tmp_path / "test.db")
    c = db.connect(path)
    yield c
    c.close()


def test_nav_series_two_coins(conn):
    db.upsert_prices(conn, "bitcoin", [
        ("2024-01-01", 100.0, 1.0, 1.0),
        ("2024-01-02", 110.0, 1.0, 1.0),
        ("2024-01-03", 120.0, 1.0, 1.0),
    ])
    db.upsert_prices(conn, "ethereum", [
        ("2024-01-01", 10.0, 1.0, 1.0),
        ("2024-01-02", 20.0, 1.0, 1.0),
        ("2024-01-03", 30.0, 1.0, 1.0),
    ])
    conn.commit()
    cfg = {"coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 2.0, "avg_entry": 50.0, "stable": False},
        {"id": "ethereum", "symbol": "ETH", "amount": 5.0, "avg_entry": 5.0, "stable": False},
    ]}
    nav = ledger.nav_series(conn, cfg)
    # 2*100 + 5*10 = 250 ; 2*110 + 5*20 = 320 ; 2*120 + 5*30 = 390
    assert list(nav.index) == list(pd.date_range("2024-01-01", "2024-01-03", freq="D"))
    assert list(nav.values) == [250.0, 320.0, 390.0]


def test_nav_includes_stable_at_amount(conn):
    db.upsert_prices(conn, "bitcoin", [
        ("2024-01-01", 100.0, 1.0, 1.0),
        ("2024-01-02", 110.0, 1.0, 1.0),
    ])
    conn.commit()
    cfg = {"coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 1.0, "avg_entry": 50.0, "stable": False},
        {"id": "usdc", "symbol": "USDC", "amount": 1000.0, "avg_entry": 1.0, "stable": True},
    ]}
    nav = ledger.nav_series(conn, cfg)
    # BTC 1*100 / 1*110 plus stable USDC 1000*1 each date (no snapshot -> price_or_1 = 1).
    assert list(nav.values) == [1100.0, 1110.0]


def test_realized_and_unrealized_pl_avg_cost(conn):
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 1.0, 100.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "buy", 1.0, 200.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-03T00:00:00Z", "sell", 1.0, 250.0, 0.0)
    db.insert_snapshot(conn, "bitcoin", "2024-01-03T00:00:00Z", 300.0, 1, 1, 1, 1)
    conn.commit()
    cfg = {"coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 1.0, "avg_entry": 150.0, "stable": False},
    ]}
    # avg after two buys = 150; sell 1 @ 250 -> realized = 250 - 150 = 100.
    assert ledger.realized_pl(conn) == pytest.approx(100.0)
    # remaining 1 @ avg 150, snapshot 300 -> unrealized = 150.
    assert ledger.unrealized_pl(conn, cfg) == pytest.approx(150.0)


def test_realized_unrealized_with_fees(conn):
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 2.0, 100.0, 10.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "sell", 1.0, 150.0, 5.0)
    db.insert_snapshot(conn, "bitcoin", "2024-01-02T00:00:00Z", 150.0, 1, 1, 1, 1)
    conn.commit()
    cfg = {"coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 1.0, "avg_entry": 105.0, "stable": False},
    ]}
    # cost = 2*100 + 10 = 210, avg = 105. sell 1 @ 150 fee 5 -> 150 - 105 - 5 = 40.
    assert ledger.realized_pl(conn) == pytest.approx(40.0)
    # remaining 1 @ avg 105, snapshot 150 -> unrealized = 45.
    assert ledger.unrealized_pl(conn, cfg) == pytest.approx(45.0)


def test_oversell_clamps_to_flat(conn):
    # Documented thin-ledger boundary: selling more than held is clamped, not
    # rejected. buy 1@100, sell 2@150 -> realized on the sold amount at avg 100,
    # position reset to flat (0), no error.
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 1.0, 100.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "sell", 2.0, 150.0, 0.0)
    conn.commit()
    cfg = {"coins": [{"id": "bitcoin", "symbol": "BTC", "amount": 0.0, "avg_entry": 0.0, "stable": False}]}
    # 2*150 - 2*100 = 100 realized; position flat -> 0 unrealized.
    assert ledger.realized_pl(conn) == pytest.approx(100.0)
    assert ledger.unrealized_pl(conn, cfg) == pytest.approx(0.0)


def test_leading_sell_uses_zero_basis(conn):
    # Documented boundary: a sell with no prior buy uses avg=0 (free basis).
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "sell", 1.0, 50.0, 0.0)
    conn.commit()
    assert ledger.realized_pl(conn) == pytest.approx(50.0)


def test_nav_leading_gap_undercounts_then_steps_in(conn):
    # Documented behavior: a shorter-history coin is absent (counted 0) until its
    # first date, then steps in. BTC spans 3 days, ETH starts on day 2.
    db.upsert_prices(conn, "bitcoin", [
        ("2024-01-01", 100.0, 1.0, 1.0),
        ("2024-01-02", 100.0, 1.0, 1.0),
        ("2024-01-03", 100.0, 1.0, 1.0),
    ])
    db.upsert_prices(conn, "ethereum", [
        ("2024-01-02", 10.0, 1.0, 1.0),
        ("2024-01-03", 10.0, 1.0, 1.0),
    ])
    conn.commit()
    cfg = {"coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 1.0, "avg_entry": 0.0, "stable": False},
        {"id": "ethereum", "symbol": "ETH", "amount": 1.0, "avg_entry": 0.0, "stable": False},
    ]}
    nav = ledger.nav_series(conn, cfg)
    # day 1: BTC only (100); day 2-3: BTC+ETH (110).
    assert list(nav.index) == list(pd.date_range("2024-01-01", "2024-01-03", freq="D"))
    assert list(nav.values) == [100.0, 110.0, 110.0]


def test_validate_transactions_coherent_returns_empty(conn):
    # E20-S4: a coherent buy-then-partial-sell sequence has no violations.
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 2.0, 100.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "sell", 1.0, 150.0, 0.0)
    conn.commit()
    rows = db.load_transactions(conn, "bitcoin")
    assert ledger.validate_transactions(rows) == []


def test_validate_transactions_flags_oversell(conn):
    # buy 1, then sell 2 -> oversell; message names the coin and the timestamp.
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 1.0, 100.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "sell", 2.0, 150.0, 0.0)
    conn.commit()
    rows = db.load_transactions(conn, "bitcoin")
    violations = ledger.validate_transactions(rows)
    assert violations
    assert any("oversell" in v.lower() for v in violations)
    assert any("bitcoin" in v for v in violations)
    assert any("2024-01-02" in v for v in violations)


def test_validate_transactions_flags_leading_sell(conn):
    # A sell with no prior buy for the coin is a leading sell.
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "sell", 1.0, 50.0, 0.0)
    conn.commit()
    rows = db.load_transactions(conn, "bitcoin")
    violations = ledger.validate_transactions(rows)
    assert violations
    assert any("leading" in v.lower() for v in violations)
    assert any("bitcoin" in v for v in violations)


def test_validate_transactions_is_per_coin(conn):
    # Running quantity is tracked per coin: BTC coherent, ETH oversold -> only ETH flagged.
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 5.0, 100.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "sell", 1.0, 150.0, 0.0)
    db.insert_transaction(conn, "ethereum", "2024-01-01T00:00:00Z", "buy", 1.0, 10.0, 0.0)
    db.insert_transaction(conn, "ethereum", "2024-01-02T00:00:00Z", "sell", 3.0, 20.0, 0.0)
    conn.commit()
    rows = db.load_transactions(conn)  # all coins
    violations = ledger.validate_transactions(rows)
    assert any("ethereum" in v for v in violations)
    assert not any("bitcoin" in v for v in violations)


def test_validate_does_not_change_clamp_behavior(conn):
    # Calling validate_transactions must not perturb the _replay clamp path: the
    # oversell still clamps to flat with realized=100 (characterization unchanged).
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 1.0, 100.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "sell", 2.0, 150.0, 0.0)
    conn.commit()
    _ = ledger.validate_transactions(db.load_transactions(conn, "bitcoin"))
    assert ledger.realized_pl(conn) == pytest.approx(100.0)


def test_empty_db_returns_empty_and_zero(conn):
    cfg = {"coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 1.0, "avg_entry": 100.0, "stable": False},
    ]}
    nav = ledger.nav_series(conn, cfg)
    assert isinstance(nav, pd.Series)
    assert nav.empty
    assert ledger.realized_pl(conn) == 0.0
    assert ledger.unrealized_pl(conn, cfg) == 0.0
