"""Look-ahead-safe event-loop backtest engine for Domdhi.Crypto (E13-S7).

Purpose
-------
Run a rule-driven long-only backtest over a close+volume daily frame, wiring
together the three Wave-2 leaf modules — DataProvider, VirtualAccount, and
ExecutionSimulator — under a single event loop that is free of look-ahead bias.

Look-ahead discipline
---------------------
At each bar T, the engine passes ``provider.history_frame(T)`` — a frame that
is exactly ``frame.loc[:T]`` — as the *only* frame ever handed to
``factors.evaluate``.  Future bars are structurally unreachable: this is enforced
by the truncation-invariance test, which verifies that a past decision (entry or
exit timestamp, realized_return) is identical whether or not bars after T exist in
the input frame.

Final-bar flatten
-----------------
Any position still open at the last bar is force-closed at that bar's close.
This guarantees that ``BacktestResult.trades`` contains only closed trades and
that ``summary["total_realized_return"]`` accounts for every position taken.

Long-only, single-position discipline
--------------------------------------
At most one position may be open at any time.  Exit logic is evaluated before
entry logic so a bar that triggers both signals closes first, then potentially
re-enters (though in practice the rules are designed to avoid that).

Net-of-cost realized_return
----------------------------
``realized_return`` is computed by the engine from the entry and exit fills it
routed.  The formula::

    realized_return = (qty * exit_fill_price - exit_fee) /
                      (qty * entry_fill_price + entry_fee) - 1.0

With zero slippage and zero fees this reduces to
``exit_close / entry_close - 1.0``.

Final-bar entry semantics (deliberate)
--------------------------------------
Entry is evaluated on every bar, INCLUDING the final one. If an entry fires on
the last bar it is opened and then immediately force-closed by the final-bar
flatten, producing a degenerate ``entry_ts == exit_ts`` trade with
``realized_return`` ~0 (zero cost) or slightly negative (round-trip fee). This is
intentional and load-bearing: suppressing entry on the final bar would make the
entry decision depend on whether future bars exist, which would *break*
truncation-invariance (the engine's central no-look-ahead guarantee). Such a
zero-holding trade still sums correctly into ``total_realized_return``, so
by-factor attribution (E13-S8) reconciles exactly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from domdhi_crypto.signals import factors

from . import BacktestResult, Bar, Fill, Order, Trade
from .data_provider import DataProvider
from .execution_simulator import simulate_fill
from .virtual_account import VirtualAccount

# --------------------------------------------------------------------------- #
# Signal rule
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SignalRule:
    """A declarative long-entry / long-exit rule based on a factor expression.

    Parameters
    ----------
    factor_name:
        Label stored in ``Trade.triggering_factor`` for attribution downstream.
    expression:
        A factor expression evaluated via ``factors.evaluate``.  Must reference
        only ``close`` / ``volume`` columns and functions in the factor registry.
    entry_threshold:
        Enter long when the factor value at T **strictly exceeds** this threshold.
    exit_threshold:
        Exit long when the factor value at T **strictly falls below** this threshold.
    """

    factor_name: str
    expression: str
    entry_threshold: float
    exit_threshold: float


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def run_backtest(
    frame: pd.DataFrame,
    rules: list[SignalRule],
    *,
    initial_cash: float = 10_000.0,
    slippage_bps: float = 0.0,
    fee_rate: float = 0.0,
) -> BacktestResult:
    """Run a look-ahead-safe event-loop backtest and return a ``BacktestResult``.

    Parameters
    ----------
    frame:
        A ``pd.DataFrame`` with a ``DatetimeIndex`` and at minimum ``close`` and
        ``volume`` columns, as returned by ``db.load_close_series``.
    rules:
        Ordered list of ``SignalRule`` objects.  Entry uses the first rule whose
        signal fires (deterministic: list order governs precedence).  Exit uses
        the rule that originally opened the trade.
    initial_cash:
        Starting cash balance for the virtual account.
    slippage_bps:
        Slippage in basis points applied by the execution simulator (adverse to
        side: buys fill higher, sells fill lower).
    fee_rate:
        Fee as a plain fraction of notional (e.g. ``0.001`` = 0.1%).

    Returns
    -------
    BacktestResult
        Contains the list of closed ``Trade`` objects and a ``summary`` dict
        with keys ``total_return``, ``total_realized_return``, ``win_rate``, and
        ``max_drawdown``.
    """
    provider = DataProvider(frame)
    account = VirtualAccount(initial_cash)
    trades: list[Trade] = []

    # open_trade holds entry state while a position is live; None when flat.
    open_trade: dict | None = None

    timestamps = provider.timestamps()
    n_bars = len(timestamps)

    for bar_idx, bar in enumerate(provider):
        T: pd.Timestamp = bar.timestamp
        is_final_bar = bar_idx == n_bars - 1

        # ------------------------------------------------------------------ #
        # Step 1 — look-ahead-safe history frame (the ONLY frame for evaluate)
        # ------------------------------------------------------------------ #
        frame_T = provider.history_frame(T)

        # ------------------------------------------------------------------ #
        # Step 2 — compute each rule's factor value at T
        # ------------------------------------------------------------------ #
        rule_values: dict[int, float] = {}
        for idx, rule in enumerate(rules):
            try:
                series = factors.evaluate(rule.expression, frame_T)
            except (ValueError, IndexError):
                continue
            # A column-less expression (e.g. "1+1") evaluates to a plain scalar with
            # no ``.iloc`` — skip the rule rather than crashing the whole run on
            # AttributeError. A malformed rule is non-fatal to the other rules.
            if not hasattr(series, "iloc"):
                continue
            value = float(series.iloc[-1])
            if math.isnan(value):
                continue
            rule_values[idx] = value

        # ------------------------------------------------------------------ #
        # Step 3 — EXIT: close open position if exit signal fires
        # ------------------------------------------------------------------ #
        if open_trade is not None:
            triggering_rule: SignalRule = open_trade["rule"]
            rule_idx: int = open_trade["rule_idx"]
            exit_value = rule_values.get(rule_idx)
            if exit_value is not None and exit_value < triggering_rule.exit_threshold:
                open_trade = _close_position(
                    open_trade, bar, T, account, trades, slippage_bps, fee_rate
                )

        # ------------------------------------------------------------------ #
        # Step 4 — ENTRY: open a position if flat and a rule signals
        # ------------------------------------------------------------------ #
        if open_trade is None:
            for idx, rule in enumerate(rules):
                value = rule_values.get(idx)
                if value is not None and value > rule.entry_threshold:
                    open_trade = _open_position(
                        idx, rule, bar, T, account, slippage_bps, fee_rate
                    )
                    break  # first matching rule wins; long-only single position

        # ------------------------------------------------------------------ #
        # Step 5 — FINAL BAR: force-close any remaining open position
        # ------------------------------------------------------------------ #
        if is_final_bar and open_trade is not None:
            open_trade = _close_position(
                open_trade, bar, T, account, trades, slippage_bps, fee_rate
            )

        # ------------------------------------------------------------------ #
        # Step 6 — mark equity curve (once per bar, after all fills)
        # ------------------------------------------------------------------ #
        account.mark(T, bar.close)

    # --------------------------------------------------------------------------- #
    # Build summary
    # --------------------------------------------------------------------------- #
    curve = account.equity_curve()
    if len(curve) > 0 and curve.iloc[0] != 0.0:
        total_return = float((curve.iloc[-1] - curve.iloc[0]) / curve.iloc[0])
    else:
        total_return = 0.0

    total_realized_return = sum((t.realized_return for t in trades), 0.0)

    if trades:
        win_rate = sum(1 for t in trades if t.realized_return > 0) / len(trades)
    else:
        win_rate = 0.0

    max_drawdown = account.max_drawdown()

    summary = {
        "total_return": total_return,
        "total_realized_return": total_realized_return,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
    }
    return BacktestResult(trades=trades, summary=summary, equity_curve=curve)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _open_position(
    rule_idx: int,
    rule: SignalRule,
    bar: Bar,
    T: pd.Timestamp,
    account: VirtualAccount,
    slippage_bps: float,
    fee_rate: float,
) -> dict:
    """Execute an all-in buy and return the open-trade state dict.

    Sizing: with ``notional = cash / (1 + fee_rate)`` the total cash outflow
    ``qty * fill.price + fee`` (where ``fee = fee_rate * notional`` and
    ``qty = notional / fill.price``) equals ``cash`` in *exact* arithmetic. Under
    IEEE-754 the independent rounding of the fee term and the final sum can push
    the total one or more ULPs above ``cash``, which the ``VirtualAccount`` guard
    rejects (``cost > cash``) and aborts the run. A single ``nextafter`` on ``qty``
    cannot bound an error introduced *after* ``qty`` in the sum, so we step ``qty``
    down in a loop against the **actual** total-cost inequality until it fits. The
    step is at most a few ULPs and ``qty`` cancels in the realized-return ratio, so
    this does not materially under-deploy capital or perturb the trade return.
    """
    notional = account.cash / (1.0 + fee_rate) if fee_rate != 0.0 else account.cash
    order = Order(timestamp=T, side="buy", notional=notional)
    fill: Fill = simulate_fill(order, bar, slippage_bps, fee_rate)
    qty = notional / fill.price
    # Loop the down-step against the real cost sum (not blindly once on qty).
    while qty > 0.0 and qty * fill.price + fill.fee > account.cash:
        qty = math.nextafter(qty, 0.0)
    account.apply_fill(fill, qty)
    return {
        "entry_ts": T,
        "entry_fill_price": fill.price,
        "entry_fee": fill.fee,
        "qty": qty,
        "rule": rule,
        "rule_idx": rule_idx,
    }


def _close_position(
    open_trade: dict,
    bar: Bar,
    T: pd.Timestamp,
    account: VirtualAccount,
    trades: list[Trade],
    slippage_bps: float,
    fee_rate: float,
) -> None:
    """Execute a sell, record the closed Trade, and return None (position closed)."""
    qty: float = open_trade["qty"]
    entry_fill_price: float = open_trade["entry_fill_price"]
    entry_fee: float = open_trade["entry_fee"]
    entry_ts: pd.Timestamp = open_trade["entry_ts"]
    rule: SignalRule = open_trade["rule"]

    order = Order(timestamp=T, side="sell", notional=qty * bar.close)
    fill: Fill = simulate_fill(order, bar, slippage_bps, fee_rate)
    account.apply_fill(fill, qty)

    entry_cost_basis = qty * entry_fill_price + entry_fee
    exit_proceeds_net = qty * fill.price - fill.fee
    realized_return = exit_proceeds_net / entry_cost_basis - 1.0

    trades.append(Trade(
        entry_ts=entry_ts,
        exit_ts=T,
        realized_return=realized_return,
        triggering_factor=rule.factor_name,
    ))
    return None
