"""Tests for the execution simulator (backtest/execution_simulator.py).

Pins the cost model: zero-cost reproduces the bar close exactly, slippage is
adverse to order side (buys fill higher, sells lower), fees are always a positive
cost regardless of side, and the conversion is deterministic. Slippage is in
basis points: slip = slippage_bps / 10_000.
"""
import pandas as pd
import pytest

from domdhi_crypto.backtest import Bar, Order
from domdhi_crypto.backtest.execution_simulator import simulate_fill

TS = pd.Timestamp("2024-01-01")


def _bar(close=100.0):
    return Bar(timestamp=TS, close=close, volume=5.0)


def _order(side, notional=1000.0):
    return Order(timestamp=TS, side=side, notional=notional)


# --------------------------------------------------------------------------- #
# Zero-cost identity
# --------------------------------------------------------------------------- #

def test_zero_slippage_zero_fee_reproduces_bar_close():
    fill = simulate_fill(_order("buy"), _bar(100.0), slippage_bps=0.0, fee_rate=0.0)
    assert fill.price == 100.0
    assert fill.fee == 0.0
    assert fill.side == "buy"
    assert fill.timestamp == TS


# --------------------------------------------------------------------------- #
# Slippage direction (adverse to side)
# --------------------------------------------------------------------------- #

def test_buy_slippage_raises_fill_price():
    fill = simulate_fill(_order("buy"), _bar(100.0), slippage_bps=50.0, fee_rate=0.0)
    assert fill.price == pytest.approx(100.0 * (1 + 50.0 / 10_000))  # 100.5


def test_sell_slippage_lowers_fill_price():
    fill = simulate_fill(_order("sell"), _bar(100.0), slippage_bps=50.0, fee_rate=0.0)
    assert fill.price == pytest.approx(100.0 * (1 - 50.0 / 10_000))  # 99.5


# --------------------------------------------------------------------------- #
# Fee positivity (both sides)
# --------------------------------------------------------------------------- #

def test_fee_is_a_positive_cost_on_both_sides():
    buy = simulate_fill(_order("buy", 1000.0), _bar(100.0), slippage_bps=0.0, fee_rate=0.001)
    sell = simulate_fill(_order("sell", 1000.0), _bar(100.0), slippage_bps=0.0, fee_rate=0.001)
    assert buy.fee == pytest.approx(1.0)   # 0.001 * 1000
    assert sell.fee == pytest.approx(1.0)
    assert buy.fee >= 0.0 and sell.fee >= 0.0


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

def test_same_inputs_produce_identical_fill():
    a = simulate_fill(_order("buy"), _bar(100.0), slippage_bps=50.0, fee_rate=0.001)
    b = simulate_fill(_order("buy"), _bar(100.0), slippage_bps=50.0, fee_rate=0.001)
    assert (a.price, a.fee, a.side, a.timestamp) == (b.price, b.fee, b.side, b.timestamp)
