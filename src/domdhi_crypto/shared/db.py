"""SQLite storage for crypto price data. All writes are idempotent upserts so
re-running ingest only refreshes/extends data without duplicating rows.

The database lives in the data directory (see ``paths.db_path``). ``connect``
and ``init_db`` accept an explicit path, which keeps them trivially testable
against a temp file or ``:memory:``.
"""
import sqlite3

import pandas as pd

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS coins (
    id     TEXT PRIMARY KEY,
    symbol TEXT,
    name   TEXT
);
CREATE TABLE IF NOT EXISTS prices (
    coin_id    TEXT,
    date       TEXT,            -- YYYY-MM-DD (UTC)
    close      REAL,
    volume     REAL,
    market_cap REAL,
    PRIMARY KEY (coin_id, date)
);
CREATE TABLE IF NOT EXISTS ohlc (
    coin_id TEXT,
    ts      INTEGER,            -- epoch ms (candle open)
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    PRIMARY KEY (coin_id, ts)
);
CREATE TABLE IF NOT EXISTS snapshots (
    coin_id    TEXT,
    fetched_at TEXT,            -- ISO8601 UTC
    price      REAL,
    market_cap REAL,
    change_24h REAL,
    change_7d  REAL,
    change_30d REAL,
    PRIMARY KEY (coin_id, fetched_at)
);
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""

# Ordered list of (version, sql) migration entries applied in ascending version order.
# Migrations only ADD tables/columns (never DROP/rewrite) so the regenerable-cache
# tables (prices/ohlc/snapshots) stay safe to delete+re-ingest; the user-entered
# `transactions` table is the source-of-truth slice that justified migrations (E16).
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            coin_id TEXT,
            ts      TEXT,                                   -- ISO8601 UTC
            side    TEXT CHECK(side IN ('buy','sell')),
            amount  REAL,
            price   REAL,
            fee     REAL
        );
        """,
    ),
]


def migrate(conn):
    """Apply every pending migration and return the current schema version.

    Reads the current version as 0 when schema_version is empty.  All pending
    migrations (version > current) are applied in ascending order — each DDL
    script followed by recording its version — then committed.  Returns the
    unchanged current version when nothing is pending.

    Note: each migration's ``executescript`` issues its own implicit COMMIT, so
    a multi-migration batch is applied step-wise, not as one atomic unit.  This
    is safe here because migrations only ADD tables/columns (never DROP or
    rewrite data): a partially-applied batch leaves earlier additions intact and
    the next ``migrate`` call resumes from the recorded version.

    Self-sufficient: creates ``schema_version`` if absent, so ``migrate`` is safe
    to call on a pre-migrations DB (e.g. one created before the version table
    existed) without first running the full ``SCHEMA`` — this is what lets
    ``connect`` auto-converge any opened DB to the latest schema.
    """
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row[0] is not None else 0

    pending = [(v, sql) for v, sql in sorted(MIGRATIONS) if v > current]
    if not pending:
        return current

    for version, sql in pending:
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))

    conn.commit()
    return pending[-1][0]


def connect(db_file=None):
    conn = sqlite3.connect(db_file or paths.db_path())
    conn.row_factory = sqlite3.Row
    # Converge any opened DB to the latest schema (add-only migrations, idempotent).
    # Read-only commands (dashboard/report/digest) connect without going through
    # init_db, so without this a pre-Epic-16 DB lacking the `transactions` table
    # would make the NAV/ledger panels fail; auto-migrating here keeps every entry
    # point safe regardless of how the DB was first created.
    migrate(conn)
    return conn


def init_db(db_file=None):
    path = db_file or paths.db_path()
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    migrate(conn)
    conn.close()
    return path


def upsert_coin(conn, coin_id, symbol, name):
    conn.execute(
        "INSERT INTO coins(id,symbol,name) VALUES(?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET symbol=excluded.symbol, name=excluded.name",
        (coin_id, symbol, name),
    )


def upsert_prices(conn, coin_id, rows):
    """rows: iterable of (date, close, volume, market_cap)."""
    conn.executemany(
        "INSERT INTO prices(coin_id,date,close,volume,market_cap) VALUES(?,?,?,?,?) "
        "ON CONFLICT(coin_id,date) DO UPDATE SET "
        "close=excluded.close, volume=excluded.volume, market_cap=excluded.market_cap",
        [(coin_id, d, c, v, m) for (d, c, v, m) in rows],
    )


def upsert_ohlc(conn, coin_id, rows):
    """rows: iterable of (ts_ms, open, high, low, close)."""
    conn.executemany(
        "INSERT INTO ohlc(coin_id,ts,open,high,low,close) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(coin_id,ts) DO UPDATE SET "
        "open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close",
        [(coin_id, t, o, h, lo, cl) for (t, o, h, lo, cl) in rows],
    )


def insert_snapshot(conn, coin_id, fetched_at, price, mcap, c24, c7, c30):
    conn.execute(
        "INSERT INTO snapshots"
        "(coin_id,fetched_at,price,market_cap,change_24h,change_7d,change_30d) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(coin_id,fetched_at) DO NOTHING",
        (coin_id, fetched_at, price, mcap, c24, c7, c30),
    )


def load_close_series(conn, coin_id):
    """Return a DataFrame indexed by a *continuous daily* date range with
    close/volume columns, or None if no rows exist.

    CoinGecko can drop the odd day. A gap would silently shift rolling windows
    (a 200-row SMA would no longer span 200 calendar days), so we reindex to a
    gap-free daily range and forward-fill close. Volume is left NaN on inserted
    days — only close feeds the indicators.
    """
    rows = conn.execute(
        "SELECT date, close, volume FROM prices WHERE coin_id=? ORDER BY date",
        (coin_id,),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full)
    df["close"] = df["close"].ffill()
    df.index.name = "date"
    return df


def load_ohlc(conn, coin_id):
    rows = conn.execute(
        "SELECT ts, open, high, low, close FROM ohlc WHERE coin_id=? ORDER BY ts",
        (coin_id,),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("date")


def load_ohlcv_daily(conn, coin_id):
    """Return a continuous-daily OHLCV DataFrame (open/high/low/close/volume) or
    None if no ``ohlc`` rows exist. This is the high/low-bearing companion to
    ``load_close_series`` — it unblocks the OHLCV factors (ATR/WILLR/CCI/AROON/ADX).

    The ``ohlc`` table's candle granularity varies with the ingested range
    (CoinGecko returns 4-hourly candles for <=30 days, daily for 31-365, weekly
    beyond), so we *resample to one bar per UTC day*: ``open`` = first, ``high`` =
    max, ``low`` = min, ``close`` = last. That normalises every granularity to
    daily and is correct even when several intraday candles share a date.

    Gap policy mirrors ``load_close_series``: reindex onto a gap-free daily range
    and forward-fill ``close``; on an inserted (no-candle) day ``open``/``high``/
    ``low`` collapse to that ffilled close, so a synthetic bar has zero true range
    rather than a fabricated high-low spread. ``volume`` is joined from the daily
    ``prices`` table (NaN on days prices lacks) — only the price columns feed the
    high/low indicators.
    """
    rows = conn.execute(
        "SELECT ts, open, high, low, close FROM ohlc WHERE coin_id=? ORDER BY ts",
        (coin_id,),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
    daily = df.groupby("date").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    full = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full)
    daily["close"] = daily["close"].ffill()
    for col in ("open", "high", "low"):
        daily[col] = daily[col].fillna(daily["close"])
    daily.index.name = "date"

    # Join daily volume from the prices table (aligned by date).
    price_df = load_close_series(conn, coin_id)
    if price_df is not None:
        daily["volume"] = price_df["volume"].reindex(daily.index)
    else:
        daily["volume"] = float("nan")
    return daily


def latest_snapshot_price(conn, coin_id):
    row = conn.execute(
        "SELECT price FROM snapshots WHERE coin_id=? ORDER BY fetched_at DESC LIMIT 1",
        (coin_id,),
    ).fetchone()
    return row["price"] if row else None


def insert_transaction(conn, coin_id, ts, side, amount, price, fee):
    """Record a user buy/sell. ``side`` must be 'buy' or 'sell' — the table's
    CHECK constraint raises ``sqlite3.IntegrityError`` otherwise. Unlike the
    cache tables this row is source-of-truth (not re-fetchable), so there is no
    ON CONFLICT clause — every call appends a distinct transaction (the
    AUTOINCREMENT ``id`` is the primary key)."""
    conn.execute(
        "INSERT INTO transactions(coin_id,ts,side,amount,price,fee) "
        "VALUES(?,?,?,?,?,?)",
        (coin_id, ts, side, amount, price, fee),
    )


def load_transactions(conn, coin_id=None):
    """Return transaction rows ordered by ``ts``, then by insertion ``id`` (every
    coin when *coin_id* is None). Rows are ``sqlite3.Row`` so callers index by
    column name.

    The secondary ``id`` sort is load-bearing: ``ts`` is a second-resolution
    ISO8601 string, so two trades recorded in the same second would otherwise
    sort non-deterministically. ``_replay`` (avg-cost P/L) and
    ``validate_transactions`` (oversell/leading-sell detection) both depend on
    same-timestamp rows replaying in insertion order — without the tiebreak a
    buy+sell in the same second could replay sell-first and report a spurious
    oversell or wrong realized P/L. ``id`` is the AUTOINCREMENT primary key, so
    it is monotonic in insertion order.

    Defense-in-depth: ``connect`` auto-migrates so the ``transactions`` table
    normally exists, but a connection built outside ``connect`` (raw sqlite3, a
    read-only DB where migration couldn't write) against a pre-Epic-16 DB would
    otherwise raise ``OperationalError``. Treat a missing table as "no
    transactions" so the ledger/NAV panels degrade to empty rather than erroring."""
    try:
        if coin_id is None:
            return conn.execute(
                "SELECT * FROM transactions ORDER BY ts, id"
            ).fetchall()
        return conn.execute(
            "SELECT * FROM transactions WHERE coin_id=? ORDER BY ts, id",
            (coin_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise
