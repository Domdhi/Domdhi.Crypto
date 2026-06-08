"""MCP context-provider module — FR-22.

Assembles a structured, 100% JSON-serializable snapshot of a coin's current
state for consumption by an LLM over the Model Context Protocol.  The primary
entry-point is ``build_context``; it resolves the coin, loads signals/factors/
position, and validates the result against ``CONTEXT_SCHEMA`` before returning.

Contract invariants (load-bearing):
- ``json.dumps(result, allow_nan=False)`` must never raise — no NaN, no numpy
  scalars, no pandas objects, no callables anywhere in the output.
- ``build_context`` is pure w.r.t. IO injection: it receives ``conn`` and
  ``coins_cfg`` as parameters and never calls ``db.connect()`` or
  ``cli.load_coins()`` itself.
- Unknown symbol → ``{"symbol": symbol, "error": "..."}`` — never ``SystemExit``.
- Stablecoin → ``position`` populated, ``signals`` carry ``ta=None``,
  ``factor_values={}``, and a ``note`` explaining the skip.
"""
import json
import math

from domdhi_crypto.shared import db
from domdhi_crypto.signals import factors, ta

# --------------------------------------------------------------------------- #
# Published schema contract (hand-rolled; no jsonschema dependency)
# --------------------------------------------------------------------------- #

CONTEXT_SCHEMA: dict = {
    "type": "object",
    "description": (
        "Structured snapshot of one coin's TA signals, factor values, portfolio "
        "position, and the available factor function menu.  Every value is JSON-safe "
        "(no NaN, no numpy scalars, no callables)."
    ),
    "required_keys": ["symbol", "signals", "position", "factor_menu"],
    "signals_required_keys": ["ta", "factor_values"],
    "position_required_keys": [
        "symbol", "amount", "avg_entry", "stable",
        "price", "value", "cost", "pl", "pl_pct",
    ],
    "factor_menu_required_keys": ["primitives", "builtin", "deferred"],
}


# --------------------------------------------------------------------------- #
# Internal validator
# --------------------------------------------------------------------------- #

def _validate_context(obj: dict) -> None:
    """Validate that *obj* satisfies the CONTEXT_SCHEMA contract.

    Raises ``ValueError`` with a descriptive message on the first violation
    found.  A passing result from ``build_context`` will always pass this
    check; external callers may also use it to verify hand-assembled dicts.
    """
    if not isinstance(obj, dict):
        raise ValueError(f"context must be a dict, got {type(obj).__name__}")

    for key in CONTEXT_SCHEMA["required_keys"]:
        if key not in obj:
            raise ValueError(f"context missing required key: {key!r}")

    signals = obj["signals"]
    if not isinstance(signals, dict):
        raise ValueError("context['signals'] must be a dict")
    for key in CONTEXT_SCHEMA["signals_required_keys"]:
        if key not in signals:
            raise ValueError(f"context['signals'] missing required key: {key!r}")
    if not isinstance(signals["factor_values"], dict):
        raise ValueError("context['signals']['factor_values'] must be a dict")

    pos = obj["position"]
    if not isinstance(pos, dict):
        raise ValueError("context['position'] must be a dict")
    for key in CONTEXT_SCHEMA["position_required_keys"]:
        if key not in pos:
            raise ValueError(f"context['position'] missing required key: {key!r}")

    menu = obj["factor_menu"]
    if not isinstance(menu, dict):
        raise ValueError("context['factor_menu'] must be a dict")
    for key in CONTEXT_SCHEMA["factor_menu_required_keys"]:
        if key not in menu:
            raise ValueError(f"context['factor_menu'] missing required key: {key!r}")

    for prim in menu.get("primitives", []):
        if not isinstance(prim, dict):
            raise ValueError("each primitive entry must be a dict")
        if "fn" in prim:
            raise ValueError("primitive entry must not contain 'fn' callable")
        for field in ("name", "signature", "description", "example", "category"):
            if field not in prim:
                raise ValueError(f"primitive entry missing field: {field!r}")

    # Terminal JSON-safety gate: the #1 invariant is that the context is
    # serializable with no NaN/Infinity (and no numpy/pandas/callable). Enforce it
    # here rather than trusting upstream coercion — this catches any future factor
    # or ta field that leaks a non-finite or non-serializable value, and turns it
    # into the module's single error contract (ValueError) instead of a surprise at
    # the MCP transport boundary.
    try:
        json.dumps(obj, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"context is not JSON-safe: {exc}") from exc


# --------------------------------------------------------------------------- #
# Factor menu builder
# --------------------------------------------------------------------------- #

def _build_factor_menu() -> dict:
    """Serialize FUNCTION_REGISTRY + BUILTIN_FACTORS + DEFERRED_FACTORS.

    Emits only the metadata fields from each FactorFunction (never ``fn``).
    """
    primitives = [
        {
            "name": ff.name,
            "signature": ff.signature,
            "description": ff.description,
            "example": ff.example,
            "category": ff.category,
        }
        for ff in factors.FUNCTION_REGISTRY.values()
    ]
    return {
        "primitives": primitives,
        "builtin": list(factors.BUILTIN_FACTORS),
        "deferred": list(factors.DEFERRED_FACTORS),
    }


# --------------------------------------------------------------------------- #
# Position builder
# --------------------------------------------------------------------------- #

def _build_position(coin: dict, conn) -> dict:
    """Build the position block for *coin* priced via the latest snapshot.

    Mirrors the pricing logic in ``cli.cmd_report`` lines 163-184.
    ``price=None`` (no snapshot) → ``value`` and ``pl`` are also ``None``;
    ``cost==0`` (zero average-entry or zero amount) → ``pl_pct`` is ``0.0``.
    """
    price = db.latest_snapshot_price(conn, coin["id"])
    amount = coin.get("amount", 0)
    avg_entry = coin.get("avg_entry", 0)
    stable = coin.get("stable", False)

    value = price * amount if price is not None else None
    cost = avg_entry * amount
    pl = (value - cost) if value is not None else None
    pl_pct = (pl / cost * 100) if (cost and pl is not None) else 0.0

    return {
        "symbol": coin["symbol"],
        "amount": amount,
        "avg_entry": avg_entry,
        "stable": stable,
        "price": price,
        "value": value,
        "cost": cost,
        "pl": pl,
        "pl_pct": pl_pct,
    }


# --------------------------------------------------------------------------- #
# TA + factor signals builder
# --------------------------------------------------------------------------- #

def _build_signals(frame, stable: bool) -> dict:
    """Compute TA summary and factor values from *frame*.

    *frame* is the DataFrame returned by ``db.load_close_series`` (close +
    volume columns, continuous daily DatetimeIndex).  When *stable* is True
    or *frame* is None, return a stub with ``ta=None`` and empty
    ``factor_values``.

    Factor values mirror the backtest engine guard pattern
    (``engine.py:156-169``): skip on ``ValueError``/``IndexError``, skip
    non-Series results, emit ``None`` (not NaN) for a NaN latest value.
    """
    if stable:
        return {
            "ta": None,
            "factor_values": {},
            "note": "stablecoin — no TA or factor analysis performed",
        }

    if frame is None:
        return {
            "ta": None,
            "factor_values": {},
            "note": "no price series available — ingest data first",
        }

    close = frame["close"]

    # TA summary — ta.analyze already coerces NaN→None via _f(), but we
    # defensively coerce any surviving NaN to None so allow_nan=False is safe.
    raw_ta = ta.analyze(close)
    ta_safe: dict = {}
    for k, v in raw_ta.items():
        # Coerce any non-finite float (NaN *or* ±Infinity) to None. math.isnan alone
        # misses Infinity, which is equally non-JSON-serializable under allow_nan=False.
        if isinstance(v, float) and not math.isfinite(v):
            ta_safe[k] = None
        else:
            # signals list (strings) and finite scalars are already safe
            ta_safe[k] = v

    # Factor values — guard pattern from backtest engine.py:156-169
    factor_values: dict = {}
    for d in factors.BUILTIN_FACTORS:
        try:
            series = factors.evaluate(d["expression"], frame)
        except (ValueError, IndexError):
            factor_values[d["name"]] = None
            continue
        if not hasattr(series, "iloc"):
            # Degenerate scalar expression — no latest-value concept
            factor_values[d["name"]] = None
            continue
        val = float(series.iloc[-1])
        # isfinite rejects NaN AND ±Infinity — the latter is reachable (e.g.
        # vol_adj_momentum divides by a near-flat-window stddev) and would break
        # json.dumps(allow_nan=False) at the MCP boundary if it leaked through.
        factor_values[d["name"]] = val if math.isfinite(val) else None

    return {
        "ta": ta_safe,
        "factor_values": factor_values,
    }


# --------------------------------------------------------------------------- #
# Public entry-point
# --------------------------------------------------------------------------- #

def build_context(symbol: str, *, conn, coins_cfg: dict) -> dict:
    """Build and return the MCP context snapshot for *symbol*.

    Parameters
    ----------
    symbol:
        Ticker symbol (case-insensitive, e.g. ``"BTC"``).
    conn:
        Open SQLite connection (caller owns lifecycle).
    coins_cfg:
        Parsed ``coins.local.json`` dict with a ``"coins"`` list.

    Returns
    -------
    dict
        Success:
            ``{symbol, signals, position, factor_menu}`` — always JSON-safe,
            validated against ``CONTEXT_SCHEMA``.
        Error:
            ``{symbol, error}`` — returned (not raised) for unknown symbols.
    """
    # ---- resolve coin (mirror cli._resolve) ----
    token = symbol.lower()
    coin = None
    for c in coins_cfg.get("coins", []):
        if token in (c["id"].lower(), c["symbol"].lower()):
            coin = c
            break

    if coin is None:
        return {"symbol": symbol, "error": f"unknown symbol {symbol!r} — not found in coins_cfg"}

    # ---- load price series (None for stables or un-ingested coins) ----
    stable = coin.get("stable", False)
    frame = None if stable else db.load_close_series(conn, coin["id"])

    # ---- assemble context ----
    signals = _build_signals(frame, stable)
    position = _build_position(coin, conn)
    factor_menu = _build_factor_menu()

    result = {
        "symbol": symbol.upper(),
        "signals": signals,
        "position": position,
        "factor_menu": factor_menu,
    }

    _validate_context(result)
    return result
