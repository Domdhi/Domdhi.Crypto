"""Tests for by-factor attribution (backtest/attribution.py).

Attribution groups a completed BacktestResult's trades by Trade.triggering_factor
and reports per-factor contribution. The integrity guard is reconciliation: the
sum of per-factor total_return must equal BacktestResult.summary
["total_realized_return"] (the sum of CLOSED-trade returns — NOT the equity-curve
"total_return", which includes unrealized P&L) within 1e-6. This is exact only
because the engine flattens all open positions at the final bar.
"""
import pandas as pd
import pytest

from domdhi_crypto.backtest import BacktestResult, Trade
from domdhi_crypto.backtest.attribution import attribute_by_factor
from domdhi_crypto.backtest.engine import SignalRule, run_backtest

D = pd.date_range("2024-01-01", periods=5, freq="D")


def _result():
    """Hand-built result: factor A has 2 trades (+0.10, -0.05), factor B has 1 (+0.20)."""
    trades = [
        Trade(entry_ts=D[0], exit_ts=D[1], realized_return=0.10, triggering_factor="A"),
        Trade(entry_ts=D[1], exit_ts=D[2], realized_return=-0.05, triggering_factor="A"),
        Trade(entry_ts=D[2], exit_ts=D[3], realized_return=0.20, triggering_factor="B"),
    ]
    summary = {
        "total_return": 0.25,
        "total_realized_return": 0.25,  # 0.10 - 0.05 + 0.20
        "win_rate": 2 / 3,
        "max_drawdown": -0.05,
    }
    return BacktestResult(trades=trades, summary=summary)


# --------------------------------------------------------------------------- #
# Grouping + per-factor stats
# --------------------------------------------------------------------------- #

def test_groups_by_triggering_factor():
    attr = attribute_by_factor(_result())
    assert set(attr) == {"A", "B"}
    assert attr["A"]["n_trades"] == 2
    assert attr["B"]["n_trades"] == 1


def test_per_factor_stats_reference():
    attr = attribute_by_factor(_result())
    assert attr["A"]["total_return"] == pytest.approx(0.05)   # 0.10 - 0.05
    assert attr["A"]["mean_return"] == pytest.approx(0.025)   # 0.05 / 2
    assert attr["A"]["win_rate"] == pytest.approx(0.5)        # 1 win of 2
    assert attr["B"]["total_return"] == pytest.approx(0.20)
    assert attr["B"]["mean_return"] == pytest.approx(0.20)
    assert attr["B"]["win_rate"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Reconciliation (the integrity guard)
# --------------------------------------------------------------------------- #

def test_reconciles_to_total_realized_return():
    res = _result()
    attr = attribute_by_factor(res)
    total = sum(v["total_return"] for v in attr.values())
    assert total == pytest.approx(res.summary["total_realized_return"], abs=1e-6)


def test_reconciles_with_a_real_backtest():
    """End-to-end: the sum of per-factor totals matches the engine's summary,
    exact because the engine flattens open positions at the final bar."""
    frame = pd.DataFrame(
        {"close": [100.0, 110.0, 120.0, 90.0, 80.0], "volume": [10.0] * 5}, index=D
    )
    rules = [SignalRule(factor_name="px", expression="close",
                        entry_threshold=105.0, exit_threshold=95.0)]
    res = run_backtest(frame, rules, initial_cash=1000.0)
    attr = attribute_by_factor(res)
    total = sum(v["total_return"] for v in attr.values())
    assert total == pytest.approx(res.summary["total_realized_return"], abs=1e-6)


# --------------------------------------------------------------------------- #
# Documented rules: no-trade factor absent, empty result
# --------------------------------------------------------------------------- #

def test_factor_with_no_trades_is_absent():
    attr = attribute_by_factor(_result())
    assert "C" not in attr  # only factors that triggered >= 1 trade appear


def test_empty_result_returns_empty_dict_without_error():
    res = BacktestResult(
        trades=[],
        summary={"total_return": 0.0, "total_realized_return": 0.0,
                 "win_rate": 0.0, "max_drawdown": 0.0},
    )
    assert attribute_by_factor(res) == {}
