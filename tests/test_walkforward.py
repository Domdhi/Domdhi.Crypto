"""Tests for walkforward.py — out-of-sample sub-period validation (E20-S5).

The walk-forward harness runs ONE look-ahead-safe ``engine.run_backtest`` over the
full frame, then segments the resulting equity curve into contiguous, non-overlapping
folds and reports per-fold strategy return vs a buy-and-hold benchmark. These tests
lock that contract and prove the per-fold returns are a *faithful* segmentation of a
direct backtest (no re-derivation, look-ahead safety inherited from the engine).

This is out-of-sample SUB-PERIOD segmentation, NOT walk-forward parameter
optimization — there is no train/fit step. All reference values are computed
directly from ``engine.run_backtest`` / the close series, not read back from the
implementation under test.
"""
import pathlib

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.backtest import engine, walkforward

# rsi_centered: enter when RSI(14)-50 > 10, exit when < -10 (so the cortex trades).
CORTEX_RULE = engine.SignalRule(
    factor_name="rsi_centered",
    expression="RSI(close, 14) - 50",
    entry_threshold=10.0,
    exit_threshold=-10.0,
)


def _frame(n: int = 160) -> pd.DataFrame:
    """Deterministic oscillating + mildly trending close series — strong enough
    swings that RSI(14) crosses 60/40 (so the cortex actually trades)."""
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    i = np.arange(n)
    close = 100.0 + 30.0 * np.sin(2 * np.pi * i / 25.0) + 0.2 * i
    volume = 1000.0 + 50.0 * np.abs(np.cos(2 * np.pi * i / 25.0))
    return pd.DataFrame({"close": close, "volume": volume}, index=idx)


def _expected_fold_bounds(frame: pd.DataFrame, n_splits: int):
    """(lo, hi) integer-position bounds per fold, matching np.array_split."""
    return [(p[0], p[-1]) for p in np.array_split(np.arange(len(frame)), n_splits)]


# --------------------------------------------------------------------------- #
# Fold partitioning
# --------------------------------------------------------------------------- #

def test_walk_forward_produces_n_folds():
    res = walkforward.walk_forward(_frame(), [CORTEX_RULE], n_splits=4)
    assert res.n_folds == 4
    assert len(res.folds) == 4
    assert [f.index for f in res.folds] == [0, 1, 2, 3]


def test_folds_are_contiguous_and_cover_full_index():
    frame = _frame()
    res = walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=4)
    bounds = _expected_fold_bounds(frame, 4)
    assert res.folds[0].start == frame.index[0]
    assert res.folds[-1].end == frame.index[-1]
    for (lo, hi), fold in zip(bounds, res.folds, strict=True):
        assert fold.start == frame.index[lo]
        assert fold.end == frame.index[hi]
    # no gaps / overlaps: each fold's start is the bar after the previous fold's end
    for prev, nxt in zip(res.folds, res.folds[1:], strict=False):
        prev_pos = frame.index.get_loc(prev.end)
        nxt_pos = frame.index.get_loc(nxt.start)
        assert nxt_pos == prev_pos + 1


# --------------------------------------------------------------------------- #
# Faithful passthrough — per-fold returns equal direct-backtest slices
# --------------------------------------------------------------------------- #

def test_fold_cortex_return_matches_direct_backtest_slice():
    frame = _frame()
    res = walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=4)
    equity = engine.run_backtest(frame, [CORTEX_RULE]).equity_curve
    for (lo, hi), fold in zip(_expected_fold_bounds(frame, 4), res.folds, strict=True):
        expected = equity.iloc[hi] / equity.iloc[lo] - 1.0
        assert fold.cortex_return == pytest.approx(expected)


def test_fold_benchmark_return_matches_close_slice():
    frame = _frame()
    res = walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=4)
    close = frame["close"]
    for (lo, hi), fold in zip(_expected_fold_bounds(frame, 4), res.folds, strict=True):
        expected = close.iloc[hi] / close.iloc[lo] - 1.0
        assert fold.benchmark_return == pytest.approx(expected)


def test_fold_edge_is_cortex_minus_benchmark():
    res = walkforward.walk_forward(_frame(), [CORTEX_RULE], n_splits=4)
    for f in res.folds:
        assert f.edge == pytest.approx(f.cortex_return - f.benchmark_return)


def test_n_trades_partition_full_trade_count():
    frame = _frame()
    res = walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=4)
    bt = engine.run_backtest(frame, [CORTEX_RULE])
    # every closed trade's exit falls in exactly one fold
    assert sum(f.n_trades for f in res.folds) == len(bt.trades)


# --------------------------------------------------------------------------- #
# Aggregates
# --------------------------------------------------------------------------- #

def test_aggregates_match_per_fold_values():
    res = walkforward.walk_forward(_frame(), [CORTEX_RULE], n_splits=4)
    edges = [f.edge for f in res.folds]
    crets = [f.cortex_return for f in res.folds]
    brets = [f.benchmark_return for f in res.folds]
    assert res.mean_edge == pytest.approx(sum(edges) / len(edges))
    assert res.mean_cortex_return == pytest.approx(sum(crets) / len(crets))
    assert res.mean_benchmark_return == pytest.approx(sum(brets) / len(brets))
    assert res.cortex_win_rate == pytest.approx(
        sum(1 for e in edges if e > 0) / len(edges)
    )


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

def test_n_splits_one_equals_whole_period():
    frame = _frame()
    res = walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=1)
    assert res.n_folds == 1
    equity = engine.run_backtest(frame, [CORTEX_RULE]).equity_curve
    whole = equity.iloc[-1] / equity.iloc[0] - 1.0
    assert res.folds[0].cortex_return == pytest.approx(whole)
    assert res.folds[0].start == frame.index[0]
    assert res.folds[0].end == frame.index[-1]


def test_invalid_n_splits_raises():
    frame = _frame()
    with pytest.raises(ValueError):
        walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=0)
    with pytest.raises(ValueError):
        walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=len(frame) + 1)


def test_handles_unsorted_and_duplicate_timestamps():
    # The leaf must normalise the frame the SAME way the engine does (sort + drop
    # duplicate timestamps keep="last") so equity.iloc and close.iloc reference the
    # same bars. A reversed frame must yield identical folds to the canonical one,
    # and a duplicate timestamp must not raise (regression: code-review MAJOR).
    frame = _frame(120)
    canonical = walkforward.walk_forward(frame, [CORTEX_RULE], n_splits=4)
    reversed_res = walkforward.walk_forward(frame.iloc[::-1], [CORTEX_RULE], n_splits=4)
    for a, b in zip(canonical.folds, reversed_res.folds, strict=True):
        assert a.start == b.start and a.end == b.end
        assert a.cortex_return == pytest.approx(b.cortex_return)
        assert a.benchmark_return == pytest.approx(b.benchmark_return)
    # a duplicated trailing timestamp is collapsed (keep last) — no IndexError
    dup = pd.concat([frame, frame.iloc[[-1]]])
    res = walkforward.walk_forward(dup, [CORTEX_RULE], n_splits=4)
    assert res.n_folds == 4
    assert res.folds[-1].end == frame.index[-1]


# --------------------------------------------------------------------------- #
# Honesty / leaf constraints
# --------------------------------------------------------------------------- #

def test_walkforward_is_pure_leaf():
    # AC: imports only backtest.engine (+ pandas/numpy/dataclasses). Must NOT reach
    # into cli/db/dashboard/arena/portfolio/agent.
    src = pathlib.Path(walkforward.__file__).read_text()
    forbidden = [
        "from domdhi_crypto.cli",
        "from domdhi_crypto.report",
        "from domdhi_crypto.shared",
        "from domdhi_crypto.portfolio",
        "from domdhi_crypto.agent",
        "import arena",
    ]
    for token in forbidden:
        assert token not in src, f"walkforward must not import: {token}"
