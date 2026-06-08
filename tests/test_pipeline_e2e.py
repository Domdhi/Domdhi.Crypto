"""End-to-end pipeline validation test (Epic 19, Story E19-S1 — FR-33).

Exercises the full pipeline:
    db.load_close_series → ta.analyze → factors.evaluate (BUILTIN_FACTORS)
    → engine.run_backtest → digest.build_digest

All network calls are structurally absent: we seed a temp DB directly,
monkeypatch ``cli.load_coins`` and ``cli.db.connect`` to point at it (mirroring
``tests/test_cli.py::factors_env``), and never call CoinGecko.

Non-degeneracy assertions (FR-33 bar) are applied per stage for both seeded
coins (bitcoin + ethereum), each with 260 daily rows of a strictly-positive,
strictly-varying close series.
"""

import math

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto import cli
from domdhi_crypto.backtest import engine
from domdhi_crypto.report import digest
from domdhi_crypto.shared import db
from domdhi_crypto.signals import factors as factors_mod
from domdhi_crypto.signals import ta

# --------------------------------------------------------------------------- #
# Seeded realistic multi-coin DB fixture — mirrors factors_env in test_cli.py
# --------------------------------------------------------------------------- #

_N = 260  # >= 200 so SMA200 and all long-window factors are non-trivial
_BASE = pd.Timestamp("2023-01-01")
_RNG = np.random.default_rng(0)

# Strictly-positive, varying walk: abs(cumsum(normal)) + 50.0
# Both coins share the same RNG seed but use different draws so they diverge.
_BTC_WALK = np.abs(np.cumsum(_RNG.standard_normal(_N))) + 50.0
_ETH_WALK = np.abs(np.cumsum(_RNG.standard_normal(_N))) + 30.0
_BTC_VOL = np.abs(_RNG.standard_normal(_N)) * 1000 + 100
_ETH_VOL = np.abs(_RNG.standard_normal(_N)) * 800 + 80


def _make_rows(walk, vol):
    return [
        (
            (_BASE + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            float(walk[i]),
            float(vol[i]),
            None,
        )
        for i in range(_N)
    ]


@pytest.fixture
def e2e_env(tmp_path, monkeypatch):
    """Temp DB seeded with bitcoin (BTC) and ethereum (ETH) price histories.

    Coins config and db.connect are monkeypatched exactly as in factors_env so
    that every pipeline stage that goes through cli.db.connect lands on the
    temp file, not the runtime DB.
    """
    dbfile = tmp_path / "e2e.db"
    db.init_db(dbfile)
    conn = db.connect(dbfile)

    db.upsert_coin(conn, "bitcoin", "BTC", "Bitcoin")
    db.upsert_prices(conn, "bitcoin", _make_rows(_BTC_WALK, _BTC_VOL))

    db.upsert_coin(conn, "ethereum", "ETH", "Ethereum")
    db.upsert_prices(conn, "ethereum", _make_rows(_ETH_WALK, _ETH_VOL))

    conn.commit()
    conn.close()

    coins_cfg = {
        "coins": [
            {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"},
            {"id": "ethereum", "symbol": "ETH", "name": "Ethereum"},
        ],
        "vs_currency": "usd",
    }
    monkeypatch.setattr(cli, "load_coins", lambda: coins_cfg)
    # Capture real connect before patching — rebinding cli.db.connect also
    # rebinds db.connect (same object), so we must hold the original explicitly
    # to avoid infinite recursion.
    _orig_connect = db.connect
    monkeypatch.setattr(cli.db, "connect", lambda db_file=None: _orig_connect(dbfile))

    return dbfile, coins_cfg


# --------------------------------------------------------------------------- #
# Stage 1: db.load_close_series — non-degeneracy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("coin_id", ["bitcoin", "ethereum"])
def test_load_close_series_non_degenerate(e2e_env, coin_id):
    """Loaded frame is non-empty, monotonically indexed, finite, and varying."""
    dbfile, _ = e2e_env
    # Use the real connect pointing at the temp file (monkeypatched in cli.db)
    conn = cli.db.connect()
    try:
        frame = db.load_close_series(conn, coin_id)
    finally:
        conn.close()

    assert frame is not None, f"load_close_series returned None for {coin_id}"
    assert not frame.empty, f"frame is empty for {coin_id}"
    assert frame.index.is_monotonic_increasing, f"DatetimeIndex not monotonic for {coin_id}"
    assert np.isfinite(frame["close"]).all(), f"non-finite close values for {coin_id}"
    assert frame["close"].nunique() > 1, f"close series is constant (all-same) for {coin_id}"
    assert len(frame) >= 200, f"fewer than 200 rows for {coin_id}: {len(frame)}"


# --------------------------------------------------------------------------- #
# Stage 2: ta.analyze — non-degeneracy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("coin_id", ["bitcoin", "ethereum"])
def test_ta_analyze_non_degenerate(e2e_env, coin_id):
    """ta.analyze returns finite price/RSI, n_days >= 200, and a signals list."""
    dbfile, _ = e2e_env
    conn = cli.db.connect()
    try:
        frame = db.load_close_series(conn, coin_id)
    finally:
        conn.close()

    result = ta.analyze(frame["close"])

    assert isinstance(result, dict), "ta.analyze must return a dict"
    assert "price" in result and "rsi" in result and "signals" in result

    assert result["n_days"] >= 200, f"n_days < 200: {result['n_days']}"

    price = result["price"]
    assert price is not None and math.isfinite(price), f"price not finite: {price}"

    rsi_v = result["rsi"]
    assert rsi_v is not None and math.isfinite(rsi_v), f"RSI not finite: {rsi_v}"

    assert isinstance(result["signals"], list), "signals must be a list"
    assert len(result["signals"]) > 0, "signals list is empty (SMA200 should fire)"


# --------------------------------------------------------------------------- #
# Stage 3: factors.evaluate over BUILTIN_FACTORS — non-degeneracy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("coin_id", ["bitcoin", "ethereum"])
def test_builtin_factors_non_degenerate(e2e_env, coin_id):
    """Evaluating BUILTIN_FACTORS over the seeded frame yields at least one
    finite, non-constant series (the set as a whole clears the FR-33 bar).

    Some factors (ATR, composite expressions requiring high/low) will raise
    ValueError and are skipped — that is documented behaviour, not a bug.
    Factors that return a scalar (not a Series) are also skipped.
    """
    dbfile, _ = e2e_env
    conn = cli.db.connect()
    try:
        frame = db.load_close_series(conn, coin_id)
    finally:
        conn.close()

    finite_varying_found = False
    successful_series: list[pd.Series] = []

    for factor in factors_mod.BUILTIN_FACTORS:
        try:
            result = factors_mod.evaluate(factor["expression"], frame)
        except (ValueError, KeyError):
            # Known deferred factors (ATR, etc.) or column-not-found — skip
            continue

        if not isinstance(result, pd.Series):
            # Pure scalar expression — not useful for non-degeneracy
            continue

        successful_series.append(result)

        finite_vals = result.dropna()
        if len(finite_vals) == 0:
            continue

        all_finite = np.isfinite(finite_vals).all()
        is_varying = finite_vals.nunique() > 1

        if all_finite and is_varying:
            finite_varying_found = True
            break  # One is enough to pass the bar

    assert len(successful_series) > 0, (
        f"No BUILTIN_FACTORS evaluated to a Series for {coin_id}; "
        "check that the frame has close+volume columns"
    )
    assert finite_varying_found, (
        f"No builtin factor produced a finite, non-constant Series for {coin_id}. "
        f"Got {len(successful_series)} successful series but none were finite+varying."
    )


# --------------------------------------------------------------------------- #
# Stage 4: engine.run_backtest — non-degeneracy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("coin_id", ["bitcoin", "ethereum"])
def test_backtest_non_degenerate(e2e_env, coin_id):
    """run_backtest produces a non-empty equity_curve with a monotonic
    DatetimeIndex, all-finite values, and a summary with the four FR-33 keys.
    """
    dbfile, _ = e2e_env
    conn = cli.db.connect()
    try:
        frame = db.load_close_series(conn, coin_id)
    finally:
        conn.close()

    rule = engine.SignalRule(
        factor_name="rsi_centered",
        expression="RSI(close, 14) - 50",
        entry_threshold=10.0,
        exit_threshold=-10.0,
    )
    result = engine.run_backtest(frame, [rule], initial_cash=10_000.0, slippage_bps=5.0, fee_rate=0.001)

    # equity_curve assertions
    curve = result.equity_curve
    assert isinstance(curve, pd.Series), "equity_curve must be a pd.Series"
    assert len(curve) > 0, "equity_curve is empty"
    assert curve.index.is_monotonic_increasing, "equity_curve index is not monotonic"
    assert np.isfinite(curve.values).all(), "equity_curve contains non-finite values"

    # summary key assertions
    summary = result.summary
    required_keys = {"total_return", "total_realized_return", "win_rate", "max_drawdown"}
    assert required_keys <= summary.keys(), (
        f"summary missing keys: {required_keys - summary.keys()}"
    )
    for key in required_keys:
        val = summary[key]
        assert isinstance(val, float), f"summary[{key!r}] is not float: {type(val)}"
        assert math.isfinite(val), f"summary[{key!r}] is not finite: {val}"


# --------------------------------------------------------------------------- #
# Stage 5: digest.build_digest — non-degeneracy
# --------------------------------------------------------------------------- #


def test_digest_build_digest_non_degenerate(e2e_env):
    """build_digest returns a non-empty Markdown string starting with '# '."""
    dbfile, coins_cfg = e2e_env
    conn = cli.db.connect()
    try:
        result = digest.build_digest(coins_cfg, conn=conn)
    finally:
        conn.close()

    assert isinstance(result, str), "build_digest must return str"
    assert len(result) > 0, "build_digest returned an empty string"
    assert result.startswith("# "), (
        f"build_digest output does not start with '# ' (dated Markdown header); "
        f"got: {result[:50]!r}"
    )
    # Load-bearing: the seeded varying series MUST reach the final stage and fire
    # signals — guards against a regression that silently swallows every coin into
    # the error/quiet branch (which would still pass the header check above).
    assert "## Triggered Signals" in result, (
        "digest has no Triggered Signals section — seeded data did not reach the "
        "final stage (all coins fell into the error/quiet branch)"
    )


# --------------------------------------------------------------------------- #
# Full pipeline integration smoke — one pass through all five stages
# --------------------------------------------------------------------------- #


def test_pipeline_e2e_no_errors(e2e_env):
    """Smoke test: run all five stages end-to-end on both coins with no errors.

    This does not re-assert the per-stage FR-33 bar (the parametrized tests above
    do that); it confirms the stages compose without uncaught exceptions and that
    the final digest is a non-empty Markdown document.
    """
    dbfile, coins_cfg = e2e_env

    rule = engine.SignalRule(
        factor_name="rsi_centered",
        expression="RSI(close, 14) - 50",
        entry_threshold=10.0,
        exit_threshold=-10.0,
    )

    conn = cli.db.connect()
    try:
        for coin_id in ("bitcoin", "ethereum"):
            # Stage 1
            frame = db.load_close_series(conn, coin_id)
            assert frame is not None

            # Stage 2
            analysis = ta.analyze(frame["close"])
            assert "signals" in analysis

            # Stage 3 — evaluate at least the first factor successfully
            evaluated = 0
            for factor in factors_mod.BUILTIN_FACTORS:
                try:
                    series = factors_mod.evaluate(factor["expression"], frame)
                    if isinstance(series, pd.Series):
                        evaluated += 1
                except (ValueError, KeyError):
                    continue
            assert evaluated > 0, f"No factors evaluated for {coin_id}"

            # Stage 4
            bt = engine.run_backtest(frame, [rule], initial_cash=10_000.0)
            assert len(bt.equity_curve) > 0

        # Stage 5
        digest_md = digest.build_digest(coins_cfg, conn=conn)
        assert digest_md.startswith("# ")
        assert "## Triggered Signals" in digest_md
    finally:
        conn.close()
