"""Tests for the IC/ICIR factor-effectiveness module (effectiveness.py).

The load-bearing invariant is the forward-return alignment: IC is the Spearman
rank correlation between a factor value at time ``t`` and the ``n``-period
*forward* return, and the last ``n`` rows of that forward return must be NaN and
never filled. Reference IC values are computed independently here (numpy
``corrcoef`` over ranks, a different code path than the implementation's
``.rank(pct=True).corr()``) so an alignment or shift regression is caught.

The look-ahead sanity guard is deterministic (fixed seed 42): a pure-noise factor
must score ~0 and a perfectly future-aligned factor must score ~1.
"""
import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.signals import effectiveness

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _close(n=260):
    """Deterministic, non-monotonic, strictly positive daily close series."""
    vals = np.cumsum(np.sin(np.arange(n) / 5.0) + np.cos(np.arange(n) / 3.0)) + 100
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.Series(vals, index=idx)


def _independent_spearman(a, b):
    """Spearman via numpy corrcoef on ranks — independent of the implementation."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


# --------------------------------------------------------------------------- #
# IC — reference value + forward-return alignment
# --------------------------------------------------------------------------- #

def test_ic_matches_independent_spearman_reference():
    close = _close(150)
    factor = pd.Series(
        np.random.default_rng(7).standard_normal(len(close)), index=close.index
    )
    fwd = close.pct_change(5).shift(-5)
    aligned = pd.DataFrame({"f": factor, "r": fwd}).dropna()
    ref = _independent_spearman(aligned["f"], aligned["r"])

    ic = effectiveness.information_coefficient(factor, close, horizon=5)
    assert ic == pytest.approx(ref, abs=1e-6)


def test_ic_noise_factor_is_near_zero():
    """Deterministic guard: pure noise (seed 42) must not predict the future."""
    close = _close(260)
    noise = pd.Series(
        np.random.default_rng(42).standard_normal(len(close)), index=close.index
    )
    ic = effectiveness.information_coefficient(noise, close, horizon=5)
    assert abs(ic) < 0.1


def test_ic_future_aligned_factor_is_near_one():
    """A factor that IS the forward return must score IC ~ 1 (alignment proof)."""
    close = _close(260)
    fwd = close.pct_change(5).shift(-5)  # the forward return, used as the factor
    ic = effectiveness.information_coefficient(fwd, close, horizon=5)
    assert ic > 0.99


def test_ic_does_not_fill_the_forward_return_nan_tail():
    """The last `horizon` rows have no forward return; IC must EXCLUDE them
    (dropna), never fill them. Proven two ways: (a) IC equals the reference
    computed over the dropna overlap, and (b) IC does NOT equal the counterfactual
    where the NaN tail is zero-filled — and the two genuinely differ, so a buggy
    fill-the-tail impl would fail (a) and coincide with (b)."""
    close = _close(80)
    horizon = 5
    factor = close.pct_change(3)  # defined everywhere except a 3-row head warmup
    fwd = close.pct_change(horizon).shift(-horizon)  # NaN only in the last `horizon` rows

    # (a) reference over the dropna overlap (tail excluded) — what a correct impl does
    aligned = pd.DataFrame({"f": factor, "r": fwd}).dropna()
    ref_dropna = _independent_spearman(aligned["f"], aligned["r"])

    # (b) counterfactual: zero-fill the NaN tail instead of dropping it
    filled = pd.DataFrame({"f": factor, "r": fwd.fillna(0.0)}).dropna()
    ref_filled = _independent_spearman(filled["f"], filled["r"])

    # the two approaches must genuinely diverge, else the test proves nothing
    assert abs(ref_dropna - ref_filled) > 1e-6

    ic = effectiveness.information_coefficient(factor, close, horizon=horizon)
    assert ic == pytest.approx(ref_dropna, abs=1e-6)      # impl excludes the tail
    assert abs(ic - ref_filled) > 1e-6                     # impl did NOT fill the tail


# --------------------------------------------------------------------------- #
# ICIR
# --------------------------------------------------------------------------- #

def test_icir_is_nan_when_fewer_than_two_ic_points():
    """min_periods=2 exception: ICIR is NaN until >= 2 defined rolling-IC points."""
    close = _close(30)
    factor = pd.Series(
        np.random.default_rng(1).standard_normal(len(close)), index=close.index
    )
    # window larger than the data -> at most one (or zero) defined IC point.
    val = effectiveness.icir(factor, close, horizon=5, window=40)
    assert np.isnan(val)


def test_icir_is_finite_with_enough_ic_points():
    close = _close(260)
    factor = pd.Series(
        np.random.default_rng(3).standard_normal(len(close)), index=close.index
    )
    val = effectiveness.icir(factor, close, horizon=5, window=20)
    assert not np.isnan(val)


def test_rolling_ic_has_nan_partial_window_head():
    close = _close(120)
    factor = pd.Series(
        np.random.default_rng(5).standard_normal(len(close)), index=close.index
    )
    ric = effectiveness.rolling_ic(factor, close, horizon=5, window=20)
    # The first defined IC needs a full window of aligned (factor, fwd) points,
    # so the head of the series is NaN (partial windows never fabricated).
    assert ric.iloc[:5].isna().all()


# --------------------------------------------------------------------------- #
# score_factors — ranking + graceful failure
# --------------------------------------------------------------------------- #

def _frame(n=200):
    close = _close(n)
    volume = pd.Series(
        np.abs(np.random.default_rng(11).standard_normal(n)) * 1000 + 100,
        index=close.index,
    )
    return pd.DataFrame({"close": close, "volume": volume})


def test_score_factors_ranks_by_icir_descending():
    frame = _frame()
    factors = [
        {"name": "roc_10", "expression": "ROC(close, 10)", "category": "momentum"},
        {"name": "rsi_14", "expression": "RSI(close, 14)", "category": "momentum"},
        {"name": "zscore_20", "expression": "ZSCORE(close, 20)", "category": "stat"},
    ]
    scored = effectiveness.score_factors(frame, factors, horizon=5, window=20)
    names = {row["name"] for row in scored}
    assert {"roc_10", "rsi_14", "zscore_20"} <= names
    # ranked by icir descending (NaN icir sorts last, not crashing the sort)
    icirs = [row["icir"] for row in scored if not np.isnan(row["icir"])]
    assert icirs == sorted(icirs, reverse=True)


def test_score_factors_reports_nan_on_evaluation_error_without_crashing():
    frame = _frame()
    factors = [
        {"name": "good", "expression": "ROC(close, 10)", "category": "momentum"},
        # references a column the close+volume frame does not have -> evaluate raises
        {"name": "needs_high", "expression": "high - close", "category": "broken"},
    ]
    scored = effectiveness.score_factors(frame, factors, horizon=5, window=20)
    by_name = {row["name"]: row for row in scored}
    assert "needs_high" in by_name
    assert np.isnan(by_name["needs_high"]["ic"])
    assert np.isnan(by_name["needs_high"]["icir"])
