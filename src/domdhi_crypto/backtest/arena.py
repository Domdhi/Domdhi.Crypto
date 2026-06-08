"""Local paper-trade arena engine for Domdhi.Crypto (E19-S2).

Purpose
-------
Orchestrate a head-to-head comparison of the cortex strategy against one or
more baselines (buy-and-hold and/or rule-driven strategies) over a shared
close+volume frame.  Returns equity curves, summary statistics, relative
performance (cortex total-return delta vs each baseline), and per-factor
attribution for the cortex.

Look-ahead discipline
---------------------
The cortex and every rule baseline are run through ``backtest.engine.run_backtest``,
which is the project's single look-ahead-safe event loop (time-gated DataProvider,
history_frame(T) truncation).  ``arena.py`` inherits that guarantee by delegation —
it does NOT re-derive signals or equity values itself.  Buy-and-hold is future-free
by construction: the value at bar k is ``initial_cash * close[k] / close[0]``, which
references only bars 0..k and is therefore consistent whether or not bars k+1..N
exist in the frame.

Leaf constraint (ADR-001 / acyclic import graph)
-------------------------------------------------
This module imports ONLY ``backtest.engine``, ``backtest.attribution``, ``pandas``,
and stdlib.  It must never import ``cli``, ``dashboard``, ``db``, ``ledger``,
``risk``, ``context``, or ``digest``.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import attribution, engine

# --------------------------------------------------------------------------- #
# Result dataclasses
# --------------------------------------------------------------------------- #

# eq=False is REQUIRED: StrategyResult carries a pd.Series (equity_curve), and
# ArenaResult transitively carries one through its StrategyResult fields. The
# auto-generated __eq__ on a frozen dataclass with a Series field raises
# "truth value of a Series is ambiguous" on any whole-instance comparison.
# Identity equality (the default when eq=False) is correct — no consumer
# compares StrategyResult/ArenaResult by value. Mirror of BacktestResult's
# decision (backtest/__init__.py, E18-S5).


@dataclass(frozen=True, eq=False)
class StrategyResult:
    """Outcome of a single strategy run over a price frame.

    Parameters
    ----------
    name:
        Human-readable strategy identifier (``"cortex"``, ``"buy_and_hold"``,
        or the rule's ``factor_name`` for rule baselines).
    equity_curve:
        Marked account value per bar (one point per bar), as returned by
        ``backtest.engine.run_backtest`` for rule strategies, or computed
        closed-form for buy-and-hold.
    summary:
        Dict with at minimum ``"total_return"``.
    """

    name: str
    equity_curve: pd.Series
    summary: dict


@dataclass(frozen=True, eq=False)
class ArenaResult:
    """Top-level output of a single arena run.

    Parameters
    ----------
    cortex:
        The primary strategy result.
    baselines:
        List whose first element is always ``buy_and_hold``, followed by one
        result per rule in ``baseline_rules`` (in list order).
    relative:
        ``{baseline.name: cortex.total_return - baseline.total_return}`` for
        every baseline in ``baselines``.
    attribution:
        Per-factor contribution dict from ``backtest.attribution.attribute_by_factor``
        applied to the cortex backtest result.
    """

    cortex: StrategyResult
    baselines: list[StrategyResult]
    relative: dict[str, float]
    attribution: dict[str, dict]


# --------------------------------------------------------------------------- #
# Buy-and-hold baseline
# --------------------------------------------------------------------------- #


def buy_and_hold(frame: pd.DataFrame, *, initial_cash: float = 10_000.0) -> StrategyResult:
    """Return a future-free buy-and-hold baseline over ``frame``.

    The equity curve at bar k is ``initial_cash * close[k] / close[0]``.
    This value depends only on ``close[0]`` (a constant) and ``close[k]``,
    so it is truncation-consistent: running on ``frame.iloc[:k+1]`` gives
    the same value as running on the full frame and reading index k.

    Parameters
    ----------
    frame:
        DataFrame with a ``close`` column and a DatetimeIndex.
    initial_cash:
        Starting notional in base currency.

    Returns
    -------
    StrategyResult
        ``name="buy_and_hold"``, equity curve indexed like ``frame``,
        summary with ``"total_return"`` only.
    """
    close = frame["close"]
    equity_curve: pd.Series = initial_cash * close / close.iloc[0]
    total_return = float(close.iloc[-1] / close.iloc[0] - 1.0)
    return StrategyResult(
        name="buy_and_hold",
        equity_curve=equity_curve,
        summary={"total_return": total_return},
    )


# --------------------------------------------------------------------------- #
# Arena entry point
# --------------------------------------------------------------------------- #


def run_arena(
    frame: pd.DataFrame,
    *,
    cortex_rules: list[engine.SignalRule],
    baseline_rules: list[engine.SignalRule] | None = None,
    initial_cash: float = 10_000.0,
    slippage_bps: float = 0.0,
    fee_rate: float = 0.0,
) -> ArenaResult:
    """Run cortex + baselines over ``frame`` and return a head-to-head ``ArenaResult``.

    Parameters
    ----------
    frame:
        Close+volume daily DataFrame, same format as accepted by
        ``backtest.engine.run_backtest``.
    cortex_rules:
        Ordered list of ``SignalRule`` objects for the primary (cortex) strategy.
    baseline_rules:
        Optional list of ``SignalRule`` objects.  Each rule is run as its own
        single-rule strategy (``[rule]``) and named by ``rule.factor_name``.
        Defaults to an empty list when ``None``.
    initial_cash:
        Starting cash for every strategy (cortex and all rule baselines).
        Buy-and-hold uses the same value to anchor its closed-form curve.
    slippage_bps:
        Slippage in basis points forwarded to ``engine.run_backtest``.
    fee_rate:
        Fee rate forwarded to ``engine.run_backtest``.

    Returns
    -------
    ArenaResult
        ``cortex``: faithful pass-through of ``engine.run_backtest(frame, cortex_rules, ...)``.
        ``baselines``: ``[buy_and_hold_result, *rule_baseline_results]``.
        ``relative``: ``{b.name: cortex.total_return - b.total_return}`` for each baseline.
        ``attribution``: ``attribution.attribute_by_factor(cortex_backtest_result)``.
    """
    if baseline_rules is None:
        baseline_rules = []

    # --- cortex ----------------------------------------------------------------
    cortex_bt = engine.run_backtest(
        frame,
        cortex_rules,
        initial_cash=initial_cash,
        slippage_bps=slippage_bps,
        fee_rate=fee_rate,
    )
    cortex_result = StrategyResult(
        name="cortex",
        equity_curve=cortex_bt.equity_curve,
        summary=cortex_bt.summary,
    )

    # --- baselines -------------------------------------------------------------
    bnh_result = buy_and_hold(frame, initial_cash=initial_cash)

    rule_baselines: list[StrategyResult] = []
    for rule in baseline_rules:
        r = engine.run_backtest(
            frame,
            [rule],
            initial_cash=initial_cash,
            slippage_bps=slippage_bps,
            fee_rate=fee_rate,
        )
        rule_baselines.append(
            StrategyResult(
                name=rule.factor_name,
                equity_curve=r.equity_curve,
                summary=r.summary,
            )
        )

    baselines: list[StrategyResult] = [bnh_result, *rule_baselines]

    # --- relative performance --------------------------------------------------
    cortex_tr: float = cortex_result.summary["total_return"]
    relative: dict[str, float] = {
        b.name: cortex_tr - b.summary["total_return"] for b in baselines
    }

    # --- per-factor attribution on the cortex result --------------------------
    attr: dict[str, dict] = attribution.attribute_by_factor(cortex_bt)

    return ArenaResult(
        cortex=cortex_result,
        baselines=baselines,
        relative=relative,
        attribution=attr,
    )
