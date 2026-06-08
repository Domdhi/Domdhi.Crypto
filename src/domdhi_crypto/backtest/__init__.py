"""Shared frozen dataclasses: the cross-module type contract for the look-ahead-safe
backtester (Epic 13).

Every backtest module — data provider, virtual account, execution simulator, engine,
and attribution — imports from here and nowhere else within the package. Field names
are a HARD contract: renaming any field here cascades silently across all consumers,
so changes require deliberate coordination and a matching test update.

Scope decision (load-bearing): the backtester operates on ``db.load_close_series``
daily bars only — NOT ``load_ohlc``, which is a separate table at a different time
granularity. A ``Bar`` therefore carries ``close`` and ``volume`` only; there is no
``high`` or ``low`` field. This is not an omission — it reflects the real data
boundary. Factors that need OHLC data are deferred (see ``factors.DEFERRED_FACTORS``).

``BacktestResult.summary`` runtime convention (dict keys, not dataclass fields):

- ``total_return``: equity-curve total return, including any open/unrealised position.
- ``total_realized_return``: sum of ``realized_return`` across all closed ``Trade``
  objects; excludes unrealised P&L.
- ``win_rate``: fraction of trades with ``realized_return > 0``.
- ``max_drawdown``: peak-to-trough drawdown of the equity curve (a negative float).

ADR-001 governs this module: **pure stdlib + pandas only** — no numpy, no internal
sibling backtest imports. This module is a deliberate *leaf* at the base of the
backtest package's internal dependency graph. It must stay importable with zero
side-effects so any consumer can load it independently.
"""
from dataclasses import dataclass, field

import pandas as pd

# --------------------------------------------------------------------------- #
# Market data
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Bar:
    """A single daily close+volume bar from ``db.load_close_series``.

    ``high`` and ``low`` are intentionally absent — the close+volume daily series
    is the only time base the backtester operates on (see module docstring).
    """

    timestamp: pd.Timestamp
    close: float
    volume: float


# --------------------------------------------------------------------------- #
# Order and fill
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Order:
    """A trade instruction emitted by the engine.

    ``side`` is ``"buy"`` or ``"sell"``.
    ``notional`` is the nominal cash amount to deploy (before fee/slippage).
    """

    timestamp: pd.Timestamp
    side: str
    notional: float


@dataclass(frozen=True)
class Fill:
    """A confirmed execution returned by the simulator.

    ``price`` is the post-slippage fill price (not the bar close).
    ``fee`` is the absolute fee charged in the account's base currency.
    ``side`` mirrors the originating ``Order.side``.
    """

    timestamp: pd.Timestamp
    price: float
    fee: float
    side: str


# --------------------------------------------------------------------------- #
# Trade and result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Trade:
    """A completed round-trip position (entry fill → exit fill).

    ``realized_return`` is the fractional return after fees, i.e.
    ``(exit_price - entry_price) / entry_price - fees_fraction``.
    ``triggering_factor`` is the ``name`` field of the ``FactorFunction`` whose
    signal opened the trade, enabling per-factor attribution downstream.
    """

    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    realized_return: float
    triggering_factor: str

    @property
    def holding_period(self) -> pd.Timedelta:
        """Duration between entry and exit as a ``pd.Timedelta``."""
        return self.exit_ts - self.entry_ts


# eq=False: the ``equity_curve`` Series makes the auto-generated ``__eq__`` raise
# "truth value of a Series is ambiguous" on whole-instance comparison. No consumer
# compares BacktestResult by value (the determinism test compares ``.summary``), so
# identity equality is correct and avoids a latent crash (E18-S5).
@dataclass(frozen=True, eq=False)
class BacktestResult:
    """Top-level output of a completed backtest run.

    ``trades`` is the ordered list of all closed ``Trade`` objects.
    ``summary`` is a plain dict carrying at minimum the keys documented in the
    module docstring: ``total_return``, ``total_realized_return``, ``win_rate``,
    ``max_drawdown``. Additional engine-specific keys are allowed.
    ``equity_curve`` is the marked account value per bar (one point per bar),
    exposed so consumers (e.g. the dashboard, E18-S5) can chart it. It defaults to
    an empty Series, keeping the field backward-compatible for the two-arg
    ``BacktestResult(trades=..., summary=...)`` construction used in tests.
    """

    trades: list[Trade]
    summary: dict
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
