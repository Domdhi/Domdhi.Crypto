"""Tests for the backtest package's shared frozen dataclasses (backtest/__init__.py).

These types are the cross-module contract every backtest module imports, so the
suite pins (1) the exact field names, (2) frozen immutability, and (3) the
``Trade.holding_period`` derived helper. Field-name drift here would silently
fan out into the data provider, account, simulator, engine, and attribution.
"""
import dataclasses

import pandas as pd
import pytest

from domdhi_crypto.backtest import BacktestResult, Bar, Fill, Order, Trade

# --------------------------------------------------------------------------- #
# Construction + field-name contract
# --------------------------------------------------------------------------- #

def test_bar_fields():
    b = Bar(timestamp=pd.Timestamp("2024-01-01"), close=100.0, volume=5.0)
    assert b.timestamp == pd.Timestamp("2024-01-01")
    assert b.close == 100.0
    assert b.volume == 5.0


def test_order_fields():
    o = Order(timestamp=pd.Timestamp("2024-01-01"), side="buy", notional=1000.0)
    assert o.side == "buy"
    assert o.notional == 1000.0


def test_fill_fields():
    f = Fill(timestamp=pd.Timestamp("2024-01-01"), price=101.0, fee=0.5, side="sell")
    assert f.price == 101.0
    assert f.fee == 0.5
    assert f.side == "sell"


def test_trade_fields_including_triggering_factor():
    t = Trade(
        entry_ts=pd.Timestamp("2024-01-01"),
        exit_ts=pd.Timestamp("2024-01-06"),
        realized_return=0.05,
        triggering_factor="rsi_14",
    )
    assert t.entry_ts == pd.Timestamp("2024-01-01")
    assert t.exit_ts == pd.Timestamp("2024-01-06")
    assert t.realized_return == 0.05
    assert t.triggering_factor == "rsi_14"


def test_backtest_result_summary_carries_required_keys():
    summary = {
        "total_return": 0.10,
        "total_realized_return": 0.08,
        "win_rate": 0.5,
        "max_drawdown": -0.2,
    }
    r = BacktestResult(trades=[], summary=summary)
    assert r.trades == []
    for key in ("total_return", "total_realized_return", "win_rate", "max_drawdown"):
        assert key in r.summary


# --------------------------------------------------------------------------- #
# Derived helper
# --------------------------------------------------------------------------- #

def test_trade_holding_period_is_timedelta():
    t = Trade(
        entry_ts=pd.Timestamp("2024-01-01"),
        exit_ts=pd.Timestamp("2024-01-05"),
        realized_return=0.0,
        triggering_factor="x",
    )
    assert t.holding_period == pd.Timedelta(days=4)


# --------------------------------------------------------------------------- #
# Immutability  (frozen=True -> FrozenInstanceError on assignment)
# --------------------------------------------------------------------------- #

def test_bar_is_frozen():
    b = Bar(timestamp=pd.Timestamp("2024-01-01"), close=1.0, volume=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.close = 2.0


def test_order_is_frozen():
    o = Order(timestamp=pd.Timestamp("2024-01-01"), side="buy", notional=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        o.notional = 2.0


def test_fill_is_frozen():
    f = Fill(timestamp=pd.Timestamp("2024-01-01"), price=1.0, fee=0.0, side="buy")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.price = 2.0


def test_trade_is_frozen():
    t = Trade(
        entry_ts=pd.Timestamp("2024-01-01"),
        exit_ts=pd.Timestamp("2024-01-02"),
        realized_return=0.0,
        triggering_factor="x",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.realized_return = 1.0


def test_backtest_result_is_frozen():
    r = BacktestResult(trades=[], summary={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.summary = {"x": 1}


def test_backtest_result_equity_curve_field():
    """E18-S5: equity_curve is a backward-compatible field defaulting to an empty
    Series, and accepts an explicit curve."""
    r = BacktestResult(trades=[], summary={})
    assert isinstance(r.equity_curve, pd.Series) and r.equity_curve.empty
    curve = pd.Series([1.0, 2.0], index=pd.date_range("2024-01-01", periods=2))
    r2 = BacktestResult(trades=[], summary={}, equity_curve=curve)
    assert list(r2.equity_curve) == [1.0, 2.0]
