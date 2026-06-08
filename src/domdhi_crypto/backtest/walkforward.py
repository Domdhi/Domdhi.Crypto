"""Out-of-sample sub-period validation (walk-forward segmentation) for Domdhi.Crypto (E20-S5).

Design honesty
--------------
This module performs SUB-PERIOD SEGMENTATION of an already-computed equity curve — it
is NOT walk-forward parameter optimisation and contains NO train/fit step. There is no
model being re-fit in each fold; no parameter is chosen or tuned per-fold.

The single ``engine.run_backtest`` call over the FULL frame is intentional:
  - Long-window factors (e.g. SMA200) require a warm-up period that spans many bars.
    Running independent backtests per fold would null out those factors in early folds,
    producing artificially bad returns that do not reflect live behaviour.
  - Look-ahead safety is INHERITED from the engine's time-gated DataProvider and
    history_frame(T) truncation. The folds merely re-index into the equity curve that
    the engine already produced; they do NOT re-derive any signals or equity values.
  - The segmentation is honest: fold i contains bars [lo, hi] inclusive. The cortex
    return for fold i is ``equity[hi] / equity[lo] - 1``, which is the actual compounded
    return the strategy produced over that sub-period given its full history context.
    The benchmark return is ``close[hi] / close[lo] - 1``, a simple buy-and-hold slice.

Leaf constraint (ADR-001 / acyclic import graph)
------------------------------------------------
This module imports ONLY ``backtest.engine``, ``pandas``, ``numpy``, and ``dataclasses``.
It must never import ``cli``, ``dashboard``, ``db``, ``shared``, ``arena``,
``portfolio``, ``agent``, or ``context``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from domdhi_crypto.backtest import engine

# --------------------------------------------------------------------------- #
# Result dataclasses
# --------------------------------------------------------------------------- #

# eq=False: sibling convention from BacktestResult / arena.StrategyResult.
# Fields here are all scalars and timestamps (no pd.Series), but we follow the
# pattern unconditionally so dataclass comparisons never surprise a future reader
# who adds a Series field.


@dataclass(frozen=True, eq=False)
class FoldResult:
    """Per-fold outcome of a walk-forward segmentation run.

    Parameters
    ----------
    index:
        0-based fold ordinal.
    start:
        First timestamp in the fold (inclusive).
    end:
        Last timestamp in the fold (inclusive).
    cortex_return:
        Compounded return of the cortex strategy over this sub-period,
        computed as ``equity[hi] / equity[lo] - 1``.
    benchmark_return:
        Buy-and-hold return over this sub-period,
        computed as ``close[hi] / close[lo] - 1``.
    edge:
        ``cortex_return - benchmark_return``.
    n_trades:
        Count of closed trades whose ``exit_ts`` falls within ``[start, end]`` inclusive.
    """

    index: int
    start: pd.Timestamp
    end: pd.Timestamp
    cortex_return: float
    benchmark_return: float
    edge: float
    n_trades: int


@dataclass(frozen=True, eq=False)
class WalkForwardResult:
    """Aggregated output of a walk-forward segmentation run.

    Parameters
    ----------
    folds:
        Ordered list of ``FoldResult`` objects (one per fold, 0-based).
    n_folds:
        Number of folds (``len(folds)``).
    cortex_win_rate:
        Fraction of folds in which ``edge > 0`` (cortex beat buy-and-hold).
    mean_edge:
        Plain mean of ``edge`` across all folds.
    mean_cortex_return:
        Plain mean of ``cortex_return`` across all folds.
    mean_benchmark_return:
        Plain mean of ``benchmark_return`` across all folds.
    """

    folds: list[FoldResult]
    n_folds: int
    cortex_win_rate: float
    mean_edge: float
    mean_cortex_return: float
    mean_benchmark_return: float


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def walk_forward(
    frame: pd.DataFrame,
    cortex_rules: list[engine.SignalRule],
    *,
    n_splits: int = 4,
    initial_cash: float = 10_000.0,
    slippage_bps: float = 0.0,
    fee_rate: float = 0.0,
) -> WalkForwardResult:
    """Run one look-ahead-safe backtest and segment its equity curve into folds.

    Parameters
    ----------
    frame:
        A close+volume ``pd.DataFrame`` with a ``DatetimeIndex``, as returned by
        ``db.load_close_series``.  Must have a ``"close"`` column.
    cortex_rules:
        Ordered list of ``engine.SignalRule`` objects passed verbatim to
        ``engine.run_backtest``.
    n_splits:
        Number of contiguous, non-overlapping folds to partition the frame into.
        Must satisfy ``1 <= n_splits <= len(frame)``.
    initial_cash:
        Starting cash balance for the virtual account (passed to engine).
    slippage_bps:
        Slippage in basis points (passed to engine).
    fee_rate:
        Fee as a plain fraction of notional (passed to engine).

    Returns
    -------
    WalkForwardResult
        Aggregated walk-forward statistics including per-fold ``FoldResult`` objects.

    Raises
    ------
    ValueError
        If ``n_splits < 1`` or ``n_splits > len(frame)``.
    """
    # Normalise the frame the SAME way the engine's DataProvider does (sort
    # ascending, drop duplicate timestamps keep="last") so that the equity curve
    # (indexed by the engine's normalised frame) and the close/index slices read
    # here reference the SAME bars. Without this, a raw frame with unsorted or
    # duplicate timestamps would make equity.iloc and close.iloc point at
    # different rows — a silent wrong answer — or raise IndexError when the engine
    # collapses duplicates and shortens the curve. Mirrors data_provider.py:56-57.
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]

    if n_splits < 1 or n_splits > len(frame):
        raise ValueError(
            f"n_splits must be between 1 and len(frame)={len(frame)}, got {n_splits}"
        )

    # --- Step 1: single full-frame backtest (look-ahead safety inherited) ---
    bt = engine.run_backtest(
        frame,
        cortex_rules,
        initial_cash=initial_cash,
        slippage_bps=slippage_bps,
        fee_rate=fee_rate,
    )
    equity: pd.Series = bt.equity_curve
    close: pd.Series = frame["close"]

    # --- Step 2: partition integer positions into n_splits contiguous groups ---
    position_groups = np.array_split(np.arange(len(frame)), n_splits)

    folds: list[FoldResult] = []
    for i, group in enumerate(position_groups):
        lo = int(group[0])
        hi = int(group[-1])

        start: pd.Timestamp = frame.index[lo]
        end: pd.Timestamp = frame.index[hi]

        cortex_return = float(equity.iloc[hi] / equity.iloc[lo] - 1.0)
        benchmark_return = float(close.iloc[hi] / close.iloc[lo] - 1.0)
        edge = cortex_return - benchmark_return

        # Count trades whose exit_ts falls within [start, end] inclusive.
        n_trades = sum(1 for t in bt.trades if start <= t.exit_ts <= end)

        folds.append(FoldResult(
            index=i,
            start=start,
            end=end,
            cortex_return=cortex_return,
            benchmark_return=benchmark_return,
            edge=edge,
            n_trades=n_trades,
        ))

    # --- Step 3: aggregates ---
    n_folds = len(folds)
    cortex_win_rate = sum(1 for f in folds if f.edge > 0) / n_folds
    mean_edge = sum(f.edge for f in folds) / n_folds
    mean_cortex_return = sum(f.cortex_return for f in folds) / n_folds
    mean_benchmark_return = sum(f.benchmark_return for f in folds) / n_folds

    return WalkForwardResult(
        folds=folds,
        n_folds=n_folds,
        cortex_win_rate=cortex_win_rate,
        mean_edge=mean_edge,
        mean_cortex_return=mean_cortex_return,
        mean_benchmark_return=mean_benchmark_return,
    )
