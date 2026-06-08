"""Tests for arena.py — the local paper-trade arena (E19-S2).

The arena is a pure leaf that orchestrates the look-ahead-safe ``backtest.engine``:
it runs the cortex strategy and each baseline (buy-and-hold + rule baselines) over
one close+volume frame and reports their equity curves, summaries, relative
performance, and the cortex's per-factor attribution. These tests lock that
contract and prove the look-ahead guard is inherited (not re-derived) from the
engine, plus that buy-and-hold is future-free by construction.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd

from domdhi_crypto.backtest import arena, engine

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

# rsi_centered: RSI(close, 14) - 50  → enter when RSI>60, exit when RSI<40
CORTEX_RULE = engine.SignalRule(
    factor_name="rsi_centered",
    expression="RSI(close, 14) - 50",
    entry_threshold=10.0,
    exit_threshold=-10.0,
)
# price_vs_sma50: (close - SMA(close,50)) / SMA(close,50) → trend baseline
BASELINE_RULE = engine.SignalRule(
    factor_name="price_vs_sma50",
    expression="(close - SMA(close, 50)) / SMA(close, 50)",
    entry_threshold=0.0,
    exit_threshold=0.0,
)


def _frame(n: int = 150) -> pd.DataFrame:
    """A deterministic oscillating + mildly trending close series — strong enough
    swings that RSI(14) crosses 60/40 (so the cortex actually trades)."""
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    i = np.arange(n)
    close = 100.0 + 30.0 * np.sin(2 * np.pi * i / 25.0) + 0.2 * i
    volume = 1000.0 + 50.0 * np.abs(np.cos(2 * np.pi * i / 25.0))
    return pd.DataFrame({"close": close, "volume": volume}, index=idx)


# --------------------------------------------------------------------------- #
# AC1 — cortex + each baseline report an equity curve, a summary, relative perf
# --------------------------------------------------------------------------- #

def test_run_arena_reports_cortex_and_baselines():
    frame = _frame()
    res = arena.run_arena(frame, cortex_rules=[CORTEX_RULE], baseline_rules=[BASELINE_RULE])

    # cortex
    assert isinstance(res.cortex, arena.StrategyResult)
    assert res.cortex.name == "cortex"
    assert isinstance(res.cortex.equity_curve, pd.Series) and len(res.cortex.equity_curve) > 0
    assert "total_return" in res.cortex.summary

    # baselines: buy_and_hold + the one rule baseline
    assert len(res.baselines) == 2
    for b in res.baselines:
        assert isinstance(b, arena.StrategyResult)
        assert isinstance(b.equity_curve, pd.Series) and len(b.equity_curve) > 0
        assert "total_return" in b.summary


def test_relative_performance_is_cortex_minus_baseline():
    frame = _frame()
    res = arena.run_arena(frame, cortex_rules=[CORTEX_RULE], baseline_rules=[BASELINE_RULE])
    cortex_tr = res.cortex.summary["total_return"]
    # one relative entry per baseline, equal to cortex_tr - baseline_tr
    assert set(res.relative) == {b.name for b in res.baselines}
    for b in res.baselines:
        assert math.isclose(res.relative[b.name], cortex_tr - b.summary["total_return"], rel_tol=1e-9, abs_tol=1e-12)


# --------------------------------------------------------------------------- #
# AC2 — baselines include buy-and-hold (closed form) + >=1 rule strategy
# --------------------------------------------------------------------------- #

def test_baselines_include_buy_and_hold_and_a_rule():
    frame = _frame()
    res = arena.run_arena(frame, cortex_rules=[CORTEX_RULE], baseline_rules=[BASELINE_RULE])
    names = {b.name for b in res.baselines}
    assert "buy_and_hold" in names
    assert "price_vs_sma50" in names  # the rule baseline, named by its factor_name


def test_buy_and_hold_is_closed_form_and_future_free():
    frame = _frame()
    bnh = arena.buy_and_hold(frame, initial_cash=10_000.0)
    close = frame["close"]
    assert bnh.name == "buy_and_hold"
    # equity = initial_cash * close / close[0]
    assert math.isclose(bnh.equity_curve.iloc[0], 10_000.0, rel_tol=1e-9)
    assert math.isclose(
        bnh.equity_curve.iloc[-1], 10_000.0 * close.iloc[-1] / close.iloc[0], rel_tol=1e-9
    )
    assert math.isclose(
        bnh.summary["total_return"], close.iloc[-1] / close.iloc[0] - 1.0, rel_tol=1e-9
    )
    # future-free: the value at bar k depends only on close[0..k], not later bars.
    k = 100
    bnh_trunc = arena.buy_and_hold(frame.iloc[: k + 1], initial_cash=10_000.0)
    assert math.isclose(bnh_trunc.equity_curve.iloc[k], bnh.equity_curve.iloc[k], rel_tol=1e-9)


# --------------------------------------------------------------------------- #
# AC3 — per-factor attribution for the cortex strategy
# --------------------------------------------------------------------------- #

def test_attribution_reports_cortex_factor():
    frame = _frame()
    res = arena.run_arena(frame, cortex_rules=[CORTEX_RULE], baseline_rules=[BASELINE_RULE])
    assert isinstance(res.attribution, dict)
    # the oscillating series is designed so the cortex trades — its factor must appear
    assert "rsi_centered" in res.attribution
    stats = res.attribution["rsi_centered"]
    assert set(stats) == {"n_trades", "total_return", "mean_return", "win_rate"}
    assert stats["n_trades"] >= 1


# --------------------------------------------------------------------------- #
# AC4 — look-ahead guard holds: arena is a faithful pass-through to the
# look-ahead-safe engine (no independent re-derivation that could leak), and BnH
# is future-free (above). Truncation consistency mirrors the engine's own guard.
# --------------------------------------------------------------------------- #

def test_cortex_is_faithful_passthrough_to_safe_engine():
    frame = _frame()
    res = arena.run_arena(frame, cortex_rules=[CORTEX_RULE], baseline_rules=[BASELINE_RULE])
    direct = engine.run_backtest(frame, [CORTEX_RULE])
    # identical summary + equity curve → the arena adds no look-ahead of its own
    assert res.cortex.summary == direct.summary
    pd.testing.assert_series_equal(res.cortex.equity_curve, direct.equity_curve)


def test_cortex_equity_is_truncation_consistent():
    frame = _frame()
    k = 120
    trunc = arena.run_arena(frame.iloc[:k], cortex_rules=[CORTEX_RULE], baseline_rules=[BASELINE_RULE])
    direct_trunc = engine.run_backtest(frame.iloc[:k], [CORTEX_RULE])
    pd.testing.assert_series_equal(trunc.cortex.equity_curve, direct_trunc.equity_curve)


# --------------------------------------------------------------------------- #
# AC5 — arena.py is a pure leaf (no cli / dashboard / db imports)
# --------------------------------------------------------------------------- #

def test_arena_is_a_pure_leaf():
    src = Path(arena.__file__).read_text(encoding="utf-8")
    import_lines = [
        ln.strip() for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))
    ]
    joined = " ".join(import_lines)
    for forbidden in (" cli", ".cli", " dashboard", ".dashboard", " db", ".db", "ledger", "risk", "context", "digest"):
        assert forbidden not in joined, f"arena.py must stay a pure leaf — found import of '{forbidden.strip()}'"
