"""Tests for the factor substrate (factors.py).

E12-S1 (this file, first batch): the primitive registry. Each primitive is pinned
against an *independently coded* reference (not imported from factors.py) so a
regression in the implementation is caught, mirroring the discipline in
``test_ta.py``. Plus the metadata contract and the ADR-001 no-``pandas-ta`` guard.
"""
import ast
import sys

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.signals import factors

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _series():
    # Deterministic, non-monotonic, strictly positive (safe for LOG/log-return).
    vals = np.cumsum(np.sin(np.arange(120) / 5.0) + np.cos(np.arange(120) / 3.0)) + 100
    return pd.Series(vals)


def _call(name, *args):
    return factors.FUNCTION_REGISTRY[name].fn(*args)


# --------------------------------------------------------------------------- #
# Registry / metadata contract  (AC: per-function metadata exposed)
# --------------------------------------------------------------------------- #

def test_registry_is_populated_with_expected_categories():
    cats = {f.category for f in factors.FUNCTION_REGISTRY.values()}
    assert {
        "moving_average", "momentum", "trend", "volatility",
        "volume", "timeseries", "cross_section", "math",
    } <= cats


def test_every_entry_has_complete_metadata():
    for name, f in factors.FUNCTION_REGISTRY.items():
        assert f.name == name
        assert callable(f.fn)
        assert f.signature and name in f.signature
        assert f.description.strip()
        assert f.example.strip()
        assert f.category.strip()


def test_required_timeseries_and_crosssection_primitives_present():
    required = {
        "DELAY", "TS_SUM", "TS_MEAN", "TS_STD", "TS_MAX", "TS_MIN", "TS_RANK",
        "TS_CORR", "TS_ARGMAX", "TS_ARGMIN", "DECAYLINEAR", "LOG_RETURN",
        "RANK", "ZSCORE", "NORMALIZE",
    }
    assert required <= set(factors.FUNCTION_REGISTRY)


# --------------------------------------------------------------------------- #
# Moving averages / momentum  (reuse ta.py — confirm wrappers match)
# --------------------------------------------------------------------------- #

def test_sma_matches_rolling_mean():
    s = _series()
    assert np.allclose(_call("SMA", s, 20).to_numpy(),
                       s.rolling(20).mean().to_numpy(), equal_nan=True)


def test_ema_matches_independent_recurrence():
    s = _series()
    alpha = 2 / (10 + 1)
    out, prev = [], None
    for v in s:
        prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out.append(prev)
    assert np.max(np.abs(_call("EMA", s, 10).to_numpy() - np.array(out))) < 1e-9


def test_roc_and_mom_against_reference():
    s = _series()
    assert np.allclose(_call("ROC", s, 5).to_numpy(),
                       ((s / s.shift(5) - 1) * 100).to_numpy(), equal_nan=True)
    assert np.allclose(_call("MOM", s, 5).to_numpy(),
                       (s - s.shift(5)).to_numpy(), equal_nan=True)


def test_macd_components_match_ta():
    from domdhi_crypto.signals import ta
    s = _series()
    line, sig, hist = ta.macd(s)
    assert np.allclose(_call("MACD", s).to_numpy(), line.to_numpy(), equal_nan=True)
    assert np.allclose(_call("MACD_SIGNAL", s).to_numpy(), sig.to_numpy(), equal_nan=True)
    assert np.allclose(_call("MACD_HIST", s).to_numpy(), hist.to_numpy(), equal_nan=True)


# --------------------------------------------------------------------------- #
# Time-series operators
# --------------------------------------------------------------------------- #

def test_delay_shifts():
    s = _series()
    out = _call("DELAY", s, 3)
    assert out.iloc[10] == s.iloc[7]
    assert out.iloc[:3].isna().all()


def test_ts_aggregates_match_rolling():
    s = _series()
    assert np.allclose(_call("TS_SUM", s, 7).to_numpy(), s.rolling(7).sum().to_numpy(), equal_nan=True)
    assert np.allclose(_call("TS_MEAN", s, 7).to_numpy(), s.rolling(7).mean().to_numpy(), equal_nan=True)
    assert np.allclose(_call("TS_STD", s, 7).to_numpy(), s.rolling(7).std().to_numpy(), equal_nan=True)
    assert np.allclose(_call("TS_MAX", s, 7).to_numpy(), s.rolling(7).max().to_numpy(), equal_nan=True)
    assert np.allclose(_call("TS_MIN", s, 7).to_numpy(), s.rolling(7).min().to_numpy(), equal_nan=True)


def test_ts_rank_bounds_and_extremes():
    # Strictly increasing window -> the latest value is the max -> rank 1.0.
    up = pd.Series(np.arange(50, dtype=float))
    r = _call("TS_RANK", up, 10)
    assert np.nanmax(r.to_numpy()) == pytest.approx(1.0)
    assert (r.dropna() >= 0).all() and (r.dropna() <= 1).all()
    # Strictly decreasing -> latest value is the min -> rank 0.0.
    down = pd.Series(np.arange(50, 0, -1, dtype=float))
    assert _call("TS_RANK", down, 10).dropna().iloc[-1] == pytest.approx(0.0)


def test_ts_argmax_argmin_positions():
    # Window of 5; build a series where the max/min positions are known.
    s = pd.Series([1.0, 5.0, 2.0, 3.0, 4.0, 0.0, 9.0])
    # Last window [2,3,4,0,9] -> argmax at offset 4, argmin at offset 3.
    assert _call("TS_ARGMAX", s, 5).iloc[-1] == 4
    assert _call("TS_ARGMIN", s, 5).iloc[-1] == 3


def test_decaylinear_weights_recent_most():
    # A step series: the weighted mean must sit above the simple mean because the
    # later (higher) values carry more weight.
    s = pd.Series([1.0, 1.0, 1.0, 10.0, 10.0])
    dl = _call("DECAYLINEAR", s, 5).iloc[-1]
    assert dl == pytest.approx((1 * 1 + 1 * 2 + 1 * 3 + 10 * 4 + 10 * 5) / 15)
    assert dl > s.tail(5).mean()


def test_log_return_against_reference():
    s = _series()
    assert np.allclose(_call("LOG_RETURN", s, 1).to_numpy(),
                       np.log(s / s.shift(1)).to_numpy(), equal_nan=True)


def test_ts_corr_perfect_when_linear():
    s = pd.Series(np.arange(1, 40, dtype=float))
    y = 2 * s + 3
    assert _call("TS_CORR", s, y, 10).dropna().iloc[-1] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Cross-section proxies
# --------------------------------------------------------------------------- #

def test_rank_is_full_series_percentile():
    s = pd.Series([10.0, 30.0, 20.0, 40.0])
    assert np.allclose(_call("RANK", s).to_numpy(), [0.25, 0.75, 0.5, 1.0])


def test_zscore_is_rolling_standardized():
    s = _series()
    m, sd = s.rolling(20).mean(), s.rolling(20).std()
    assert np.allclose(_call("ZSCORE", s, 20).to_numpy(),
                       ((s - m) / sd).to_numpy(), equal_nan=True)


def test_normalize_in_unit_range():
    s = _series()
    n = _call("NORMALIZE", s, 20).dropna()
    assert (n >= 0).all() and (n <= 1).all()


# --------------------------------------------------------------------------- #
# Volume / volatility / trend
# --------------------------------------------------------------------------- #

def test_obv_accumulates_by_direction():
    close = pd.Series([10.0, 11.0, 10.5, 12.0])
    vol = pd.Series([100.0, 200.0, 150.0, 300.0])
    # diff signs: [nan->0, +, -, +] -> obv = [0, 200, 50, 350]
    assert np.allclose(_call("OBV", close, vol).to_numpy(), [0, 200, 50, 350])


def test_stddev_matches_rolling():
    s = _series()
    assert np.allclose(_call("STDDEV", s, 14).to_numpy(),
                       s.rolling(14).std().to_numpy(), equal_nan=True)


def test_linearreg_slope_recovers_known_slope():
    # A line of slope 2 -> rolling slope is 2 everywhere it is defined.
    s = pd.Series(2.0 * np.arange(40) + 5.0)
    assert _call("LINEARREG_SLOPE", s, 10).dropna().iloc[-1] == pytest.approx(2.0)


def test_atr_requires_ohlc_and_matches_ta():
    from domdhi_crypto.signals import ta
    n = 40
    high = pd.Series(np.linspace(10, 20, n) + 1)
    low = pd.Series(np.linspace(10, 20, n) - 1)
    close = pd.Series(np.linspace(10, 20, n))
    frame = pd.DataFrame({"high": high, "low": low, "close": close})
    assert np.allclose(_call("ATR", high, low, close, 14).to_numpy(),
                       ta.atr(frame, 14).to_numpy(), equal_nan=True)


# --------------------------------------------------------------------------- #
# Math primitives
# --------------------------------------------------------------------------- #

def test_math_primitives():
    s = pd.Series([-2.0, 0.0, 3.0])
    assert np.allclose(_call("ABS", s).to_numpy(), [2, 0, 3])
    assert np.allclose(_call("SIGN", s).to_numpy(), [-1, 0, 1])
    assert np.allclose(_call("POW", pd.Series([2.0, 3.0]), 2).to_numpy(), [4, 9])
    assert np.allclose(_call("MAX", pd.Series([1.0, 5.0]), pd.Series([3.0, 2.0])).to_numpy(), [3, 5])
    assert np.allclose(_call("MIN", pd.Series([1.0, 5.0]), pd.Series([3.0, 2.0])).to_numpy(), [1, 2])


# --------------------------------------------------------------------------- #
# ADR-001 guard: pure numpy/pandas, no pandas-ta, no asteval
# --------------------------------------------------------------------------- #

def test_no_pandas_ta_imported():
    # Importing factors must not pull pandas-ta into the process.
    assert "pandas_ta" not in sys.modules


def test_factors_source_has_no_forbidden_imports():
    # Static guard: the module's import graph names neither dependency anywhere.
    import inspect

    tree = ast.parse(inspect.getsource(factors))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "pandas_ta" not in imported
    assert "asteval" not in imported
    # Leaf module: only numpy, pandas, and stdlib (the sibling ``ta`` is a
    # relative import — module=None — so it does not appear in this set).
    assert imported <= {"numpy", "pandas", "dataclasses", "collections", "ast", "operator"}


# =========================================================================== #
# E12-S2 — safe declarative factor expression evaluator
# =========================================================================== #

def _ohlcv_frame(n=260):
    """Mimic the shape of db.load_close_series: daily index, close + volume only."""
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    close = pd.Series(
        np.cumsum(np.sin(np.arange(n) / 5.0) + np.cos(np.arange(n) / 3.0)) + 100,
        index=idx,
    )
    volume = pd.Series(np.abs(np.sin(np.arange(n) / 4.0)) * 1000 + 50, index=idx)
    return pd.DataFrame({"close": close, "volume": volume}, index=idx)


def _full_ohlcv_frame(n=300):
    """Mimic db.load_ohlcv_daily: full open/high/low/close/volume daily frame, so
    the high/low factors (ATR/WILLR/CCI/AROON/ADX) are reachable."""
    base = _ohlcv_frame(n)
    close = base["close"]
    spread = np.abs(np.cos(np.arange(n) / 2.0)) + 0.5
    return pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": base["volume"],
        },
        index=base.index,
    )


# ---- valid expressions evaluate correctly ----

def test_evaluate_arithmetic_with_function_call():
    frame = _ohlcv_frame()
    out = factors.evaluate("(close - EMA(close, 200)) / close", frame)
    # Compute the expected value directly via the registry to avoid duplicating math.
    ema = factors.FUNCTION_REGISTRY["EMA"].fn(frame["close"], 200)
    expected = (frame["close"] - ema) / frame["close"]
    assert np.allclose(out.to_numpy(), expected.to_numpy(), equal_nan=True)


def test_evaluate_bare_column_returns_series():
    frame = _ohlcv_frame()
    out = factors.evaluate("volume", frame)
    assert np.allclose(out.to_numpy(), frame["volume"].to_numpy(), equal_nan=True)


def test_evaluate_partial_window_is_nan_not_fabricated():
    frame = _ohlcv_frame()
    out = factors.evaluate("SMA(close, 20)", frame)
    # First 19 points cannot fill a 20-window -> NaN, never invented.
    assert out.iloc[:19].isna().all()
    assert not np.isnan(out.iloc[19])


def test_evaluate_comparison_returns_boolean_series():
    frame = _ohlcv_frame()
    out = factors.evaluate("close > SMA(close, 50)", frame)
    assert out.dtype == bool
    assert out.shape[0] == frame.shape[0]


def test_evaluate_nested_calls_and_negation():
    frame = _ohlcv_frame()
    out = factors.evaluate("-ZSCORE(TS_MEAN(close, 5), 20)", frame)
    inner = factors.FUNCTION_REGISTRY["TS_MEAN"].fn(frame["close"], 5)
    expected = -factors.FUNCTION_REGISTRY["ZSCORE"].fn(inner, 20)
    assert np.allclose(out.to_numpy(), expected.to_numpy(), equal_nan=True)


def test_evaluate_operates_on_db_shaped_close_volume_frame():
    # AC: the evaluator's frame is the close+volume frame from db.load_close_series.
    frame = _ohlcv_frame()
    assert list(frame.columns) == ["close", "volume"]
    out = factors.evaluate("OBV(close, volume)", frame)
    assert out.shape[0] == frame.shape[0]


# ---- high/low factors are deferred, not faked (data-shape gotcha) ----

def test_high_low_factor_raises_rather_than_fabricating():
    # ATR needs high/low; the close+volume frame has neither, so it must error
    # loudly instead of silently producing wrong values.
    frame = _ohlcv_frame()
    with pytest.raises(ValueError, match="unknown column"):
        factors.evaluate("ATR(high, low, close, 14)", frame)


# ---- security: malicious / disallowed expressions are rejected ----

@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo pwned')",   # import + arbitrary call
    "open('/etc/passwd')",                       # non-registry call
    "exec('x=1')",                               # exec
    "eval('1+1')",                               # eval
    "close.__class__",                           # dunder attribute access
    "().__class__.__bases__",                    # sandbox-escape chain
    "close.values",                              # attribute access
    "close.rolling(5).mean()",                   # method chaining via attributes
    "close[0]",                                  # subscript
    "lambda: 1",                                 # lambda
    "[x for x in close]",                        # comprehension
    "{1: 2}",                                    # dict literal
    "(1, 2)",                                    # tuple literal
    "1 if close else 2",                         # conditional expression
    "close & close",                             # bitwise operator
    "'a string'",                                # string literal
    "True",                                      # boolean literal
    "RSI(close, period=14)",                     # keyword args disallowed
    "nonexistent_column",                        # unknown name
    "BOGUS_FUNC(close)",                         # unknown function
    "import os",                                 # statement, not an expression
])
def test_evaluate_rejects_malicious_or_invalid(expr):
    frame = _ohlcv_frame()
    with pytest.raises(ValueError):
        factors.evaluate(expr, frame)


def test_evaluate_rejects_before_evaluating(tmp_path):
    # Prove rejection happens BEFORE any evaluation: a string that *would* create a
    # file if executed must raise, and the file must not exist afterwards. (open()
    # is not a registry function, so this can never reach execution — this test
    # pins that the guard fires first, observably, not via a hollow sentinel.)
    target = tmp_path / "should_not_exist.txt"
    with pytest.raises(ValueError):
        factors.evaluate(f"open({str(target)!r}, 'w')", frame=_ohlcv_frame())
    assert not target.exists()


# ---- resource-exhaustion (DoS) guards: must raise/return fast, never hang ----

def test_evaluate_rejects_deeply_nested_expression():
    # A long unary chain would overflow the recursive walk's stack; the node cap
    # must turn that into a ValueError, never a RecursionError.
    expr = "-" * 400 + "close"  # 400 > _MAX_NODES (256); parses fine, walk would not
    with pytest.raises(ValueError):
        factors.evaluate(expr, _ohlcv_frame())


def test_evaluate_integer_power_does_not_explode_to_bignum():
    # 9 ** 9 ** 9 as Python ints is a ~370M-digit number that hangs the process.
    # Float coercion makes it overflow *instantly* (no bignum); the resulting
    # float OverflowError is normalized to ValueError. Either way: fast, bounded.
    with pytest.raises(ValueError):
        factors.evaluate("9 ** 9 ** 9", _ohlcv_frame())


def test_evaluate_scalar_only_expression_returns_scalar():
    # Documented degenerate case: an expression with no column is a plain scalar.
    assert factors.evaluate("1 + 1", _ohlcv_frame()) == 2.0
    assert factors.evaluate("2 > 1", _ohlcv_frame()) is True


# =========================================================================== #
# E12-S3 — built-in factor library
# =========================================================================== #

def test_at_least_40_builtin_factors_loaded_as_data():
    assert len(factors.BUILTIN_FACTORS) >= 40
    # Every entry is data with the full schema — not Python per factor.
    for f in factors.BUILTIN_FACTORS:
        assert set(f) == {"name", "expression", "description", "category"}
        assert all(isinstance(f[k], str) and f[k].strip() for k in f)


def test_builtin_factor_names_are_unique():
    names = [f["name"] for f in factors.BUILTIN_FACTORS]
    assert len(names) == len(set(names))


def test_builtin_factors_span_multiple_categories():
    cats = {f["category"] for f in factors.BUILTIN_FACTORS}
    assert {"trend", "momentum", "volatility", "volume", "statistical"} <= cats


@pytest.mark.parametrize("factor", factors.BUILTIN_FACTORS, ids=lambda f: f["name"])
def test_every_builtin_evaluates_without_error(factor):
    # Each builtin must evaluate on a populated full-OHLCV frame and return a
    # full-length result (or a scalar). No exceptions; partial windows -> NaN.
    # The full frame (not close-only) so the high/low factors are reachable too.
    frame = _full_ohlcv_frame(n=300)
    out = factors.evaluate(factor["expression"], frame)
    if isinstance(out, pd.Series):
        assert out.shape[0] == frame.shape[0]
    else:
        assert np.isscalar(out)


def test_previously_deferred_ohlcv_factors_are_now_live():
    # The five high/low factors were unblocked once db.load_ohlcv_daily + the
    # WILLR/CCI/AROON_OSC/ADX primitives landed. DEFERRED is now empty and each is
    # present in BUILTIN_FACTORS as a real expression.
    assert factors.DEFERRED_FACTORS == []
    names = {f["name"] for f in factors.BUILTIN_FACTORS}
    assert {"atr_ratio_14", "williams_r_14", "cci_20", "aroon_25", "adx_14"} <= names


def test_ohlcv_factors_evaluate_on_full_frame_but_nan_on_close_only():
    # On a full OHLCV frame they produce real (non-all-NaN) values; on the
    # close+volume frame they raise unknown-column — caught upstream as NaN.
    full = _full_ohlcv_frame(n=300)
    close_only = _ohlcv_frame(n=300)
    for name in ("atr_ratio_14", "williams_r_14", "cci_20", "aroon_25", "adx_14"):
        expr = next(f["expression"] for f in factors.BUILTIN_FACTORS if f["name"] == name)
        out = factors.evaluate(expr, full)
        assert out.notna().any(), f"{name} produced all-NaN on a full OHLCV frame"
        with pytest.raises(ValueError, match="unknown column"):
            factors.evaluate(expr, close_only)


def test_a_high_low_factor_would_indeed_fail_on_close_volume_frame():
    # Sanity that the deferral is real, not cosmetic: a high/low expression that a
    # deferred factor would use raises on the close+volume frame.
    frame = _ohlcv_frame()
    with pytest.raises(ValueError, match="unknown column"):
        factors.evaluate("(close - TS_MIN(low, 14)) / (TS_MAX(high, 14) - TS_MIN(low, 14))", frame)
