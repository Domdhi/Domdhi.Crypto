"""Tests for digest.py — the offline Markdown brief (E15-S1.1).

``build_digest(coins_cfg, *, conn)`` is pure (no IO): it is exercised with an
injected ``tmp_path`` SQLite connection and an in-memory coins config, so no
real ``coins.local.json``/network is touched. ``build()`` is the IO wrapper.

Triggered definition (v1): a coin triggers iff its ``signals.ta["signals"]``
list contains any non-neutral string. ``ta._signals`` always emits a directional
MACD/regime/cross string for any coin with a real series, so in practice the only
NON-triggered coins are stables and no-data coins (ta=None → empty signals). The
"neutral" fixtures here are therefore a stablecoin and a known-but-unfilled coin.
"""

import pandas as pd
import pytest

from domdhi_crypto.report import digest
from domdhi_crypto.shared import db, paths


def _seed_ramp(conn, coin_id, symbol, name, n=260):
    """Seed a strictly-increasing daily close series.

    A monotonic-up series has zero down-days → RSI 100 (overbought), recent
    price above its 200D SMA (bull regime), SMA50 above SMA200 (golden cross),
    and a positive MACD histogram (bullish). Those four signals are all
    non-neutral, so the coin triggers — and the exact qualitative outcome is
    known independently of the implementation.
    """
    base = pd.Timestamp("2023-01-01")
    rows = [
        ((base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"), float(50 + i), 100.0, None)
        for i in range(n)
    ]
    db.upsert_coin(conn, coin_id, symbol, name)
    db.upsert_prices(conn, coin_id, rows)


@pytest.fixture
def digest_conn(tmp_path):
    """tmp DB seeded with a triggered coin (BTC ramp + snapshot), a stablecoin
    (USDT, snapshot only), and a known-but-empty coin (DOGE, no prices)."""
    dbfile = tmp_path / "t.db"
    db.init_db(dbfile)
    conn = db.connect(dbfile)
    _seed_ramp(conn, "bitcoin", "BTC", "Bitcoin")
    # Position price comes from the snapshots table, independent of the TA series.
    # price 1000 @ amount 0.5 → value 500; avg_entry 100 @ 0.5 → cost 50;
    # pl 450 → pl_pct = 450/50*100 = 900.0% (hand-computed independent reference).
    db.insert_snapshot(conn, "bitcoin", "2023-09-18T00:00:00Z", 1000.0, None, None, None, None)
    db.upsert_coin(conn, "tether", "USDT", "Tether")
    db.insert_snapshot(conn, "tether", "2023-09-18T00:00:00Z", 1.0, None, None, None, None)
    db.upsert_coin(conn, "dogecoin", "DOGE", "Dogecoin")  # no prices, no snapshot
    conn.commit()
    yield conn
    conn.close()


TRIGGERED_CFG = {
    "vs_currency": "usd",
    "coins": [
        {"id": "bitcoin", "symbol": "BTC", "amount": 0.5, "avg_entry": 100},
        {"id": "tether", "symbol": "USDT", "stable": True},
        {"id": "dogecoin", "symbol": "DOGE"},
    ],
}

QUIET_ONLY_CFG = {
    "vs_currency": "usd",
    "coins": [
        {"id": "tether", "symbol": "USDT", "stable": True},
        {"id": "dogecoin", "symbol": "DOGE"},
    ],
}


# --------------------------------------------------------------------------- #
# build_digest — triggered coin renders with its exact signal strings
# --------------------------------------------------------------------------- #

def test_triggered_coin_gets_section_with_expected_signals(digest_conn):
    md = digest.build_digest(TRIGGERED_CFG, conn=digest_conn)
    # Section header for the triggered coin
    assert "### BTC" in md
    # A monotonic-up series MUST produce exactly these qualitative signals.
    # (MACD direction is intentionally excluded: a perfectly linear ramp drives
    # the MACD histogram to ~0, so its sign is indeterminate — unlike RSI/regime/
    # cross, which are unambiguous for a strictly increasing series.)
    assert "overbought" in md
    assert "bull regime" in md
    assert "golden cross" in md
    # Counterfactual: the opposite-direction signals must NOT appear for an up-ramp.
    btc_section = md.split("### BTC", 1)[1].split("###", 1)[0]
    assert "oversold" not in btc_section
    assert "bear regime" not in btc_section
    assert "death cross" not in btc_section


def test_triggered_section_embeds_position_pl(digest_conn):
    md = digest.build_digest(TRIGGERED_CFG, conn=digest_conn)
    btc_section = md.split("### BTC", 1)[1].split("###", 1)[0]
    # pl_pct = (500 - 50)/50*100 = 900.0% — hand-computed, not read from impl.
    assert "900" in btc_section


def test_triggered_section_embeds_key_factors(digest_conn):
    md = digest.build_digest(TRIGGERED_CFG, conn=digest_conn)
    btc_section = md.split("### BTC", 1)[1].split("###", 1)[0]
    # factor_values from build_context include the built-in factor names.
    assert "rsi_14" in btc_section


# --------------------------------------------------------------------------- #
# build_digest — non-triggered coins get NO section, only a quiet line
# --------------------------------------------------------------------------- #

def test_non_triggered_coins_get_no_section(digest_conn):
    md = digest.build_digest(TRIGGERED_CFG, conn=digest_conn)
    # Stable + no-data coins are quiet → no per-coin section header for them.
    assert "### USDT" not in md
    assert "### DOGE" not in md
    # ...but they are acknowledged in the quiet-coins summary line.
    assert "USDT" in md
    assert "DOGE" in md


def test_quiet_coins_listed_together(digest_conn):
    md = digest.build_digest(TRIGGERED_CFG, conn=digest_conn)
    # Both quiet symbols appear; neither got promoted to a section.
    quiet_symbols = [s for s in ("USDT", "DOGE") if s in md]
    assert sorted(quiet_symbols) == ["DOGE", "USDT"]


# --------------------------------------------------------------------------- #
# build_digest — zero-trigger fallback document
# --------------------------------------------------------------------------- #

def test_zero_trigger_returns_nonempty_doc_with_marker(digest_conn):
    md = digest.build_digest(QUIET_ONLY_CFG, conn=digest_conn)
    assert md.strip() != ""
    assert "No signals triggered" in md
    # The dated top-level header is always present, even with zero triggers.
    assert md.lstrip().startswith("# ")
    # No coin should have been promoted to a section.
    assert "### " not in md


def test_dated_header_present_when_triggered(digest_conn):
    md = digest.build_digest(TRIGGERED_CFG, conn=digest_conn)
    first_line = md.lstrip().splitlines()[0]
    assert first_line.startswith("# ")
    # Header carries the date (YYYY-) — independent check the year is rendered.
    assert "20" in first_line


# --------------------------------------------------------------------------- #
# finite-number guard (math.isfinite, NOT math.isnan — covers ±inf too)
# --------------------------------------------------------------------------- #

def test_fmt_num_coerces_non_finite_to_placeholder():
    assert digest._fmt_num(float("nan")) == "n/a"
    assert digest._fmt_num(float("inf")) == "n/a"
    assert digest._fmt_num(float("-inf")) == "n/a"
    assert digest._fmt_num(None) == "n/a"


def test_fmt_num_renders_finite_values():
    # Finite value renders as a number (independent: 123.456 → contains "123").
    out = digest._fmt_num(123.456)
    assert out != "n/a"
    assert "123" in out


# --------------------------------------------------------------------------- #
# paths + build() IO wrapper
# --------------------------------------------------------------------------- #

def test_digest_path_is_digest_md_in_data_dir():
    assert paths.DIGEST_FILE == "digest.md"
    assert paths.digest_path() == paths.data_dir() / "digest.md"


def test_build_writes_file_and_returns_path(tmp_path, digest_conn):
    out = tmp_path / "brief.md"
    returned = digest.build(out_path=out, conn=digest_conn, coins_cfg=TRIGGERED_CFG)
    assert returned == out
    assert out.exists()
    # File content equals the pure builder's output for the same inputs.
    expected = digest.build_digest(TRIGGERED_CFG, conn=digest_conn)
    assert out.read_text(encoding="utf-8") == expected


def test_build_defaults_out_path_to_digest_path(tmp_path, monkeypatch, digest_conn):
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    returned = digest.build(conn=digest_conn, coins_cfg=TRIGGERED_CFG)
    assert returned == paths.digest_path()
    assert returned == tmp_path / "digest.md"
    assert returned.exists()
