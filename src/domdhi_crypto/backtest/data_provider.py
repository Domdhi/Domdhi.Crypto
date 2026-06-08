"""Look-ahead-safe data provider for the Domdhi.Crypto backtester.

The load-bearing property is the look-ahead guard: at any event time T, the
provider surfaces only bars whose timestamp is <= T. No future bar is ever
returned by ``history`` or ``bar_at``; ``next_bar`` returns None at the end of
the series rather than fabricating a value. This contract is what makes a
backtest free of lookahead bias.

Operates on ``db.load_close_series`` close+volume daily bars only — NOT
``load_ohlc``, which is a separate table at a different time granularity. A
``Bar`` therefore carries ``close`` and ``volume`` only; there is no ``high``
or ``low`` field. This is not an omission — it reflects the real data boundary.

This module is a deliberate *leaf*: it imports pandas and the backtest package
types only — it does not import ``db`` or any other internal module. The caller
is responsible for passing a prepared ``pd.DataFrame``; this keeps the module
independently importable and side-effect free.

Determinism guarantee: all iteration and slicing is driven exclusively by the
sorted DatetimeIndex. No sets, no dict ordering, no randomness.
"""
from __future__ import annotations

from collections.abc import Iterator

import pandas as pd

from . import Bar

# --------------------------------------------------------------------------- #
# Data provider
# --------------------------------------------------------------------------- #


class DataProvider:
    """Serves bars from a close+volume daily frame in ascending time order.

    The frame is sorted on construction so that the provider is correct even
    if the caller passes data in reverse or shuffled order.
    """

    def __init__(self, frame: pd.DataFrame) -> None:
        """Store the sorted frame and cache the ordered timestamp list.

        Parameters
        ----------
        frame:
            A ``pd.DataFrame`` with a ``DatetimeIndex`` and at least ``close``
            and ``volume`` columns, as returned by ``db.load_close_series``.
        """
        # Sort ascending, then drop duplicate timestamps (keep the last row for a
        # given day). load_close_series yields a unique gap-free daily index, but a
        # defensive leaf must not break on raw/dup input: a duplicate label would
        # make the scalar point-lookup `self.frame.loc[t]` return a DataFrame, and
        # `float(row["close"])` would then raise TypeError.
        sorted_frame = frame.sort_index()
        self.frame: pd.DataFrame = sorted_frame[~sorted_frame.index.duplicated(keep="last")]
        self._timestamps: list[pd.Timestamp] = list(self.frame.index)

    # ---------------------------------------------------------------------- #
    # Index access
    # ---------------------------------------------------------------------- #

    def timestamps(self) -> list[pd.Timestamp]:
        """Return the ascending list of index labels (one per bar)."""
        return list(self._timestamps)

    # ---------------------------------------------------------------------- #
    # Iteration
    # ---------------------------------------------------------------------- #

    def __iter__(self) -> Iterator[Bar]:
        """Yield every Bar in ascending timestamp order."""
        for ts in self._timestamps:
            row = self.frame.loc[ts]
            yield Bar(
                timestamp=ts,
                close=float(row["close"]),
                volume=float(row["volume"]),
            )

    # ---------------------------------------------------------------------- #
    # Look-ahead-safe history accessors
    # ---------------------------------------------------------------------- #

    def history(self, t: pd.Timestamp) -> list[Bar]:
        """Return all bars with timestamp <= t, in ascending order (inclusive).

        The look-ahead guard is enforced structurally: ``.loc[:t]`` on a sorted
        DatetimeIndex can only yield labels <= t.
        """
        slice_frame = self.frame.loc[:t]
        bars: list[Bar] = []
        for ts, row in slice_frame.iterrows():
            bars.append(Bar(
                timestamp=ts,
                close=float(row["close"]),
                volume=float(row["volume"]),
            ))
        return bars

    def history_frame(self, t: pd.Timestamp) -> pd.DataFrame:
        """Return the raw frame slice up to and including t.

        Equivalent to ``self.frame.loc[:t]`` — a label-based inclusive slice.
        """
        return self.frame.loc[:t]

    def bar_at(self, t: pd.Timestamp) -> Bar | None:
        """Return the Bar at exactly timestamp t, or None if t is not in the index."""
        if t not in self.frame.index:
            return None
        row = self.frame.loc[t]
        return Bar(
            timestamp=t,
            close=float(row["close"]),
            volume=float(row["volume"]),
        )

    def next_bar(self, t: pd.Timestamp) -> Bar | None:
        """Return the first bar with timestamp strictly greater than t.

        Returns None when t is the last bar (end-of-series) — never fabricates
        a value or leaks a future bar before it is due.
        """
        later = self.frame.index[self.frame.index > t]
        if len(later) == 0:
            return None
        ts = later[0]
        row = self.frame.loc[ts]
        return Bar(
            timestamp=ts,
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
