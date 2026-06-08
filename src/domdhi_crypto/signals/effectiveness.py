"""IC/ICIR factor-effectiveness module.

Measures how predictive a factor is of future price moves via Information
Coefficient (IC) — the Spearman rank correlation between a factor value at time
*t* and the *n*-period forward return at time *t*.

Forward-return invariant (load-bearing)
---------------------------------------
The forward return is ``close.pct_change(horizon).shift(-horizon)``, which
equals ``close[t+horizon] / close[t] - 1``.  The last ``horizon`` rows always
produce NaN and are **never filled**.  Any alignment step calls ``.dropna()``
so those trailing rows never enter the correlation — a filled tail would leak
future information into the IC estimate and inflate noise scores.

ADR-001 note
------------
Pure numpy/pandas only.  Spearman rank correlation is computed as
``series.rank(pct=True).corr(other.rank(pct=True))`` — no scipy, no
pandas-ta.  This is an auditable, hand-rolled computation that matches the
``numpy.corrcoef``-over-ranks reference used in the test suite within 1e-6.

min_periods=2 exception
-----------------------
``icir()`` and ``rolling_ic()`` use ``ic.std()`` (pandas default ddof=1),
which requires at least 2 defined IC points to produce a finite result.  The
project default is ``min_periods=window`` to avoid fabricating statistics from
partial windows; here the IC series is already sparse (one point per aligned
window), so ``min_periods=2`` is the documented exception — ICIR is NaN until
≥ 2 defined rolling-IC points exist, never fabricated.
"""
import numpy as np
import pandas as pd

from . import factors

# --------------------------------------------------------------------------- #
# Core IC computation
# --------------------------------------------------------------------------- #


def information_coefficient(factor: pd.Series, close: pd.Series, horizon: int = 5) -> float:
    """Spearman rank correlation between ``factor`` and the ``horizon``-period forward return.

    Forward return is ``close.pct_change(horizon).shift(-horizon)``; the last
    ``horizon`` rows are NaN and never filled.  The two series are aligned into a
    joint frame and ``.dropna()`` is called before correlation — rows where either
    is NaN (factor warmup or the NaN tail) are excluded.

    Returns ``float('nan')`` when fewer than 2 overlapping non-NaN points exist.
    """
    fwd = close.pct_change(horizon).shift(-horizon)
    df = pd.DataFrame({"f": factor, "r": fwd}).dropna()
    if len(df) < 2:
        return float("nan")
    return float(df["f"].rank(pct=True).corr(df["r"].rank(pct=True)))


# --------------------------------------------------------------------------- #
# Rolling IC
# --------------------------------------------------------------------------- #


def rolling_ic(
    factor: pd.Series,
    close: pd.Series,
    horizon: int = 5,
    window: int = 20,
) -> pd.Series:
    """Rolling Spearman IC: IC at each aligned point using the trailing ``window`` rows.

    Only positions with a full trailing ``window`` of aligned (factor, fwd) rows
    produce a defined IC; the head of the returned Series is NaN.  The returned
    Series is indexed by the aligned dropna index — positions before a full window
    are NaN (partial windows never fabricated).

    min_periods=2 exception: see module docstring.
    """
    fwd = close.pct_change(horizon).shift(-horizon)
    df = pd.DataFrame({"f": factor, "r": fwd}).dropna()
    out = pd.Series(np.nan, index=df.index)
    for i in range(window - 1, len(df)):
        w = df.iloc[i - window + 1 : i + 1]
        out.iloc[i] = w["f"].rank(pct=True).corr(w["r"].rank(pct=True))
    return out


# --------------------------------------------------------------------------- #
# ICIR
# --------------------------------------------------------------------------- #


def icir(
    factor: pd.Series,
    close: pd.Series,
    horizon: int = 5,
    window: int = 20,
) -> float:
    """Information Coefficient Information Ratio: mean(rolling IC) / std(rolling IC).

    ``std`` uses pandas default ddof=1 and requires ≥ 2 defined rolling-IC
    points (min_periods=2 exception — see module docstring).  Returns NaN when
    fewer than 2 defined IC points exist.
    """
    ic = rolling_ic(factor, close, horizon=horizon, window=window).dropna()
    if len(ic) < 2:
        return float("nan")
    std = ic.std()
    # Zero (or non-finite) IC dispersion -> ICIR is undefined. Returning inf here
    # would sort a degenerate, no-dispersion factor to the TOP of score_factors
    # (-inf sorts first); NaN sorts last, which is the correct treatment.
    if not np.isfinite(std) or std == 0:
        return float("nan")
    return float(ic.mean() / std)


# --------------------------------------------------------------------------- #
# Factor scoring
# --------------------------------------------------------------------------- #


def score_factors(
    frame: pd.DataFrame,
    factors_list: list[dict],
    horizon: int = 5,
    window: int = 20,
) -> list[dict]:
    """Score a list of factor dicts by IC and ICIR against ``frame['close']``.

    Each dict in ``factors_list`` must have ``'name'`` and ``'expression'`` keys
    (the BUILTIN_FACTORS shape).  Each factor is evaluated via
    ``factors.evaluate(expr, frame)``; evaluation errors are caught and reported
    as ``ic=NaN, icir=NaN`` rather than crashing the whole batch.

    Returns a list of ``{name, category, ic, icir}`` dicts sorted by ICIR
    descending, with NaN ICIR values sorted last.
    """
    close = frame["close"]
    results: list[dict] = []

    for d in factors_list:
        name = d["name"]
        category = d.get("category")
        ic_val = float("nan")
        icir_val = float("nan")

        # Narrow the catch to evaluation only: a bad expression (unknown column,
        # syntax error) must not crash the batch and is reported as NaN. But a bug
        # in information_coefficient/icir — which operate on an already-validated
        # Series — should surface loudly, not be silently swallowed as "all NaN".
        try:
            series = factors.evaluate(d["expression"], frame)
        except Exception:  # noqa: BLE001 - any bad factor expression -> NaN, not a crash
            series = None

        # A degenerate expression (e.g. "1 + 1") yields a scalar, not a Series -> NaN.
        if isinstance(series, pd.Series):
            ic_val = information_coefficient(series, close, horizon=horizon)
            icir_val = icir(series, close, horizon=horizon, window=window)

        results.append({"name": name, "category": category, "ic": ic_val, "icir": icir_val})

    results.sort(
        key=lambda r: (-r["icir"]) if not np.isnan(r["icir"]) else float("inf")
    )
    return results
