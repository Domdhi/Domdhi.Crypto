"""Declarative factor substrate: a pure-numpy/pandas primitive registry plus a
safe expression evaluator and a built-in factor library expressed as data.

This is the cortex spine. Three layers build up here, in dependency order:

1. ``FUNCTION_REGISTRY`` (E12-S1) — every primitive a factor expression may call,
   keyed by an UPPERCASE name, each carrying metadata (signature/description/
   example/category). This is the agent's *factor menu*.
2. ``evaluate(expr, frame)`` (E12-S2) — a restricted ``ast`` walk that evaluates a
   factor *string* over an OHLCV-style frame, calling only registry functions.
3. ``BUILTIN_FACTORS`` (E12-S3) — ≥40 ready-made factors as data, re-homed onto
   the primitives above.

ADR-001 governs the whole module: **pure numpy/pandas only** — no ``pandas-ta``
(it breaks on numpy 2.x / Python 3.13) and no ``asteval`` (the evaluator uses the
stdlib ``ast`` module). Keeping the math hand-rolled and the evaluator dependency
-free is the auditability that distinguishes this from off-the-shelf factor zoos.

The module is a deliberate *leaf*: it imports numpy, pandas, and ``ta`` only — no
other internal modules — so the dependency graph stays acyclic.

Data-shape note (load-bearing): two frame sources feed the evaluator. The
``close`` + ``volume`` frame from ``db.load_close_series`` evaluates the bulk of
the library; the full ``open/high/low/close/volume`` frame from
``db.load_ohlcv_daily`` (which resamples the candle ``ohlc`` table to daily bars)
additionally unlocks the high/low primitives (``ATR``, ``WILLR``, ``CCI``,
``AROON_OSC``, ``ADX``). Against a close-only frame those high/low factors raise
"unknown column", which ``score_factors`` and the backtest engine catch per-factor
and surface as NaN — so they degrade gracefully rather than crash.
"""
import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import ta


@dataclass(frozen=True)
class FactorFunction:
    """A registered primitive plus the metadata that makes it discoverable.

    ``fn`` is the callable invoked by the evaluator; the rest is the menu entry an
    agent (or human) reads to know what the primitive does and how to call it.
    """

    name: str
    fn: Callable
    signature: str
    description: str
    example: str
    category: str


FUNCTION_REGISTRY: dict[str, FactorFunction] = {}


def _reg(name, fn, signature, description, example, category):
    """Register ``fn`` under ``name`` with metadata and return it unchanged."""
    FUNCTION_REGISTRY[name] = FactorFunction(
        name=name,
        fn=fn,
        signature=signature,
        description=description,
        example=example,
        category=category,
    )
    return fn


# --------------------------------------------------------------------------- #
# Moving averages  (wrap ta.py — do not duplicate)
# --------------------------------------------------------------------------- #

def _sma(x, window):
    return ta.sma(x, int(window))


def _ema(x, span):
    return ta.ema(x, int(span))


# --------------------------------------------------------------------------- #
# Momentum  (wrap ta.py where it already implements the indicator)
# --------------------------------------------------------------------------- #

def _rsi(x, period=14):
    return ta.rsi(x, int(period))


def _macd_line(close, fast=12, slow=26, signal=9):
    line, _, _ = ta.macd(close, int(fast), int(slow), int(signal))
    return line


def _macd_signal(close, fast=12, slow=26, signal=9):
    _, sig, _ = ta.macd(close, int(fast), int(slow), int(signal))
    return sig


def _macd_hist(close, fast=12, slow=26, signal=9):
    _, _, hist = ta.macd(close, int(fast), int(slow), int(signal))
    return hist


def _roc(x, window):
    """Rate of change over ``window`` periods, in percent."""
    return x.pct_change(int(window)) * 100


def _mom(x, window):
    """Momentum: difference vs. ``window`` periods ago."""
    return x - x.shift(int(window))


# --------------------------------------------------------------------------- #
# Trend
# --------------------------------------------------------------------------- #

def _linearreg_slope(x, window):
    """Rolling least-squares slope of ``x`` against a unit time index."""
    window = int(window)
    idx = np.arange(window, dtype=float)
    idx_dev = idx - idx.mean()
    denom = float((idx_dev ** 2).sum())

    def _slope(w):
        return float((idx_dev * (w - w.mean())).sum() / denom)

    return x.rolling(window).apply(_slope, raw=True)


# --------------------------------------------------------------------------- #
# Volatility  (wrap ta.py)
# --------------------------------------------------------------------------- #

def _stddev(x, window):
    return x.rolling(int(window)).std()


def _bbands_pctb(close, period=20, mult=2):
    _, _, _, pctb = ta.bollinger(close, int(period), mult)
    return pctb


def _atr(high, low, close, period=14):
    """Average True Range. Needs high/low — reachable only from an OHLCV frame
    (``db.load_ohlcv_daily``), not the close+volume ``load_close_series`` frame."""
    frame = pd.DataFrame({"high": high, "low": low, "close": close})
    return ta.atr(frame, int(period))


def _williams_r(high, low, close, period=14):
    """Williams %R. Needs high/low (OHLCV frame)."""
    frame = pd.DataFrame({"high": high, "low": low, "close": close})
    return ta.williams_r(frame, int(period))


def _cci(high, low, close, period=20):
    """Commodity Channel Index. Needs high/low (OHLCV frame)."""
    frame = pd.DataFrame({"high": high, "low": low, "close": close})
    return ta.cci(frame, int(period))


def _aroon_osc(high, low, period=25):
    """Aroon Oscillator (Aroon Up - Aroon Down). Needs high/low (OHLCV frame)."""
    frame = pd.DataFrame({"high": high, "low": low})
    return ta.aroon_osc(frame, int(period))


def _adx(high, low, close, period=14):
    """Average Directional Index (trend strength). Needs high/low (OHLCV frame)."""
    frame = pd.DataFrame({"high": high, "low": low, "close": close})
    return ta.adx(frame, int(period))


def _annualized_vol(close, periods_per_year=365):
    """Scalar: stdev of daily returns scaled by sqrt(periods_per_year)."""
    return ta.annualized_vol(close, int(periods_per_year))


# --------------------------------------------------------------------------- #
# Volume
# --------------------------------------------------------------------------- #

def _obv(close, volume):
    """On-Balance Volume: signed cumulative volume by close direction."""
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume.fillna(0.0)).cumsum()


# --------------------------------------------------------------------------- #
# Time-series operators
# --------------------------------------------------------------------------- #

def _delay(x, n):
    return x.shift(int(n))


def _ts_sum(x, window):
    return x.rolling(int(window)).sum()


def _ts_mean(x, window):
    return x.rolling(int(window)).mean()


def _ts_std(x, window):
    return x.rolling(int(window)).std()


def _ts_max(x, window):
    return x.rolling(int(window)).max()


def _ts_min(x, window):
    return x.rolling(int(window)).min()


def _ts_rank(x, window):
    """Rolling percentile rank in [0, 1] of the most recent value within window."""
    window = int(window)

    def _last_rank(w):
        # argsort().argsort() gives 0-based ranks; take the last point's rank.
        return float(w.argsort().argsort()[-1]) / (len(w) - 1) if len(w) > 1 else 0.0

    return x.rolling(window).apply(_last_rank, raw=True)


def _ts_corr(x, y, window):
    return x.rolling(int(window)).corr(y)


def _ts_argmax(x, window):
    """Offset (0=oldest) of the maximum within the trailing window."""
    return x.rolling(int(window)).apply(np.argmax, raw=True)


def _ts_argmin(x, window):
    """Offset (0=oldest) of the minimum within the trailing window."""
    return x.rolling(int(window)).apply(np.argmin, raw=True)


def _decaylinear(x, window):
    """Linearly-weighted rolling mean — most recent point gets the largest weight."""
    window = int(window)
    weights = np.arange(1, window + 1, dtype=float)
    weights /= weights.sum()

    def _wmean(w):
        return float(np.dot(w, weights))

    return x.rolling(window).apply(_wmean, raw=True)


def _log_return(x, n=1):
    return np.log(x / x.shift(int(n)))


def _diff(x, n=1):
    return x.diff(int(n))


def _pct_change(x, n=1):
    return x.pct_change(int(n))


# --------------------------------------------------------------------------- #
# Cross-section  (single-asset proxies — documented)
#
# True cross-section operates across many assets at one timestamp. With a single
# coin's series that is degenerate, so RANK is a full-series percentile and
# ZSCORE/NORMALIZE are *rolling* — the sensible single-asset analogue. This is a
# deliberate, documented reinterpretation, not an accident.
# --------------------------------------------------------------------------- #

def _rank(x):
    """Full-series percentile rank in [0, 1] (single-asset cross-section proxy)."""
    return x.rank(pct=True)


def _zscore(x, window):
    """Rolling z-score: (x - rolling_mean) / rolling_std over ``window``."""
    window = int(window)
    m = x.rolling(window).mean()
    s = x.rolling(window).std()
    return (x - m) / s


def _normalize(x, window):
    """Rolling min-max normalize to [0, 1] over ``window``."""
    window = int(window)
    lo = x.rolling(window).min()
    hi = x.rolling(window).max()
    return (x - lo) / (hi - lo)


# --------------------------------------------------------------------------- #
# Math  (work on Series or scalars alike)
# --------------------------------------------------------------------------- #

def _abs(x):
    return np.abs(x)


def _log(x):
    return np.log(x)


def _sign(x):
    return np.sign(x)


def _sqrt(x):
    return np.sqrt(x)


def _power(x, p):
    return x ** p


def _max(x, y):
    return np.maximum(x, y)


def _min(x, y):
    return np.minimum(x, y)


# --------------------------------------------------------------------------- #
# Registration  (this is the contract every later story + epic consumes)
# --------------------------------------------------------------------------- #

_reg("SMA", _sma, "SMA(x, window)",
     "Simple moving average.", "SMA(close, 20)", "moving_average")
_reg("EMA", _ema, "EMA(x, span)",
     "Exponential moving average (adjust=False).", "EMA(close, 200)", "moving_average")

_reg("RSI", _rsi, "RSI(x, period=14)",
     "Wilder's Relative Strength Index.", "RSI(close, 14)", "momentum")
_reg("MACD", _macd_line, "MACD(close, fast=12, slow=26, signal=9)",
     "MACD line (EMA fast - EMA slow).", "MACD(close)", "momentum")
_reg("MACD_SIGNAL", _macd_signal, "MACD_SIGNAL(close, fast=12, slow=26, signal=9)",
     "MACD signal line.", "MACD_SIGNAL(close)", "momentum")
_reg("MACD_HIST", _macd_hist, "MACD_HIST(close, fast=12, slow=26, signal=9)",
     "MACD histogram (line - signal).", "MACD_HIST(close)", "momentum")
_reg("ROC", _roc, "ROC(x, window)",
     "Rate of change over window, in percent.", "ROC(close, 10)", "momentum")
_reg("MOM", _mom, "MOM(x, window)",
     "Momentum: x minus x shifted by window.", "MOM(close, 10)", "momentum")

_reg("LINEARREG_SLOPE", _linearreg_slope, "LINEARREG_SLOPE(x, window)",
     "Rolling least-squares slope vs. time.", "LINEARREG_SLOPE(close, 20)", "trend")

_reg("STDDEV", _stddev, "STDDEV(x, window)",
     "Rolling standard deviation.", "STDDEV(close, 20)", "volatility")
_reg("BBANDS_PCTB", _bbands_pctb, "BBANDS_PCTB(close, period=20, mult=2)",
     "Bollinger %B (position within the bands).", "BBANDS_PCTB(close, 20, 2)", "volatility")
_reg("ATR", _atr, "ATR(high, low, close, period=14)",
     "Average True Range. Needs high/low (OHLCV frame).",
     "ATR(high, low, close, 14)", "volatility")
_reg("ANNUALIZED_VOL", _annualized_vol, "ANNUALIZED_VOL(close, periods_per_year=365)",
     "Scalar annualized volatility of daily returns.", "ANNUALIZED_VOL(close)", "volatility")
_reg("WILLR", _williams_r, "WILLR(high, low, close, period=14)",
     "Williams %R: close position in the high-low range, scaled to [-100, 0]. "
     "Needs high/low (OHLCV frame).", "WILLR(high, low, close, 14)", "momentum")
_reg("CCI", _cci, "CCI(high, low, close, period=20)",
     "Commodity Channel Index off typical price. Needs high/low (OHLCV frame).",
     "CCI(high, low, close, 20)", "momentum")
_reg("AROON_OSC", _aroon_osc, "AROON_OSC(high, low, period=25)",
     "Aroon Oscillator (Up - Down), range [-100, 100]. Needs high/low (OHLCV frame).",
     "AROON_OSC(high, low, 25)", "trend")
_reg("ADX", _adx, "ADX(high, low, close, period=14)",
     "Average Directional Index — trend strength, range [0, 100]. "
     "Needs high/low (OHLCV frame).", "ADX(high, low, close, 14)", "trend")

_reg("OBV", _obv, "OBV(close, volume)",
     "On-Balance Volume (signed cumulative volume).", "OBV(close, volume)", "volume")

_reg("DELAY", _delay, "DELAY(x, n)",
     "Value n periods ago (shift).", "DELAY(close, 1)", "timeseries")
_reg("TS_SUM", _ts_sum, "TS_SUM(x, window)",
     "Rolling sum.", "TS_SUM(volume, 5)", "timeseries")
_reg("TS_MEAN", _ts_mean, "TS_MEAN(x, window)",
     "Rolling mean.", "TS_MEAN(close, 5)", "timeseries")
_reg("TS_STD", _ts_std, "TS_STD(x, window)",
     "Rolling standard deviation.", "TS_STD(close, 20)", "timeseries")
_reg("TS_MAX", _ts_max, "TS_MAX(x, window)",
     "Rolling maximum.", "TS_MAX(close, 20)", "timeseries")
_reg("TS_MIN", _ts_min, "TS_MIN(x, window)",
     "Rolling minimum.", "TS_MIN(close, 20)", "timeseries")
_reg("TS_RANK", _ts_rank, "TS_RANK(x, window)",
     "Rolling percentile rank of the latest value in [0,1].", "TS_RANK(close, 20)", "timeseries")
_reg("TS_CORR", _ts_corr, "TS_CORR(x, y, window)",
     "Rolling Pearson correlation of two series.", "TS_CORR(close, volume, 20)", "timeseries")
_reg("TS_ARGMAX", _ts_argmax, "TS_ARGMAX(x, window)",
     "Offset (0=oldest) of the max within the window.", "TS_ARGMAX(close, 20)", "timeseries")
_reg("TS_ARGMIN", _ts_argmin, "TS_ARGMIN(x, window)",
     "Offset (0=oldest) of the min within the window.", "TS_ARGMIN(close, 20)", "timeseries")
_reg("DECAYLINEAR", _decaylinear, "DECAYLINEAR(x, window)",
     "Linearly-weighted rolling mean (recent-weighted).", "DECAYLINEAR(close, 10)", "timeseries")
_reg("LOG_RETURN", _log_return, "LOG_RETURN(x, n=1)",
     "Log return over n periods.", "LOG_RETURN(close, 1)", "timeseries")
_reg("DIFF", _diff, "DIFF(x, n=1)",
     "Discrete difference over n periods.", "DIFF(close, 1)", "timeseries")
_reg("PCT_CHANGE", _pct_change, "PCT_CHANGE(x, n=1)",
     "Fractional change over n periods.", "PCT_CHANGE(close, 1)", "timeseries")

_reg("RANK", _rank, "RANK(x)",
     "Full-series percentile rank in [0,1] (single-asset cross-section proxy).",
     "RANK(close)", "cross_section")
_reg("ZSCORE", _zscore, "ZSCORE(x, window)",
     "Rolling z-score over window.", "ZSCORE(close, 20)", "cross_section")
_reg("NORMALIZE", _normalize, "NORMALIZE(x, window)",
     "Rolling min-max normalize to [0,1].", "NORMALIZE(close, 20)", "cross_section")

_reg("ABS", _abs, "ABS(x)",
     "Absolute value.", "ABS(MOM(close, 5))", "math")
_reg("LOG", _log, "LOG(x)",
     "Natural logarithm.", "LOG(close)", "math")
_reg("SIGN", _sign, "SIGN(x)",
     "Sign (-1/0/1).", "SIGN(DIFF(close, 1))", "math")
_reg("SQRT", _sqrt, "SQRT(x)",
     "Square root.", "SQRT(volume)", "math")
_reg("POW", _power, "POW(x, p)",
     "x raised to the power p.", "POW(close, 2)", "math")
_reg("MAX", _max, "MAX(x, y)",
     "Element-wise maximum.", "MAX(close, SMA(close, 20))", "math")
_reg("MIN", _min, "MIN(x, y)",
     "Element-wise minimum.", "MIN(close, SMA(close, 20))", "math")


# --------------------------------------------------------------------------- #
# E12-S2 — Safe declarative factor expression evaluator
#
# Factors are *data*: a string like "(close-EMA(close,200))/close" is parsed with
# the stdlib ``ast`` module (NO ``asteval``, NO ``eval``/``exec``/``compile``) and
# walked under a strict whitelist. Only four things are ever permitted:
#   1. calls to FUNCTION_REGISTRY primitives (by bare name),
#   2. frame column names (resolved to the column Series),
#   3. numeric literals,
#   4. arithmetic / unary / comparison operators.
# Every other AST node — attribute access, subscripts, dunders, imports, lambdas,
# comprehensions, arbitrary calls — is rejected with ValueError *before* any value
# is produced. There is no path to arbitrary code execution.
#
# The frame is whatever ``db.load_close_series`` yields: a daily index with
# ``close`` + ``volume`` columns. Factors that reference high/low (e.g. ATR) name a
# column the frame does not have, so they raise "unknown column" rather than
# silently fabricating values — the documented deferral, surfaced not faked.
# --------------------------------------------------------------------------- #

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# Hard cap on AST size. Real factor expressions are tiny (tens of nodes); a much
# larger tree is either pathological or an attempt to exhaust the stack (a deep
# unary/operator chain) — reject it as ValueError before the recursive walk so the
# evaluator's contract ("raises ValueError, never RecursionError") always holds.
_MAX_NODES = 256
_CMPOPS = {
    ast.Lt: operator.lt,
    ast.Gt: operator.gt,
    ast.LtE: operator.le,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def evaluate(expr, frame):
    """Safely evaluate a factor expression ``expr`` over a pandas ``frame``.

    Returns a pandas Series (or, for pure-comparison factors, a boolean Series).
    A degenerate expression that references no column (e.g. "1 + 1") returns a
    plain float/bool scalar — real factors always touch a column. Partial windows
    surface as NaN — never fabricated. Raises ValueError for any syntactically
    invalid, oversized, or disallowed expression; nothing outside the whitelist is
    ever executed (no RecursionError, no unbounded compute).
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, RecursionError, ValueError) as exc:
        raise ValueError(f"invalid factor expression: {exc}") from exc
    n_nodes = sum(1 for _ in ast.walk(tree))
    if n_nodes > _MAX_NODES:
        raise ValueError(f"expression too large ({n_nodes} nodes > {_MAX_NODES})")
    try:
        return _eval_node(tree.body, frame)
    except (OverflowError, ZeroDivisionError, RecursionError) as exc:
        # Whitelisted-but-pathological arithmetic (e.g. 9**9**9 overflowing float,
        # scalar divide-by-zero). Surface as ValueError so callers have one error
        # contract to catch — never an unbounded hang or a leaked builtin error.
        raise ValueError(f"expression could not be evaluated: {exc}") from exc


def _eval_node(node, frame):
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"operator {type(node.op).__name__} is not allowed")
        return op(_eval_node(node.left, frame), _eval_node(node.right, frame))

    if isinstance(node, ast.UnaryOp):
        op = _UNARYOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unary operator {type(node.op).__name__} is not allowed")
        return op(_eval_node(node.operand, frame))

    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("chained comparisons are not allowed")
        op = _CMPOPS.get(type(node.ops[0]))
        if op is None:
            raise ValueError(f"comparison {type(node.ops[0]).__name__} is not allowed")
        return op(_eval_node(node.left, frame), _eval_node(node.comparators[0], frame))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("only direct calls to registry functions are allowed")
        name = node.func.id
        if name not in FUNCTION_REGISTRY:
            raise ValueError(f"unknown function: {name!r}")
        if node.keywords:
            raise ValueError("keyword arguments are not allowed in factor expressions")
        args = [_eval_node(arg, frame) for arg in node.args]
        return FUNCTION_REGISTRY[name].fn(*args)

    if isinstance(node, ast.Name):
        if node.id in frame.columns:
            return frame[node.id]
        raise ValueError(f"unknown column or name: {node.id!r}")

    if isinstance(node, ast.Constant):
        # Reject bool (a subclass of int), str, bytes, complex, None — numbers only.
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"only numeric literals are allowed, got {node.value!r}")
        # Coerce to float: factor math is over float Series, and it makes integer
        # power expressions (9**9**9) overflow to inf instead of spinning up a
        # multi-hundred-megabyte bignum. Window args are re-cast to int inside the
        # primitives, so float literals stay correct there too.
        return float(node.value)

    raise ValueError(f"disallowed expression element: {type(node).__name__}")


# --------------------------------------------------------------------------- #
# E12-S3 — Built-in factor library (ported from HammerGPT, Apache-2.0)
#
# Factors are DATA, not code: each is a string expression over the registry
# primitives plus the OHLCV columns. Adding a factor is editing this
# list — no new Python. Definitions are re-homed (not copied) onto E12-S1
# primitives from HammerGPT's ``insert_builtin_expression_factors.py`` (Apache-2.0;
# see the NOTICE file). The project is MIT — permissive, attribution preserved.
#
# Most factors use only close+volume (evaluable against db.load_close_series). The
# final "ohlcv" group needs high/low (ADX, Aroon, CCI, Williams %R, ATR-ratio) and
# is reachable from db.load_ohlcv_daily, which resamples the candle `ohlc` table to
# daily OHLCV. Against a close-only frame those five evaluate to NaN gracefully
# (score_factors and the engine both catch the missing-column error per-factor), so
# they are discoverable everywhere but only score where high/low is present.
#
# Current total: 67 factors — 62 close+volume + 5 OHLCV (high/low). Toward the ~64
# HammerGPT target; the OHLCV five close the remaining high/low-dependent gap.
# --------------------------------------------------------------------------- #

BUILTIN_FACTORS: list[dict] = [
    # ---- trend ----
    {"name": "price_vs_sma20", "expression": "(close - SMA(close, 20)) / SMA(close, 20)",
     "description": "Close relative to its 20-day SMA.", "category": "trend"},
    {"name": "price_vs_sma50", "expression": "(close - SMA(close, 50)) / SMA(close, 50)",
     "description": "Close relative to its 50-day SMA.", "category": "trend"},
    {"name": "price_vs_ema200", "expression": "(close - EMA(close, 200)) / close",
     "description": "Close relative to its 200-day EMA (regime).", "category": "trend"},
    {"name": "price_vs_ema50", "expression": "(close - EMA(close, 50)) / EMA(close, 50)",
     "description": "Close relative to its 50-day EMA.", "category": "trend"},
    {"name": "sma_cross_20_50", "expression": "(SMA(close, 20) - SMA(close, 50)) / SMA(close, 50)",
     "description": "20/50 SMA spread (golden/death-cross proxy).", "category": "trend"},
    {"name": "ema_cross_12_26", "expression": "(EMA(close, 12) - EMA(close, 26)) / EMA(close, 26)",
     "description": "12/26 EMA spread.", "category": "trend"},
    {"name": "ema_ribbon_8_21", "expression": "(EMA(close, 8) - EMA(close, 21)) / EMA(close, 21)",
     "description": "8/21 EMA ribbon spread (fast momentum ribbon).", "category": "trend"},
    {"name": "slope_10", "expression": "LINEARREG_SLOPE(close, 10) / close",
     "description": "Normalized 10-day regression slope.", "category": "trend"},
    {"name": "slope_20", "expression": "LINEARREG_SLOPE(close, 20) / close",
     "description": "Normalized 20-day regression slope.", "category": "trend"},
    {"name": "slope_50", "expression": "LINEARREG_SLOPE(close, 50) / close",
     "description": "Normalized 50-day regression slope.", "category": "trend"},
    {"name": "dist_from_high_60", "expression": "(close - TS_MAX(close, 60)) / TS_MAX(close, 60)",
     "description": "Drawdown from the 60-day high.", "category": "trend"},
    {"name": "dist_from_low_60", "expression": "(close - TS_MIN(close, 60)) / TS_MIN(close, 60)",
     "description": "Run-up from the 60-day low.", "category": "trend"},

    # ---- momentum ----
    {"name": "roc_5", "expression": "ROC(close, 5)",
     "description": "5-day rate of change (%).", "category": "momentum"},
    {"name": "roc_10", "expression": "ROC(close, 10)",
     "description": "10-day rate of change (%).", "category": "momentum"},
    {"name": "roc_20", "expression": "ROC(close, 20)",
     "description": "20-day rate of change (%).", "category": "momentum"},
    {"name": "mom_10_norm", "expression": "MOM(close, 10) / close",
     "description": "10-day momentum, price-normalized.", "category": "momentum"},
    {"name": "rsi_7", "expression": "RSI(close, 7)",
     "description": "7-day Wilder RSI (short-term overbought/oversold).", "category": "momentum"},
    {"name": "rsi_14", "expression": "RSI(close, 14)",
     "description": "14-day Wilder RSI.", "category": "momentum"},
    {"name": "rsi_28", "expression": "RSI(close, 28)",
     "description": "28-day Wilder RSI.", "category": "momentum"},
    {"name": "rsi_centered", "expression": "RSI(close, 14) - 50",
     "description": "RSI centered on zero (sign = bias).", "category": "momentum"},
    {"name": "macd_line", "expression": "MACD(close)",
     "description": "MACD line (12/26).", "category": "momentum"},
    {"name": "macd_hist", "expression": "MACD_HIST(close)",
     "description": "MACD histogram.", "category": "momentum"},
    {"name": "macd_hist_norm", "expression": "MACD_HIST(close) / close",
     "description": "MACD histogram, price-normalized.", "category": "momentum"},
    {"name": "log_return_1", "expression": "LOG_RETURN(close, 1)",
     "description": "1-day log return.", "category": "momentum"},
    {"name": "log_return_5", "expression": "LOG_RETURN(close, 5)",
     "description": "5-day log return.", "category": "momentum"},
    {"name": "cum_return_10", "expression": "close / DELAY(close, 10) - 1",
     "description": "10-day cumulative return.", "category": "momentum"},
    {"name": "cum_return_20", "expression": "close / DELAY(close, 20) - 1",
     "description": "20-day cumulative return.", "category": "momentum"},
    {"name": "momentum_accel", "expression": "MOM(close, 5) - DELAY(MOM(close, 5), 5)",
     "description": "Acceleration of 5-day momentum.", "category": "momentum"},

    # ---- volatility ----
    {"name": "std_5_norm", "expression": "STDDEV(close, 5) / close",
     "description": "5-day price stdev, normalized.", "category": "volatility"},
    {"name": "std_20_norm", "expression": "STDDEV(close, 20) / close",
     "description": "20-day price stdev, normalized.", "category": "volatility"},
    {"name": "std_ratio_10_30", "expression": "STDDEV(close, 10) / STDDEV(close, 30)",
     "description": "Short/long volatility ratio.", "category": "volatility"},
    {"name": "bb_pctb_10", "expression": "BBANDS_PCTB(close, 10, 2)",
     "description": "Bollinger %B (10, 2) — short-band position.", "category": "volatility"},
    {"name": "bb_pctb_20", "expression": "BBANDS_PCTB(close, 20, 2)",
     "description": "Bollinger %B (20, 2).", "category": "volatility"},
    {"name": "return_vol_10", "expression": "TS_STD(LOG_RETURN(close, 1), 10)",
     "description": "10-day realized return volatility.", "category": "volatility"},
    {"name": "return_vol_20", "expression": "TS_STD(LOG_RETURN(close, 1), 20)",
     "description": "20-day realized return volatility.", "category": "volatility"},
    {"name": "range_60_norm", "expression": "(TS_MAX(close, 60) - TS_MIN(close, 60)) / close",
     "description": "60-day high-low range, normalized.", "category": "volatility"},
    {"name": "abs_return_mean_10", "expression": "TS_MEAN(ABS(LOG_RETURN(close, 1)), 10)",
     "description": "10-day mean absolute return.", "category": "volatility"},

    # ---- volume ----
    {"name": "obv", "expression": "OBV(close, volume)",
     "description": "On-Balance Volume.", "category": "volume"},
    {"name": "obv_slope_20", "expression": "LINEARREG_SLOPE(OBV(close, volume), 20)",
     "description": "20-day slope of OBV.", "category": "volume"},
    {"name": "obv_zscore_20", "expression": "ZSCORE(OBV(close, volume), 20)",
     "description": "20-day z-score of OBV (normalized accumulation/distribution).", "category": "volume"},
    {"name": "volume_zscore_5", "expression": "ZSCORE(volume, 5)",
     "description": "Volume z-score over 5 days (very short-term surge).", "category": "volume"},
    {"name": "volume_zscore_20", "expression": "ZSCORE(volume, 20)",
     "description": "Volume z-score over 20 days.", "category": "volume"},
    {"name": "volume_ratio_20", "expression": "volume / TS_MEAN(volume, 20)",
     "description": "Volume vs. its 20-day average.", "category": "volume"},
    {"name": "volume_roc_10", "expression": "ROC(volume, 10)",
     "description": "10-day volume rate of change.", "category": "volume"},
    {"name": "price_volume_corr_20", "expression": "TS_CORR(close, volume, 20)",
     "description": "20-day price-volume correlation.", "category": "volume"},
    {"name": "volume_trend", "expression": "(TS_MEAN(volume, 5) - TS_MEAN(volume, 20)) / TS_MEAN(volume, 20)",
     "description": "Short/long volume trend.", "category": "volume"},

    # ---- statistical / cross-section ----
    {"name": "zscore_close_20", "expression": "ZSCORE(close, 20)",
     "description": "20-day price z-score.", "category": "statistical"},
    {"name": "zscore_close_50", "expression": "ZSCORE(close, 50)",
     "description": "50-day price z-score.", "category": "statistical"},
    {"name": "normalize_close_20", "expression": "NORMALIZE(close, 20)",
     "description": "20-day min-max normalized price.", "category": "statistical"},
    {"name": "normalize_close_60", "expression": "NORMALIZE(close, 60)",
     "description": "60-day min-max normalized price.", "category": "statistical"},
    {"name": "ts_rank_close_20", "expression": "TS_RANK(close, 20)",
     "description": "Rolling 20-day percentile rank of close.", "category": "statistical"},
    {"name": "ts_rank_close_50", "expression": "TS_RANK(close, 50)",
     "description": "Rolling 50-day percentile rank of close.", "category": "statistical"},
    {"name": "ts_rank_volume_20", "expression": "TS_RANK(volume, 20)",
     "description": "Rolling 20-day percentile rank of volume.", "category": "statistical"},
    {"name": "rank_close", "expression": "RANK(close)",
     "description": "Full-series percentile rank of close.", "category": "statistical"},
    {"name": "ts_argmax_close_20", "expression": "TS_ARGMAX(close, 20)",
     "description": "Days since the 20-day high (offset).", "category": "statistical"},
    {"name": "ts_argmin_close_20", "expression": "TS_ARGMIN(close, 20)",
     "description": "Days since the 20-day low (offset).", "category": "statistical"},
    {"name": "decaylinear_return_10", "expression": "DECAYLINEAR(LOG_RETURN(close, 1), 10)",
     "description": "Recency-weighted 10-day return.", "category": "statistical"},

    # ---- composite ----
    {"name": "trend_strength", "expression": "SIGN(close - SMA(close, 50)) * ABS(ZSCORE(close, 50))",
     "description": "Signed distance-from-trend magnitude.", "category": "composite"},
    {"name": "mean_reversion_20", "expression": "-ZSCORE(close, 20)",
     "description": "Mean-reversion signal (negated z-score).", "category": "composite"},
    {"name": "vol_adj_momentum", "expression": "ROC(close, 20) / (STDDEV(close, 20) / close)",
     "description": "Volatility-adjusted 20-day momentum.", "category": "composite"},
    {"name": "momentum_vol_ratio_10", "expression": "ROC(close, 10) / STDDEV(close, 10)",
     "description": "10-day Sharpe-style momentum (return per unit of volatility).", "category": "composite"},
    {"name": "price_vol_divergence", "expression": "SIGN(ROC(close, 10)) * SIGN(ROC(volume, 10))",
     "description": "Price/volume direction agreement (+1 confirm, -1 diverge).", "category": "composite"},

    # ---- ohlcv (high/low) ----
    # Reachable only from an OHLCV frame (db.load_ohlcv_daily); they evaluate to
    # NaN (gracefully) against the close+volume load_close_series frame because the
    # high/low columns are absent — score_factors/engine both catch that per-factor.
    {"name": "atr_ratio_14", "expression": "ATR(high, low, close, 14) / close",
     "description": "Average True Range as a fraction of price (normalized volatility).",
     "category": "volatility"},
    {"name": "williams_r_14", "expression": "WILLR(high, low, close, 14)",
     "description": "Williams %R (close position in the 14-day high-low range).",
     "category": "momentum"},
    {"name": "cci_20", "expression": "CCI(high, low, close, 20)",
     "description": "Commodity Channel Index over 20 days.", "category": "momentum"},
    {"name": "aroon_25", "expression": "AROON_OSC(high, low, 25)",
     "description": "Aroon Oscillator over 25 days (trend direction/age).", "category": "trend"},
    {"name": "adx_14", "expression": "ADX(high, low, close, 14)",
     "description": "Average Directional Index over 14 days (trend strength).", "category": "trend"},
]


# Previously-deferred high/low/open factors are now LIVE (in BUILTIN_FACTORS above)
# since db.load_ohlcv_daily provides an OHLCV frame and the WILLR/CCI/AROON_OSC/ADX
# primitives are registered. Kept as an (empty) list so importers referencing the
# name still resolve and the audit trail of what was deferred stays in git history.
DEFERRED_FACTORS: list[dict] = []
