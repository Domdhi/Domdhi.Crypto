"""By-factor attribution for a completed BacktestResult.

Groups every closed ``Trade`` by ``Trade.triggering_factor`` and reports
per-factor contribution: trade count, total/mean ``realized_return``, and win
rate.

Integrity guarantee: the sum of per-factor ``total_return`` values reconciles to
``BacktestResult.summary["total_realized_return"]`` (the sum of closed-trade
returns — NOT the equity-curve ``total_return``, which includes unrealised P&L)
within 1e-6. This holds exactly because every trade is counted exactly once and
the engine flattens all open positions at the final bar before producing the
result, so every position is a closed trade.

Documented rule — no-trade-factor absent: factors that triggered zero trades are
ABSENT from the returned dict. An empty ``BacktestResult`` returns an empty dict
without error.

This module is a pure leaf: it imports only from the backtest package's own type
contract and uses stdlib aggregation — no numpy, no pandas, no db.
"""

from . import BacktestResult

# --------------------------------------------------------------------------- #
# Attribution
# --------------------------------------------------------------------------- #


def attribute_by_factor(result: BacktestResult) -> dict[str, dict]:
    """Return per-factor contribution grouped by ``Trade.triggering_factor``.

    Each key in the returned dict is a factor name; each value is a dict with
    EXACTLY these keys:

    - ``"n_trades"``    (int)   — number of trades triggered by this factor.
    - ``"total_return"`` (float) — sum of ``realized_return`` for this factor.
    - ``"mean_return"``  (float) — ``total_return / n_trades``.
    - ``"win_rate"``     (float) — fraction of trades with ``realized_return > 0``.

    Factors with zero trades are absent from the result. An empty
    ``result.trades`` list returns ``{}``.
    """
    groups: dict[str, list[float]] = {}
    for trade in result.trades:
        groups.setdefault(trade.triggering_factor, []).append(trade.realized_return)

    out: dict[str, dict] = {}
    for factor, returns in groups.items():
        n = len(returns)
        total = sum(returns)
        out[factor] = {
            "n_trades": n,
            "total_return": total,
            "mean_return": total / n,
            "win_rate": sum(1 for r in returns if r > 0) / n,
        }
    return out
