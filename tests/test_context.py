"""Tests for the MCP context-provider module (context.py) — FR-22.

AC-derived (TDD). The load-bearing properties under test:

1. **JSON-safety** — the context is handed to an LLM over MCP, so it must contain
   no NaN and no pandas/callable objects. Tests assert ``json.dumps(result,
   allow_nan=False)`` succeeds (allow_nan=False turns a leaked NaN into an error).
2. **Independent factor reference** — ``factor_values["price_vs_sma20"]`` is checked
   against a rolling-mean computed a *different* way (pandas ``.rolling`` in the
   test) than the builtin expression path, so a wrong factor wiring is caught.
3. **Position math** — value/cost/pl are checked against hand-computed products,
   not against the implementation's own numbers.
4. **No callables leak** — the factor menu must serialize only metadata, never the
   ``FactorFunction.fn`` callable.

The DB is a real temp-file SQLite seeded with a deterministic 260-day series.
"""
import json

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.agent import context
from domdhi_crypto.shared import db
from domdhi_crypto.signals import factors

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_N = 260
_SNAP_PRICE = 60_000.0


def _closes(n=_N):
    """Deterministic, strictly-positive, non-monotonic daily closes."""
    vals = np.cumsum(np.sin(np.arange(n) / 5.0) + np.cos(np.arange(n) / 3.0)) + 200.0
    return [float(v) for v in vals]


@pytest.fixture()
def seeded(tmp_path):
    """Return (conn, coins_cfg) against a temp DB seeded with three coins:

    - bitcoin (BTC): 260 daily prices + a snapshot  → full happy path
    - litecoin (LTC): 260 daily prices, NO snapshot → price None branch
    - usd-coin (USDC): stable, no prices/snapshot    → stablecoin branch
    """
    path = str(tmp_path / "crypto.db")
    db.init_db(path)
    conn = db.connect(path)

    closes = _closes()
    dates = pd.date_range("2023-01-01", periods=_N, freq="D").strftime("%Y-%m-%d")
    rows = [(d, c, 1000.0 + i, c * 10) for i, (d, c) in enumerate(zip(dates, closes, strict=True))]

    for cid, sym in (("bitcoin", "BTC"), ("litecoin", "LTC")):
        db.upsert_coin(conn, cid, sym, sym)
        db.upsert_prices(conn, cid, rows)
    db.upsert_coin(conn, "usd-coin", "USDC", "USD Coin")
    db.insert_snapshot(conn, "bitcoin", "2023-09-18T00:00:00Z", _SNAP_PRICE, 1e12, 1.0, 2.0, 3.0)
    conn.commit()

    coins_cfg = {
        "vs_currency": "usd",
        "coins": [
            {"id": "bitcoin", "symbol": "BTC", "amount": 0.5, "avg_entry": 50_000.0},
            {"id": "litecoin", "symbol": "LTC", "amount": 10, "avg_entry": 80.0},
            {"id": "usd-coin", "symbol": "USDC", "amount": 1000, "avg_entry": 1.0, "stable": True},
        ],
    }
    yield conn, coins_cfg
    conn.close()


# --------------------------------------------------------------------------- #
# Happy path — structure, schema, JSON-safety
# --------------------------------------------------------------------------- #

def test_build_context_top_level_shape(seeded):
    conn, cfg = seeded
    ctx = context.build_context("BTC", conn=conn, coins_cfg=cfg)
    assert ctx["symbol"] == "BTC"
    assert set(ctx) >= {"symbol", "signals", "position", "factor_menu"}
    assert "error" not in ctx


def test_build_context_is_json_safe_no_nan(seeded):
    conn, cfg = seeded
    ctx = context.build_context("BTC", conn=conn, coins_cfg=cfg)
    # allow_nan=False raises if any NaN/Infinity leaked through (the #1 failure mode).
    json.dumps(ctx, allow_nan=False)


def test_build_context_validates_against_schema(seeded):
    conn, cfg = seeded
    ctx = context.build_context("BTC", conn=conn, coins_cfg=cfg)
    # CONTEXT_SCHEMA is the published contract; the module's own validator must pass it.
    assert isinstance(context.CONTEXT_SCHEMA, dict)
    context._validate_context(ctx)  # must not raise


# --------------------------------------------------------------------------- #
# Signals — ta summary + factor_values with an INDEPENDENT reference
# --------------------------------------------------------------------------- #

def test_signals_include_ta_summary(seeded):
    conn, cfg = seeded
    ctx = context.build_context("BTC", conn=conn, coins_cfg=cfg)
    ta_block = ctx["signals"]["ta"]
    # ta.analyze keys that downstream reasoning relies on.
    for key in ("price", "rsi", "macd_hist", "sma20", "sma50", "signals"):
        assert key in ta_block


def test_factor_value_matches_independent_rolling_mean(seeded):
    conn, cfg = seeded
    ctx = context.build_context("BTC", conn=conn, coins_cfg=cfg)
    fv = ctx["signals"]["factor_values"]
    # Independent reference: compute (close - SMA20)/SMA20 via pandas rolling — a
    # different path than the builtin "price_vs_sma20" expression evaluation.
    close = db.load_close_series(conn, "bitcoin")["close"]
    sma20 = close.rolling(20).mean()
    expected = float((close.iloc[-1] - sma20.iloc[-1]) / sma20.iloc[-1])
    assert fv["price_vs_sma20"] == pytest.approx(expected, abs=1e-9)


def test_flat_plateau_series_stays_json_safe(tmp_path):
    """Regression (Wave-1 review CRITICAL-1): a flat-then-step series drives
    factors like vol_adj_momentum to +/-Infinity. math.isnan misses Infinity, so
    inf would leak and break json.dumps(allow_nan=False). Assert it does NOT."""
    path = str(tmp_path / "flat.db")
    db.init_db(path)
    conn = db.connect(path)
    # 60 flat days, then a step, then 40 more flat days → zero-variance windows.
    closes = [100.0] * 60 + [150.0] + [150.0] * 60
    dates = pd.date_range("2023-01-01", periods=len(closes), freq="D").strftime("%Y-%m-%d")
    rows = [(d, c, 1000.0, c * 10) for d, c in zip(dates, closes, strict=True)]
    db.upsert_coin(conn, "bitcoin", "BTC", "BTC")
    db.upsert_prices(conn, "bitcoin", rows)
    conn.commit()
    cfg = {"vs_currency": "usd",
           "coins": [{"id": "bitcoin", "symbol": "BTC", "amount": 1, "avg_entry": 100.0}]}
    ctx = context.build_context("BTC", conn=conn, coins_cfg=cfg)
    conn.close()
    # The load-bearing assertion: serializing with allow_nan=False must not raise.
    json.dumps(ctx, allow_nan=False)
    # And any factor that would have been inf is coerced to None, never left as inf.
    for name, val in ctx["signals"]["factor_values"].items():
        assert val is None or (isinstance(val, float) and np.isfinite(val)), name


def test_under_window_factor_is_none_not_nan(seeded):
    conn, cfg = seeded
    ctx = context.build_context("BTC", conn=conn, coins_cfg=cfg)
    fv = ctx["signals"]["factor_values"]
    # price_vs_ema200 needs 200 pts; with 260 it's defined. Use a factor that is
    # under-window on this series would be None — assert the *type contract*: every
    # value is either a float or None, never a NaN float.
    for name, val in fv.items():
        assert val is None or (isinstance(val, float) and not np.isnan(val)), name


# --------------------------------------------------------------------------- #
# Position — math checked against hand-computed products
# --------------------------------------------------------------------------- #

def test_position_pricing_happy_path(seeded):
    conn, cfg = seeded
    pos = context.build_context("BTC", conn=conn, coins_cfg=cfg)["position"]
    assert pos["price"] == pytest.approx(_SNAP_PRICE)
    assert pos["value"] == pytest.approx(_SNAP_PRICE * 0.5)          # 30000
    assert pos["cost"] == pytest.approx(50_000.0 * 0.5)             # 25000
    assert pos["pl"] == pytest.approx(_SNAP_PRICE * 0.5 - 25_000.0)  # +5000
    assert pos["pl_pct"] == pytest.approx(20.0)


def test_position_missing_snapshot_price_none(seeded):
    conn, cfg = seeded
    # litecoin has prices (so signals exist) but no snapshot → price None, no crash.
    ctx = context.build_context("LTC", conn=conn, coins_cfg=cfg)
    assert ctx["position"]["price"] is None
    assert ctx["position"]["value"] is None
    json.dumps(ctx, allow_nan=False)


# --------------------------------------------------------------------------- #
# Factor menu — metadata only, no callables
# --------------------------------------------------------------------------- #

def test_factor_menu_has_no_callables_and_full_metadata(seeded):
    conn, cfg = seeded
    menu = context.build_context("BTC", conn=conn, coins_cfg=cfg)["factor_menu"]
    assert len(menu["builtin"]) == len(factors.BUILTIN_FACTORS)
    # Every primitive entry carries the FactorFunction metadata keys and NOT the fn.
    for prim in menu["primitives"]:
        assert set(prim) == {"name", "signature", "description", "example", "category"}
        assert "fn" not in prim
    names = {p["name"] for p in menu["primitives"]}
    assert "RSI" in names and "SMA" in names
    # Whole menu must be JSON-safe (a leaked callable would raise here).
    json.dumps(menu, allow_nan=False)


# --------------------------------------------------------------------------- #
# Error & stablecoin branches — structured, never SystemExit
# --------------------------------------------------------------------------- #

def test_unknown_symbol_returns_structured_error(seeded):
    conn, cfg = seeded
    ctx = context.build_context("DOGE", conn=conn, coins_cfg=cfg)
    # A server tool must NOT raise SystemExit on bad input — it returns an error dict.
    assert "error" in ctx
    assert ctx["symbol"] == "DOGE"


def test_stablecoin_has_position_but_no_factor_values(seeded):
    conn, cfg = seeded
    ctx = context.build_context("USDC", conn=conn, coins_cfg=cfg)
    assert ctx["position"]["amount"] == 1000
    assert ctx["signals"]["ta"] is None
    assert ctx["signals"]["factor_values"] == {}
    assert "note" in ctx["signals"]
    json.dumps(ctx, allow_nan=False)
