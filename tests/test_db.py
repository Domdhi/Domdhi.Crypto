"""Tests for the SQLite layer — the README sells "re-run forever, no dupes",
so the idempotent-upsert claim gets tested directly, plus the gap-filling loader.
"""
import sqlite3

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.shared import db


@pytest.fixture
def conn(tmp_path):
    path = db.init_db(tmp_path / "test.db")
    c = db.connect(path)
    yield c
    c.close()


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_connect_auto_migrates_pre_epic16_db(tmp_path):
    """A DB created before the migrations existed (only base cache tables, no
    schema_version/transactions) must converge to the latest schema when opened
    via db.connect() — read-only commands (dashboard/report/digest) rely on this."""
    path = tmp_path / "legacy.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE coins (id TEXT PRIMARY KEY, symbol TEXT, name TEXT);"
        "CREATE TABLE prices (coin_id TEXT, date TEXT, close REAL, volume REAL, "
        "market_cap REAL, PRIMARY KEY (coin_id, date));"
    )
    raw.commit()
    raw.close()
    # pre-condition: no transactions/schema_version table
    pre = sqlite3.connect(path)
    names = {r[0] for r in pre.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    pre.close()
    assert "transactions" not in names and "schema_version" not in names

    conn = db.connect(path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "transactions" in tables, "connect() did not auto-create transactions"
        assert "schema_version" in tables
        # converged to the latest recorded version, and load works (no crash)
        assert (conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0) >= 1
        assert db.load_transactions(conn) == []
    finally:
        conn.close()


def test_load_transactions_missing_table_returns_empty(tmp_path):
    """Defense-in-depth: load_transactions on a connection whose DB lacks the
    table (e.g. built outside connect()) returns [] rather than raising."""
    path = tmp_path / "bare.db"
    raw = sqlite3.connect(path)  # raw conn, never migrated — no transactions table
    raw.row_factory = sqlite3.Row
    try:
        assert db.load_transactions(raw) == []
        assert db.load_transactions(raw, "bitcoin") == []
    finally:
        raw.close()


def test_load_transactions_breaks_same_ts_ties_by_insertion_id(conn):
    """Same-second rows must replay in insertion order — load_transactions sorts
    by (ts, id), so a buy recorded before a sell in the SAME timestamp returns
    buy-first regardless of how SQLite would order a ts-only sort. Without the id
    tiebreak, _replay / validate_transactions could see the sell first and report
    a spurious oversell."""
    ts = "2024-01-01T00:00:00Z"
    db.insert_transaction(conn, "bitcoin", ts, "buy", 1.0, 100.0, 0.0)
    db.insert_transaction(conn, "bitcoin", ts, "sell", 1.0, 110.0, 0.0)
    conn.commit()

    rows = db.load_transactions(conn, "bitcoin")
    assert [r["side"] for r in rows] == ["buy", "sell"]
    # ids are monotonic in insertion order, so the tiebreak is well-defined
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)

    # all-coins path applies the same tiebreak
    all_rows = db.load_transactions(conn)
    assert [r["side"] for r in all_rows] == ["buy", "sell"]


def test_init_db_creates_all_tables(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert {"coins", "prices", "ohlc", "snapshots"} <= tables


def test_upsert_prices_is_idempotent(conn):
    rows = [("2024-01-01", 100.0, 5.0, 1000.0), ("2024-01-02", 110.0, 6.0, 1100.0)]
    db.upsert_prices(conn, "bitcoin", rows)
    db.upsert_prices(conn, "bitcoin", rows)  # re-run: must not duplicate
    conn.commit()
    assert _count(conn, "prices") == 2


def test_upsert_prices_updates_in_place(conn):
    db.upsert_prices(conn, "bitcoin", [("2024-01-01", 100.0, 5.0, 1000.0)])
    db.upsert_prices(conn, "bitcoin", [("2024-01-01", 999.0, 7.0, 2000.0)])
    conn.commit()
    row = conn.execute(
        "SELECT close, volume, market_cap FROM prices WHERE coin_id='bitcoin'"
    ).fetchone()
    assert _count(conn, "prices") == 1
    assert tuple(row) == (999.0, 7.0, 2000.0)


def test_upsert_coin_updates_symbol_and_name(conn):
    db.upsert_coin(conn, "bitcoin", "BTC", "Bitcoin")
    db.upsert_coin(conn, "bitcoin", "XBT", "Bitcoin Renamed")
    conn.commit()
    assert _count(conn, "coins") == 1
    row = conn.execute("SELECT symbol, name FROM coins WHERE id='bitcoin'").fetchone()
    assert tuple(row) == ("XBT", "Bitcoin Renamed")


def _ohlc_candle(date, o, h, low_, c):
    return (int(pd.Timestamp(date, tz="UTC").timestamp() * 1000), o, h, low_, c)


def test_load_ohlcv_daily_returns_none_without_rows(conn):
    assert db.load_ohlcv_daily(conn, "bitcoin") is None


def test_load_ohlcv_daily_has_full_ohlcv_columns_and_continuous_index(conn):
    base = pd.Timestamp("2023-01-01")
    candles, prices = [], []
    for i in range(10):
        d = (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        o = 100.0 + i
        candles.append(_ohlc_candle(d, o, o + 2, o - 2, o + 1))
        prices.append((d, o + 1, 1000.0 + i, None))
    db.upsert_ohlc(conn, "bitcoin", candles)
    db.upsert_prices(conn, "bitcoin", prices)
    conn.commit()

    frame = db.load_ohlcv_daily(conn, "bitcoin")
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 10
    # high/low/open are real (not collapsed) on days that have a candle
    assert frame["high"].iloc[0] == pytest.approx(102.0)
    assert frame["low"].iloc[0] == pytest.approx(98.0)
    assert frame["volume"].iloc[0] == pytest.approx(1000.0)


def test_load_ohlcv_daily_resamples_intraday_candles_to_one_day(conn):
    """Sub-daily candles (CoinGecko's <=30d granularity) collapse to one daily bar:
    open=first, high=max, low=min, close=last."""
    base = pd.Timestamp("2023-01-01", tz="UTC")
    candles = [
        (int(base.timestamp() * 1000), 10.0, 15.0, 9.0, 12.0),
        (int((base + pd.Timedelta(hours=12)).timestamp() * 1000), 12.0, 20.0, 11.0, 18.0),
    ]
    db.upsert_ohlc(conn, "eth", candles)
    conn.commit()
    frame = db.load_ohlcv_daily(conn, "eth")
    assert len(frame) == 1
    assert frame["open"].iloc[0] == pytest.approx(10.0)
    assert frame["high"].iloc[0] == pytest.approx(20.0)
    assert frame["low"].iloc[0] == pytest.approx(9.0)
    assert frame["close"].iloc[0] == pytest.approx(18.0)


def test_load_ohlcv_daily_fills_gap_days_with_zero_range_bars(conn):
    """A missing candle day is reindexed in; its open/high/low collapse to the
    ffilled close so the synthetic bar has zero true range (no fabricated spread)."""
    candles = [
        _ohlc_candle("2023-01-01", 100.0, 102.0, 98.0, 101.0),
        # skip 2023-01-02
        _ohlc_candle("2023-01-03", 105.0, 107.0, 103.0, 106.0),
    ]
    db.upsert_ohlc(conn, "bitcoin", candles)
    conn.commit()
    frame = db.load_ohlcv_daily(conn, "bitcoin")
    assert len(frame) == 3  # gap day inserted
    gap = frame.loc["2023-01-02"]
    assert gap["close"] == pytest.approx(101.0)  # ffilled from 2023-01-01
    assert gap["high"] == gap["low"] == gap["open"] == pytest.approx(101.0)


def test_upsert_ohlc_is_idempotent(conn):
    candles = [(1_700_000_000_000, 1.0, 2.0, 0.5, 1.5)]
    db.upsert_ohlc(conn, "bitcoin", candles)
    db.upsert_ohlc(conn, "bitcoin", candles)
    conn.commit()
    assert _count(conn, "ohlc") == 1


def test_insert_snapshot_keeps_first_on_duplicate_timestamp(conn):
    db.insert_snapshot(conn, "bitcoin", "2024-01-01T00:00:00Z", 100.0, 1, 1, 1, 1)
    db.insert_snapshot(conn, "bitcoin", "2024-01-01T00:00:00Z", 222.0, 2, 2, 2, 2)
    conn.commit()
    assert _count(conn, "snapshots") == 1
    # DO NOTHING -> the original price is preserved.
    assert db.latest_snapshot_price(conn, "bitcoin") == 100.0


def test_latest_snapshot_price_picks_newest(conn):
    db.insert_snapshot(conn, "bitcoin", "2024-01-01T00:00:00Z", 100.0, 1, 1, 1, 1)
    db.insert_snapshot(conn, "bitcoin", "2024-01-02T00:00:00Z", 105.0, 1, 1, 1, 1)
    conn.commit()
    assert db.latest_snapshot_price(conn, "bitcoin") == 105.0


def test_load_close_series_none_when_empty(conn):
    assert db.load_close_series(conn, "bitcoin") is None


def test_load_close_series_fills_date_gaps(conn):
    # Deliberately skip 2024-01-03 and 2024-01-04.
    rows = [
        ("2024-01-01", 100.0, 1.0, 1.0),
        ("2024-01-02", 110.0, 1.0, 1.0),
        ("2024-01-05", 130.0, 1.0, 1.0),
    ]
    db.upsert_prices(conn, "bitcoin", rows)
    conn.commit()
    df = db.load_close_series(conn, "bitcoin")
    # Reindexed to a continuous daily range (5 calendar days, no holes).
    assert len(df) == 5
    expected = pd.date_range("2024-01-01", "2024-01-05", freq="D")
    assert list(df.index) == list(expected)
    # close is forward-filled across the gap; never NaN.
    assert not df["close"].isna().any()
    assert df.loc["2024-01-03", "close"] == 110.0
    assert df.loc["2024-01-04", "close"] == 110.0
    # Volume is left untouched (NaN) on the inserted days.
    assert np.isnan(df.loc["2024-01-03", "volume"])


# --------------------------------------------------------------------------- #
# Schema-migration scaffolding (E16-S1)
# --------------------------------------------------------------------------- #

def test_schema_version_table_exists(conn):
    # init_db must create the schema_version table (baseline for migrations).
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "schema_version" in tables


def test_migrate_treats_empty_version_table_as_zero(conn):
    # An empty schema_version reads as version 0: clearing it makes migrate()
    # re-apply every registered migration from scratch (DDL is idempotent).
    conn.execute("DELETE FROM schema_version")
    conn.commit()
    assert (conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0) == 0
    returned = db.migrate(conn)
    expected = max([v for v, _ in db.MIGRATIONS], default=0)
    assert returned == expected


def test_migrate_applies_pending_and_records_version(conn, monkeypatch):
    # Engine test with a throwaway migration ABOVE every shipped version so it is
    # always pending regardless of how many real migrations the registry holds.
    monkeypatch.setattr(db, "MIGRATIONS", [(999, "CREATE TABLE _mt (x INTEGER);")])
    returned = db.migrate(conn)
    conn.commit()
    assert returned == 999
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 999
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "_mt" in tables


def test_migrate_is_idempotent(conn, monkeypatch):
    # Second call on an already-current DB applies nothing: version unchanged AND
    # row counts in coins/prices/snapshots unchanged (asserted, not assumed).
    monkeypatch.setattr(db, "MIGRATIONS", [(1, "CREATE TABLE _mt (x INTEGER);")])
    db.upsert_prices(conn, "bitcoin", [("2024-01-01", 100.0, 1.0, 1.0)])
    db.insert_snapshot(conn, "bitcoin", "2024-01-01T00:00:00Z", 100.0, 1, 1, 1, 1)
    conn.commit()
    first = db.migrate(conn)
    conn.commit()
    counts = (_count(conn, "coins"), _count(conn, "prices"), _count(conn, "snapshots"))
    second = db.migrate(conn)  # no-op
    conn.commit()
    assert second == first  # version unchanged
    assert (_count(conn, "coins"), _count(conn, "prices"), _count(conn, "snapshots")) == counts


def test_migrate_preserves_existing_rows(conn, monkeypatch):
    # A populated DB run through migrate() keeps every pre-existing row
    # (independent row-count + spot value, not just "no error").
    monkeypatch.setattr(db, "MIGRATIONS", [(1, "CREATE TABLE _mt (x INTEGER);")])
    db.upsert_prices(conn, "bitcoin", [
        ("2024-01-01", 100.0, 5.0, 1000.0),
        ("2024-01-02", 110.0, 6.0, 1100.0),
    ])
    db.insert_snapshot(conn, "bitcoin", "2024-01-01T00:00:00Z", 100.0, 1, 1, 1, 1)
    conn.commit()
    db.migrate(conn)
    conn.commit()
    assert _count(conn, "prices") == 2
    assert _count(conn, "snapshots") == 1
    row = conn.execute(
        "SELECT close FROM prices WHERE coin_id='bitcoin' AND date='2024-01-02'"
    ).fetchone()
    assert row[0] == 110.0


def test_init_db_converges_to_latest_version(conn):
    # init_db (run by the fixture) applied SCHEMA then migrate() with the real
    # registry; the recorded version equals the latest registered migration
    # (0 when the registry is empty).
    expected = max([v for v, _ in db.MIGRATIONS], default=0)
    cur = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
    assert cur == expected


# --------------------------------------------------------------------------- #
# transactions table + helpers (E16-S2)
# --------------------------------------------------------------------------- #

def test_transactions_table_created_by_migration(conn):
    # The transactions table arrives via an E16-S1 migration (not a raw SCHEMA
    # edit); init_db -> migrate must have created it.
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "transactions" in tables


def test_insert_and_load_transactions_ordered_by_ts(conn):
    # Insert out of chronological order; load_transactions returns them by ts.
    db.insert_transaction(conn, "bitcoin", "2024-01-02T00:00:00Z", "sell", 1.0, 250.0, 0.0)
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 2.0, 100.0, 0.0)
    conn.commit()
    rows = db.load_transactions(conn, "bitcoin")
    assert [r["ts"] for r in rows] == ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"]
    assert rows[0]["side"] == "buy"
    assert rows[1]["side"] == "sell"
    assert rows[0]["amount"] == 2.0


def test_load_transactions_all_coins_when_none(conn):
    db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "buy", 1.0, 100.0, 0.0)
    db.insert_transaction(conn, "ethereum", "2024-01-02T00:00:00Z", "buy", 5.0, 10.0, 0.0)
    conn.commit()
    rows = db.load_transactions(conn)  # coin_id=None -> every coin
    assert len(rows) == 2
    assert {r["coin_id"] for r in rows} == {"bitcoin", "ethereum"}


def test_transactions_check_rejects_bad_side(conn):
    # CHECK(side IN ('buy','sell')) must reject anything else.
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_transaction(conn, "bitcoin", "2024-01-01T00:00:00Z", "hodl", 1.0, 100.0, 0.0)
        conn.commit()
