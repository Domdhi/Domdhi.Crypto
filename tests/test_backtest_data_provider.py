"""Tests for the look-ahead-safe data provider (backtest/data_provider.py).

The load-bearing property is the look-ahead guard: at any event time T the
provider must never surface a bar with timestamp > T. These tests assert that
for several T, plus the end-of-series behaviour (a future/next bar returns None
rather than leaking or fabricating a value) and deterministic ordering.
"""
import numpy as np
import pandas as pd

from domdhi_crypto.backtest import Bar
from domdhi_crypto.backtest.data_provider import DataProvider


def _frame(n=10):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"close": np.arange(n, dtype=float) + 100, "volume": np.arange(n, dtype=float) + 1},
        index=idx,
    )


# --------------------------------------------------------------------------- #
# Ascending iteration -> Bar objects
# --------------------------------------------------------------------------- #

def test_iter_yields_bars_in_ascending_order():
    fr = _frame(5)
    bars = list(DataProvider(fr))
    assert all(isinstance(b, Bar) for b in bars)
    ts = [b.timestamp for b in bars]
    assert ts == sorted(ts)
    assert bars[0].close == 100.0
    assert bars[0].volume == 1.0


def test_timestamps_are_ascending():
    fr = _frame(6)
    ts = DataProvider(fr).timestamps()
    assert ts == sorted(ts)
    assert ts[0] == fr.index[0]
    assert ts[-1] == fr.index[-1]


# --------------------------------------------------------------------------- #
# Look-ahead guard
# --------------------------------------------------------------------------- #

def test_history_never_returns_a_future_bar():
    fr = _frame(10)
    dp = DataProvider(fr)
    for t in (fr.index[2], fr.index[5], fr.index[9]):
        hist = dp.history(t)
        assert all(b.timestamp <= t for b in hist)
        assert hist[-1].timestamp == t  # inclusive of T


def test_history_frame_is_truncated_at_or_before_t():
    fr = _frame(10)
    dp = DataProvider(fr)
    t = fr.index[5]
    hf = dp.history_frame(t)
    assert (hf.index <= t).all()
    assert hf.index.max() == t


def test_bar_at_future_timestamp_returns_none():
    fr = _frame(5)
    dp = DataProvider(fr)
    future = fr.index[-1] + pd.Timedelta(days=10)
    assert dp.bar_at(future) is None


# --------------------------------------------------------------------------- #
# Next-bar settlement accessor + end-of-series guard
# --------------------------------------------------------------------------- #

def test_next_bar_returns_the_following_bar():
    fr = _frame(5)
    dp = DataProvider(fr)
    nb = dp.next_bar(fr.index[0])
    assert nb is not None
    assert nb.timestamp == fr.index[1]


def test_next_bar_at_end_of_series_returns_none():
    fr = _frame(5)
    dp = DataProvider(fr)
    assert dp.next_bar(fr.index[-1]) is None


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

def test_iteration_is_deterministic_across_reruns():
    fr = _frame(8)
    a = [(b.timestamp, b.close, b.volume) for b in DataProvider(fr)]
    b = [(b.timestamp, b.close, b.volume) for b in DataProvider(fr)]
    assert a == b


# --------------------------------------------------------------------------- #
# Defensive input handling (unsorted / duplicate timestamps)
# --------------------------------------------------------------------------- #

def test_unsorted_input_is_sorted_on_construction():
    fr = _frame(5)
    shuffled = fr.iloc[[3, 0, 4, 1, 2]]
    dp = DataProvider(shuffled)
    assert dp.timestamps() == sorted(dp.timestamps())
    assert dp.timestamps()[0] == fr.index[0]


def test_duplicate_timestamp_bar_at_returns_a_scalar_bar():
    fr = _frame(4)
    dup = pd.concat([fr, fr.iloc[[2]]])  # duplicate the 3rd timestamp
    dp = DataProvider(dup)
    bar = dp.bar_at(fr.index[2])
    assert bar is not None
    assert isinstance(bar.close, float)  # not a Series -> no TypeError
