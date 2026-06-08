"""Tests for the look-ahead-safe event backtest engine (backtest/engine.py).

The scenario is hand-computed and deterministic. Closes = [100, 110, 120, 90, 80]
over 5 daily bars; a single rule enters long when close > 105 and exits when
close < 95 (factor expression is the bare ``close`` column). With zero costs and
1000 starting cash this produces exactly ONE closed trade:

    enter day1 @110 (close>105), exit day3 @90 (close<95)
    realized_return = 90/110 - 1 = -0.181818...
    equity curve    = [1000, 1000, 1090.909, 818.18, 818.18]
    total_return    = 818.18/1000 - 1 = -0.181818...   (flat at end -> == realized)
    win_rate        = 0/1 = 0.0
    max_drawdown    = (818.18 - 1090.909)/1090.909 = -0.25

The three load-bearing properties asserted: the summary stats reference, the
truncation-invariance look-ahead guard (a past decision cannot change when future
bars are removed), and byte-stable determinism across re-runs.
"""
import pandas as pd
import pytest

from domdhi_crypto.backtest.engine import SignalRule, run_backtest

CLOSES = [100.0, 110.0, 120.0, 90.0, 80.0]


def _frame():
    idx = pd.date_range("2024-01-01", periods=len(CLOSES), freq="D")
    return pd.DataFrame({"close": CLOSES, "volume": [10.0] * len(CLOSES)}, index=idx)


def _rules():
    return [SignalRule(
        factor_name="px",
        expression="close",
        entry_threshold=105.0,
        exit_threshold=95.0,
    )]


def _key(t):
    return (t.entry_ts, t.exit_ts, round(t.realized_return, 9), t.triggering_factor)


# --------------------------------------------------------------------------- #
# Summary stats reference (hand-computed, zero costs)
# --------------------------------------------------------------------------- #

def test_single_trade_and_triggering_factor():
    res = run_backtest(_frame(), _rules(), initial_cash=1000.0)
    assert len(res.trades) == 1
    tr = res.trades[0]
    assert tr.triggering_factor == "px"
    assert tr.entry_ts == _frame().index[1]
    assert tr.exit_ts == _frame().index[3]
    assert tr.realized_return == pytest.approx(90.0 / 110.0 - 1.0, abs=1e-6)


def test_summary_reference():
    res = run_backtest(_frame(), _rules(), initial_cash=1000.0)
    s = res.summary
    assert s["total_realized_return"] == pytest.approx(90.0 / 110.0 - 1.0, abs=1e-6)
    assert s["total_return"] == pytest.approx(818.181818 / 1000.0 - 1.0, abs=1e-5)
    assert s["win_rate"] == pytest.approx(0.0)
    assert s["max_drawdown"] == pytest.approx(-0.25, abs=1e-6)


def test_equity_curve_exposed_on_result():
    """E18-S5 contract change: BacktestResult now carries the equity curve so the
    dashboard can chart it. One point per bar, matching the module's hand-computed
    reference [1000, 1000, 1090.909, 818.18, 818.18]."""
    res = run_backtest(_frame(), _rules(), initial_cash=1000.0)
    curve = res.equity_curve
    assert isinstance(curve, pd.Series)
    assert list(curve.index) == list(_frame().index), "one equity point per bar"
    assert curve.iloc[0] == pytest.approx(1000.0)
    assert curve.iloc[2] == pytest.approx(1090.909091, abs=1e-3)
    assert curve.iloc[-1] == pytest.approx(818.181818, abs=1e-3)


def test_costs_reduce_realized_return():
    no_cost = run_backtest(_frame(), _rules(), initial_cash=1000.0)
    with_cost = run_backtest(
        _frame(), _rules(), initial_cash=1000.0, slippage_bps=10.0, fee_rate=0.001
    )
    # slippage (buy higher, sell lower) + fees must make the same trade worse
    assert with_cost.trades[0].realized_return < no_cost.trades[0].realized_return


# --------------------------------------------------------------------------- #
# Look-ahead guard: truncation invariance
# --------------------------------------------------------------------------- #

def test_truncation_invariance_past_decisions_unchanged():
    frame = _frame()
    full = run_backtest(frame, _rules(), initial_cash=1000.0)
    # remove the future bar (day4); the day1 entry / day3 exit decision must not change
    trunc = run_backtest(frame.iloc[:4], _rules(), initial_cash=1000.0)
    assert [_key(t) for t in trunc.trades] == [_key(t) for t in full.trades]


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

def test_deterministic_across_reruns():
    frame = _frame()
    a = run_backtest(frame, _rules(), initial_cash=1000.0)
    b = run_backtest(frame, _rules(), initial_cash=1000.0)
    assert [_key(t) for t in a.trades] == [_key(t) for t in b.trades]
    assert a.summary == b.summary


# --------------------------------------------------------------------------- #
# A flat (never-triggered) run produces no trades and a clean summary
# --------------------------------------------------------------------------- #

def test_no_signal_produces_no_trades():
    frame = _frame()
    # entry threshold above every close -> never enters
    rules = [SignalRule(factor_name="px", expression="close",
                        entry_threshold=1e9, exit_threshold=0.0)]
    res = run_backtest(frame, rules, initial_cash=1000.0)
    assert res.trades == []
    assert res.summary["total_realized_return"] == pytest.approx(0.0)
    assert res.summary["win_rate"] == pytest.approx(0.0)
    # never deployed capital -> flat equity -> no drawdown
    assert res.summary["max_drawdown"] == pytest.approx(0.0)


def test_truncation_invariance_entry_decision_unchanged():
    """Stronger look-ahead guard: cut BETWEEN entry (day1) and exit (day3). The
    exit legitimately moves earlier (day2 flatten) because the real exit bar is
    gone — but the ENTRY decision at day1 must be identical whether or not the
    future bars (days 3-4) exist. That invariance is the no-look-ahead property."""
    frame = _frame()
    full = run_backtest(frame, _rules(), initial_cash=1000.0)
    mid = run_backtest(frame.iloc[:3], _rules(), initial_cash=1000.0)
    assert len(full.trades) == 1 and len(mid.trades) == 1
    assert mid.trades[0].entry_ts == full.trades[0].entry_ts == frame.index[1]


def test_all_in_buy_with_fees_does_not_overflow_cash():
    """Regression (review CRITICAL-1): an all-in buy with fee_rate > 0 must not
    trip VirtualAccount's cost>cash reject guard via a 1-ULP rounding overshoot.
    These exact cash/price values reproduced the abort before the loop-step fix."""
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    frame = pd.DataFrame(
        {"close": [23489.917842, 23000.0], "volume": [1.0, 1.0]}, index=idx
    )
    # entry fires bar0 (close>0); exit never fires (no positive close < -1), so the
    # position is closed only by the final-bar flatten -> exactly one trade.
    rules = [SignalRule(factor_name="px", expression="close",
                        entry_threshold=0.0, exit_threshold=-1.0)]
    res = run_backtest(frame, rules, initial_cash=9859464.167335, fee_rate=0.005)
    assert len(res.trades) == 1  # all-in buy executed and completed without ValueError


def test_columnless_expression_is_skipped_not_fatal():
    """Regression (review MAJOR-2): a column-less expression evaluates to a scalar
    with no .iloc; the rule must be skipped, not crash the run on AttributeError."""
    frame = _frame()
    rules = [SignalRule(factor_name="const", expression="1 + 1",
                        entry_threshold=0.0, exit_threshold=-1.0)]
    res = run_backtest(frame, rules, initial_cash=1000.0)
    assert res.trades == []  # rule skipped -> no signals -> no trades, run completes
