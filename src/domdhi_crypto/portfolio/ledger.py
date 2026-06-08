"""Thin portfolio ledger — NAV-over-time + average-cost P/L (Epic 16, E16-S2).

Position context to weight decisions, NOT a tax tracker or rebalancer. Like
``context.build_context`` / ``digest.build_digest`` these are PURE functions: the
caller injects an open ``conn`` (+ ``coins_cfg``); nothing here calls
``db.connect()`` or loads ``coins.local.json`` itself (Epic-14 pure-vs-IO split).

NAV source (deliberate deviation from the backlog's "from snapshots" wording):
``snapshots`` are sparse (one row per ingest run), so a meaningful NAV time-series
derives from the *daily* ``prices`` close series × holdings — ``db.load_close_series``
already gap-fills to a continuous daily index. Stable coins carry no price history,
so they contribute a constant ``amount * (latest_snapshot_price or 1)`` across the range.

P/L is average-cost (matching ``context._build_position``'s avg-entry model), fee-aware:
  buy : total_cost += amount*price + fee ;            total_amount += amount
  sell: avg = total_cost / total_amount
        realized += amount*price - amount*avg - fee
        total_cost -= amount*avg ;                     total_amount -= amount
Realized P/L sums matched sells; unrealized values the remaining open position at
``db.latest_snapshot_price`` minus its average cost. Every returned float is
finite-guarded with ``math.isfinite`` (memory ``json-safety-isnan-misses-infinity``).
"""
import math

import pandas as pd

from domdhi_crypto.shared import db


def nav_series(conn, coins_cfg):
    """Daily portfolio NAV as a dated ``pd.Series``.

    NAV(date) = sum over coins of ``amount * close(date)``; stables add a constant
    ``amount * (latest_snapshot_price or 1)``. The index is the union of the
    non-stable coins' daily close ranges. Returns an empty Series (never raises)
    when no priced holding has data.

    Leading-gap behavior (known, accepted): coins are outer-joined on date and
    forward-filled, so a coin with a SHORTER price history has leading NaNs that
    ``sum(skipna=True)`` treats as 0 — early NAV reflects only the coins that
    already have data, and stepping in a later-listed coin shows as a jump on its
    first date. This understates the very earliest NAV but keeps the series
    continuous; callers wanting a fully-populated curve should align ingest ranges.
    """
    coins = coins_cfg.get("coins", [])

    # Non-stable contributions: holding amount * continuous daily close.
    contribs = {}
    for c in coins:
        if c.get("stable", False):
            continue
        frame = db.load_close_series(conn, c["id"])
        if frame is None:
            continue
        amount = c.get("amount", 0.0) or 0.0
        contribs[c["id"]] = frame["close"] * amount

    if not contribs:
        return pd.Series(dtype=float)

    # Align on the union of dates; ffill so a shorter-history coin holds its last
    # known value rather than dropping the whole row to NaN.
    matrix = pd.DataFrame(contribs).sort_index().ffill()
    nav = matrix.sum(axis=1)

    # Stable coins: constant value across the range (no price history).
    stable_value = 0.0
    for c in coins:
        if not c.get("stable", False):
            continue
        amount = c.get("amount", 0.0) or 0.0
        price = db.latest_snapshot_price(conn, c["id"])
        if price is None or not math.isfinite(price):
            price = 1.0
        stable_value += amount * price
    if stable_value:
        nav = nav + stable_value

    # Drop any non-finite point so the series is clean for downstream math.
    return nav[nav.map(math.isfinite)]


def _replay(rows):
    """Average-cost replay of ordered transaction rows.

    Returns ``(realized, open_amount, avg_cost)``. Buy fees fold into cost basis;
    sell fees reduce realized proceeds.

    Thin-ledger boundaries (INTENTIONAL — this is position context, not a
    validating tax engine; input sanity is the user's responsibility):
    - **Oversell is clamped, not rejected.** Selling more than is held computes
      realized P/L on the sold amount at the current average, then resets the
      position to flat (never negative). A fat-finger ``sell`` silently absorbs
      rather than raising — neither ``_replay`` nor ``insert_transaction``
      validates sequence sanity. (See ``test_oversell_clamps_to_flat``.)
    - **A leading sell with no prior buy** uses ``avg = 0`` (free cost basis), so
      its proceeds count as pure realized gain. (See ``test_leading_sell_uses_zero_basis``.)
    Validating transaction sequences is deferred (a future story), by design.
    """
    total_amount = 0.0
    total_cost = 0.0
    realized = 0.0
    for r in rows:
        side = r["side"]
        amount = r["amount"] or 0.0
        price = r["price"] or 0.0
        fee = r["fee"] or 0.0
        if side == "buy":
            total_cost += amount * price + fee
            total_amount += amount
        elif side == "sell":
            avg = (total_cost / total_amount) if total_amount > 0 else 0.0
            realized += amount * price - amount * avg - fee
            total_cost -= amount * avg
            total_amount -= amount
            if total_amount <= 0:  # fully (or over-) closed: reset basis cleanly
                total_amount = 0.0
                total_cost = 0.0
    avg_cost = (total_cost / total_amount) if total_amount > 0 else 0.0
    return realized, total_amount, avg_cost


def _coin_ids(conn, coins_cfg):
    """Non-stable coin ids to evaluate — from coins_cfg when given, else every
    coin that has a transaction.

    Note the asymmetry with ``unrealized_pl``, which always skips stables:
    ``realized_pl(conn)`` (no cfg) replays EVERY transacted coin, stables
    included. This is intentional — a recorded stable trade has real realized
    P/L (≈0 at price ~1), whereas a stable has no meaningful *unrealized* gain.
    Pass ``coins_cfg`` to scope realized P/L to non-stable holdings."""
    if coins_cfg:
        return [c["id"] for c in coins_cfg.get("coins", []) if not c.get("stable", False)]
    rows = conn.execute("SELECT DISTINCT coin_id FROM transactions").fetchall()
    return [r["coin_id"] for r in rows]


def realized_pl(conn, coins_cfg=None):
    """Total realized P/L (average-cost) across all transacted coins."""
    total = 0.0
    for cid in _coin_ids(conn, coins_cfg):
        realized, _, _ = _replay(db.load_transactions(conn, cid))
        if math.isfinite(realized):
            total += realized
    return total


def validate_transactions(rows) -> list[str]:
    """Optional, opt-in checker that walks an ordered transaction sequence and
    returns a list of human-readable problem strings (empty = coherent).

    Does NOT modify ``_replay`` behaviour or any P/L function — it is a pure
    read-only pass over the same rows. Two violation types are detected,
    per-coin:

    - **Leading sell**: first event for a coin is a sell (no prior buy at all).
      Message: ``"leading sell at {ts} for {coin_id}: sell of {amount} with no prior buy"``.
    - **Oversell**: a sell whose amount exceeds the current running held qty
      (the coin has prior buys, but not enough to cover this sell).
      Message: ``"oversell at {ts} for {coin_id}: tried to sell {amount} but only {qty} held"``.

    After each row the running qty is updated with the same clamp as ``_replay``
    (``max(0.0, qty - amount)``) so subsequent rows are checked against a
    non-negative balance, matching the flat-reset behaviour callers rely on.
    """
    holdings: dict[str, float] = {}   # coin_id -> running qty
    has_bought: dict[str, bool] = {}  # coin_id -> True once a buy is seen
    violations: list[str] = []

    for r in rows:
        coin_id = r["coin_id"]
        ts = r["ts"]
        side = r["side"]
        amount = r["amount"] or 0.0

        qty = holdings.get(coin_id, 0.0)
        bought = has_bought.get(coin_id, False)

        if side == "buy":
            qty += amount
            has_bought[coin_id] = True
        elif side == "sell":
            if not bought:
                violations.append(
                    f"leading sell at {ts} for {coin_id}: sell of {amount} with no prior buy"
                )
            elif amount > qty:
                violations.append(
                    f"oversell at {ts} for {coin_id}: tried to sell {amount} but only {qty} held"
                )
            qty = max(0.0, qty - amount)

        holdings[coin_id] = qty

    return violations


def unrealized_pl(conn, coins_cfg):
    """Total unrealized P/L of the remaining open position, marked to the latest
    snapshot price. Coins with no open position or no snapshot are skipped."""
    total = 0.0
    for c in coins_cfg.get("coins", []):
        if c.get("stable", False):
            continue
        rows = db.load_transactions(conn, c["id"])
        if not rows:
            continue
        _, open_amount, avg_cost = _replay(rows)
        if open_amount <= 0:
            continue
        price = db.latest_snapshot_price(conn, c["id"])
        if price is None or not math.isfinite(price):
            continue
        gain = open_amount * (price - avg_cost)
        if math.isfinite(gain):
            total += gain
    return total
