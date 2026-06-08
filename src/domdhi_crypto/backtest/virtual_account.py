"""Virtual account for the Domdhi.Crypto backtester (E13-S5).

Tracks cash, position, and equity through a sequence of ``Fill`` objects.  Each
``apply_fill`` call mutates the account's cash and position but does **not**
record an equity-curve point — that is the caller's responsibility.

Contract: ``mark()`` is the SOLE equity-curve writer.
    The engine calls ``mark(timestamp, price)`` once per bar, after any fills for
    that bar have been applied.  This separation ensures every bar appears on the
    equity curve exactly once regardless of whether a fill occurred; bars with no
    fill would be silently absent if ``apply_fill`` recorded curve points.

Realized P/L contract (gross of fees):
    ``realized_pnl()`` accumulates ``quantity * (fill_price - avg_cost)`` for each
    sell.  Fees are deducted directly from ``cash`` during both buys and sells —
    they are not embedded in realized P/L.  This means ``realized_pnl`` measures
    the gross trading edge while ``cash`` (and therefore ``equity``) reflects the
    actual net position including fees.

Rejection rules (ValueError, not clamp):
    BUY  — rejected when ``quantity * price + fee > cash``.
    SELL — rejected when ``quantity > position``.

Leaf-import constraint (ADR-001): imports only ``pandas`` and the backtest
package's own types — no ``db``, no ``numpy``, no other internal modules.
"""
import pandas as pd

from . import Fill

# --------------------------------------------------------------------------- #
# Virtual account
# --------------------------------------------------------------------------- #


class VirtualAccount:
    """A bookkeeping ledger that simulates a single-asset margin-free account.

    Parameters
    ----------
    cash:
        Starting cash balance in the account's base currency.
    """

    def __init__(self, cash: float) -> None:
        self.cash: float = cash
        self.position: float = 0.0
        self._avg_cost: float = 0.0
        self._realized_pnl: float = 0.0
        self._curve_timestamps: list[pd.Timestamp] = []
        self._curve_values: list[float] = []

    # ----------------------------------------------------------------------- #
    # Core accounting
    # ----------------------------------------------------------------------- #

    def apply_fill(self, fill: Fill, quantity: float) -> None:
        """Apply a confirmed fill to the account.

        Parameters
        ----------
        fill:
            The ``Fill`` returned by the execution simulator.  Carries price,
            fee, and side; does NOT carry quantity (that is supplied explicitly).
        quantity:
            Units to buy or sell.  Must be positive.

        Raises
        ------
        ValueError
            BUY: when the total cost (notional + fee) exceeds available cash.
            SELL: when the requested quantity exceeds the current position.
        """
        if fill.side == "buy":
            cost = quantity * fill.price + fill.fee
            if cost > self.cash:
                raise ValueError(
                    f"Insufficient cash: need {cost:.6f}, have {self.cash:.6f}. "
                    "Buy rejected — do not clamp."
                )
            # Update average cost before adjusting position
            if self.position + quantity > 0:
                self._avg_cost = (
                    self.position * self._avg_cost + quantity * fill.price
                ) / (self.position + quantity)
            self.cash -= cost
            self.position += quantity

        elif fill.side == "sell":
            if quantity > self.position:
                raise ValueError(
                    f"Insufficient position: need {quantity:.6f}, hold {self.position:.6f}. "
                    "Sell rejected — do not clamp."
                )
            self._realized_pnl += quantity * (fill.price - self._avg_cost)
            self.cash += quantity * fill.price - fill.fee
            self.position -= quantity
            if self.position == 0.0:
                self._avg_cost = 0.0

        else:
            raise ValueError(f"Unknown fill side: {fill.side!r}. Expected 'buy' or 'sell'.")

    # ----------------------------------------------------------------------- #
    # Equity
    # ----------------------------------------------------------------------- #

    def equity(self, mark_price: float) -> float:
        """Return current account equity at the given mark price.

        Parameters
        ----------
        mark_price:
            Current market price used to value the open position.

        Returns
        -------
        float
            ``cash + position * mark_price``.
        """
        return self.cash + self.position * mark_price

    # ----------------------------------------------------------------------- #
    # Equity curve
    # ----------------------------------------------------------------------- #

    def mark(self, timestamp: pd.Timestamp, price: float) -> None:
        """Append one equity-curve point at the given timestamp and price.

        This is the SOLE writer of the equity curve.  The engine must call this
        once per bar; ``apply_fill`` never writes to the curve.

        Parameters
        ----------
        timestamp:
            Bar timestamp that will index this curve point.
        price:
            Mark price used to compute ``equity(price)`` for this bar.
        """
        self._curve_timestamps.append(timestamp)
        self._curve_values.append(self.equity(price))

    def equity_curve(self) -> pd.Series:
        """Return the recorded equity curve as a ``pd.Series``.

        Returns
        -------
        pd.Series
            Indexed by the timestamps passed to ``mark()``.  Empty (length 0)
            before the first ``mark()`` call.
        """
        if not self._curve_timestamps:
            return pd.Series(dtype=float)
        return pd.Series(self._curve_values, index=self._curve_timestamps, dtype=float)

    def max_drawdown(self) -> float:
        """Return the maximum peak-to-trough drawdown of the equity curve.

        Computed as the minimum value of ``(equity - running_max) / running_max``
        over all recorded curve points.  A value <= 0 by construction.

        Drawdown is undefined while the running peak equity is non-positive
        (e.g. an account started with zero cash), so those points are skipped
        rather than dividing by zero.

        Returns
        -------
        float
            Maximum drawdown fraction, or 0.0 if the curve has no points.
        """
        curve = self._curve_values
        if not curve:
            return 0.0
        running_max = curve[0]
        min_dd = 0.0
        for eq in curve:
            if eq > running_max:
                running_max = eq
            if running_max <= 0:
                continue
            dd = (eq - running_max) / running_max
            if dd < min_dd:
                min_dd = dd
        return min_dd

    # ----------------------------------------------------------------------- #
    # P/L
    # ----------------------------------------------------------------------- #

    def realized_pnl(self) -> float:
        """Return cumulative realized P/L, gross of fees.

        Each closed unit contributes ``quantity * (fill_price - avg_cost)``
        at the time of the sell fill.  Fees are NOT embedded here — they are
        deducted from ``cash`` directly, so ``equity`` is net of fees while
        this figure measures the raw trading edge.

        Returns
        -------
        float
            Cumulative realized P/L in base-currency units.
        """
        return self._realized_pnl

    def unrealized_pnl(self, mark_price: float) -> float:
        """Return unrealized P/L on the current open position.

        Parameters
        ----------
        mark_price:
            Current market price used to value the position.

        Returns
        -------
        float
            ``position * (mark_price - avg_cost)``.  Zero when position is flat.
        """
        return self.position * (mark_price - self._avg_cost)
