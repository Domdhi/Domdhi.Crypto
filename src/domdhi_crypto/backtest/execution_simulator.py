"""Execution simulator: converts an ``Order`` + executing ``Bar`` into a ``Fill``.

This module applies a configurable cost model to a bar close price before returning
a confirmed fill. Two cost components are modelled:

- **Slippage** — adverse to the order side (the standard convention): a buy fills
  *above* the bar close; a sell fills *below* it. Slippage is expressed in basis
  points (1 bp = 0.01%). ``slippage_bps=50`` → 0.5% adverse price shift.
- **Fee** — a flat fraction of the notional (e.g. ``fee_rate=0.001`` = 10 bps).
  Always a non-negative cost regardless of side.

Setting ``slippage_bps=0.0`` and ``fee_rate=0.0`` reproduces the bar close exactly
with zero fee — the cost model is purely additive and fully disable-able.

Units summary
~~~~~~~~~~~~~
- ``slippage_bps`` : float — slippage in basis points; divide by 10 000 to get a
  fraction. Pass ``0.0`` to disable.
- ``fee_rate``     : float — fee as a plain fraction (e.g. ``0.001`` = 0.1%).
  Pass ``0.0`` to disable.

This module is a deliberate *leaf* over the backtest types only: it imports from
``backtest/__init__.py`` and nothing else — no db, no factors, no pandas beyond what
the frozen dataclasses already carry.
"""
from . import Bar, Fill, Order

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def simulate_fill(
    order: Order,
    bar: Bar,
    slippage_bps: float = 0.0,
    fee_rate: float = 0.0,
) -> Fill:
    """Simulate the execution of *order* against *bar* and return a ``Fill``.

    Parameters
    ----------
    order:
        The trade instruction. ``order.side`` must be ``"buy"`` or ``"sell"``.
        ``order.notional`` is the gross cash amount before costs.
    bar:
        The bar on which the order is executed. Only ``bar.close`` and
        ``bar.timestamp`` are consumed.
    slippage_bps:
        Slippage in basis points. Converted internally via
        ``slip = slippage_bps / 10_000``. BUY fills at
        ``bar.close * (1 + slip)``; SELL fills at ``bar.close * (1 - slip)``.
        Default ``0.0`` (no slippage).
    fee_rate:
        Fee as a plain fraction of notional (e.g. ``0.001`` = 10 bps).
        ``fee = fee_rate * order.notional``. Always >= 0 regardless of side.
        Default ``0.0`` (no fee).

    Returns
    -------
    Fill
        A frozen dataclass carrying ``timestamp``, ``price``, ``fee``, and
        ``side`` mirroring the originating order.
    """
    slip = slippage_bps / 10_000

    if order.side == "buy":
        price = bar.close * (1 + slip)
    else:
        price = bar.close * (1 - slip)

    fee = fee_rate * order.notional

    return Fill(
        timestamp=bar.timestamp,
        price=price,
        fee=fee,
        side=order.side,
    )
