"""Tests for the virtual account (backtest/virtual_account.py).

Pins the cash/position/equity accounting against hand-computed references: a
multi-fill realized-P/L scenario, the equity-curve -> max-drawdown reference, and
the documented over-trade rule (reject = ValueError). ``mark()`` is the sole
equity-curve writer — applying a fill does NOT record a curve point.
"""
import pandas as pd
import pytest

from domdhi_crypto.backtest import Fill
from domdhi_crypto.backtest.virtual_account import VirtualAccount

TS = pd.Timestamp("2024-01-01")


def _buy(price, fee=0.0):
    return Fill(timestamp=TS, price=price, fee=fee, side="buy")


def _sell(price, fee=0.0):
    return Fill(timestamp=TS, price=price, fee=fee, side="sell")


# --------------------------------------------------------------------------- #
# Cash / position / equity basics
# --------------------------------------------------------------------------- #

def test_starts_with_configured_cash_and_zero_position():
    acct = VirtualAccount(1000.0)
    assert acct.cash == 1000.0
    assert acct.position == 0.0


def test_buy_reduces_cash_by_notional_plus_fee_and_adds_position():
    acct = VirtualAccount(1000.0)
    acct.apply_fill(_buy(100.0, fee=1.0), quantity=2.0)
    assert acct.cash == pytest.approx(1000.0 - (2.0 * 100.0 + 1.0))  # 799.0
    assert acct.position == pytest.approx(2.0)


def test_equity_is_cash_plus_position_times_mark():
    acct = VirtualAccount(1000.0)
    acct.apply_fill(_buy(100.0, fee=0.0), quantity=2.0)  # cash 800, pos 2
    assert acct.equity(110.0) == pytest.approx(800.0 + 2.0 * 110.0)  # 1020.0


# --------------------------------------------------------------------------- #
# Realized / unrealized P/L  (hand-computed multi-fill reference)
# --------------------------------------------------------------------------- #

def test_realized_pnl_matches_multifill_reference():
    acct = VirtualAccount(1000.0)
    acct.apply_fill(_buy(100.0, fee=1.0), quantity=2.0)   # avg cost 100
    acct.apply_fill(_sell(120.0, fee=1.0), quantity=2.0)  # realized = 2*(120-100)
    # realized P/L is avg-cost based, gross of fees (fees flow through cash):
    assert acct.realized_pnl() == pytest.approx(40.0)
    assert acct.position == pytest.approx(0.0)
    # net cash effect: -201 (buy) +239 (sell) = +38 over the starting 1000
    assert acct.cash == pytest.approx(1038.0)


def test_unrealized_pnl_tracks_open_position():
    acct = VirtualAccount(1000.0)
    acct.apply_fill(_buy(100.0, fee=0.0), quantity=3.0)  # avg cost 100
    assert acct.unrealized_pnl(130.0) == pytest.approx(3.0 * (130.0 - 100.0))  # 90.0


# --------------------------------------------------------------------------- #
# Equity curve + max drawdown  (mark() is the sole writer)
# --------------------------------------------------------------------------- #

def test_mark_is_the_sole_equity_curve_writer():
    acct = VirtualAccount(1000.0)
    acct.apply_fill(_buy(100.0, fee=0.0), quantity=1.0)  # no curve point recorded
    assert len(acct.equity_curve()) == 0
    acct.mark(TS, 100.0)
    assert len(acct.equity_curve()) == 1


def test_max_drawdown_matches_hand_computed_reference():
    # Buy 1 unit @100 (fee 0) so cash=900? no: start cash 100 -> cash 0, pos 1,
    # then equity(price) == price, giving a clean curve to reason about.
    acct = VirtualAccount(100.0)
    acct.apply_fill(_buy(100.0, fee=0.0), quantity=1.0)  # cash 0, pos 1
    for ts_offset, price in enumerate((100.0, 120.0, 90.0, 110.0)):
        acct.mark(TS + pd.Timedelta(days=ts_offset), price)
    curve = acct.equity_curve()
    assert list(curve.values) == pytest.approx([100.0, 120.0, 90.0, 110.0])
    # running max 120 at the trough of 90 -> (90-120)/120 = -0.25
    assert acct.max_drawdown() == pytest.approx(-0.25)


# --------------------------------------------------------------------------- #
# Over-trade rule (documented: reject with ValueError)
# --------------------------------------------------------------------------- #

def test_buying_beyond_cash_is_rejected():
    acct = VirtualAccount(100.0)
    with pytest.raises(ValueError):
        acct.apply_fill(_buy(100.0, fee=0.0), quantity=2.0)  # cost 200 > cash 100


def test_selling_more_than_held_is_rejected():
    acct = VirtualAccount(10000.0)
    acct.apply_fill(_buy(100.0, fee=0.0), quantity=1.0)
    with pytest.raises(ValueError):
        acct.apply_fill(_sell(100.0, fee=0.0), quantity=2.0)  # only 1 held


def test_max_drawdown_with_zero_peak_equity_does_not_raise():
    # An account started with zero cash and no position has a zero-equity peak;
    # drawdown is undefined there and must be skipped, not divide-by-zero.
    acct = VirtualAccount(0.0)
    acct.mark(TS, 0.0)
    acct.mark(TS + pd.Timedelta(days=1), 0.0)
    assert acct.max_drawdown() == 0.0
