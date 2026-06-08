"""FastMCP stdio server exposing the Domdhi.Crypto signal + decision surface — FR-22/FR-23.

This module lets an LLM agent (Claude Desktop/Code) reason over the local portfolio
*offline*: it exposes the Epic-12 factor menu, Epic-13 signals, and the FR-23
decision contract as MCP tools, all backed by the local SQLite DB and
``coins.local.json``. No live-exchange calls.

Optional-dependency contract (load-bearing)
-------------------------------------------
The ``mcp`` SDK is an OPTIONAL extra (``pip install domdhi-crypto[mcp]``). This module
must therefore import cleanly WITHOUT ``mcp`` installed:

- There is NO top-level ``import mcp``. The SDK is imported lazily inside
  ``build_server`` (and only there).
- All tool logic lives in module-level helper functions (``_get_context``,
  ``_prepare_decision``, ``_get_decision_schema``, ``_validate``) that delegate to the
  pure ``context``/``decision`` modules. They are unit-testable with no ``mcp`` present.
- ``build_server`` / ``run`` are the only entry-points that require the extra; calling
  them without it raises ``ImportError``, which the ``mcp`` CLI subcommand turns into an
  actionable message.

Tool stability
--------------
Tools NEVER raise out to the transport on bad input — ``_get_context`` returns a
structured ``{"error": ...}`` dict for unknown symbols (via ``context.build_context``)
and ``_validate`` returns ``{"ok": False, "error": ...}`` rather than raising. A server
that crashes on a malformed agent call is worse than one that reports the problem.
"""
from __future__ import annotations

from domdhi_crypto.agent import context
from domdhi_crypto.cli import load_coins
from domdhi_crypto.shared import db

from . import decision

SERVER_NAME = "domdhi-crypto"

# --------------------------------------------------------------------------- #
# Pure delegation helpers (no mcp required — the tool bodies call these)
# --------------------------------------------------------------------------- #


def _get_context(symbol: str, *, conn=None, coins_cfg: dict | None = None) -> dict:
    """Return the MCP context snapshot for *symbol* (signals + position + factor menu).

    IO boundary: opens a DB connection and loads ``coins.local.json`` when not
    injected (the production path), or uses the injected ``conn``/``coins_cfg`` (the
    test path). Delegates the actual assembly to the pure ``context.build_context``.

    Tool boundary: this NEVER raises out to the transport. ``load_coins`` raises
    ``SystemExit`` (a BaseException) when ``coins.local.json`` is absent, a malformed
    config entry can raise ``KeyError``, and ``_validate_context`` raises ``ValueError``
    on a JSON-safety failure — all are converted to a structured ``{"error": ...}`` dict.
    """
    try:
        if coins_cfg is None:
            coins_cfg = load_coins()
        if conn is not None:
            return context.build_context(symbol, conn=conn, coins_cfg=coins_cfg)
        owned = db.connect()
        try:
            return context.build_context(symbol, conn=owned, coins_cfg=coins_cfg)
        finally:
            owned.close()
    except SystemExit as exc:
        return {"symbol": symbol, "error": f"configuration error: {exc}"}
    except Exception as exc:  # noqa: BLE001 - tool boundary: never raise out to the transport
        return {"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}


def _prepare_decision(
    symbol: str, why_now: str, *, conn=None, coins_cfg: dict | None = None
) -> dict:
    """Assemble the event-driven decision request for *symbol*.

    Returns ``{"trigger_context": ..., "decision_schema": ...}`` — the trigger context
    (why-now + position + signals + factor menu ref) the agent reasons over, paired
    with the JSON schema its response must satisfy. If the symbol is unknown,
    ``trigger_context`` carries the structured error from ``context.build_context``.
    """
    ctx = _get_context(symbol, conn=conn, coins_cfg=coins_cfg)  # never raises (see above)
    if "error" in ctx:
        return {"trigger_context": ctx, "decision_schema": decision.DECISION_SCHEMA}
    try:
        tc = decision.build_trigger_context(ctx, why_now)
    except Exception as exc:  # noqa: BLE001 - tool boundary: never raise out to the transport
        tc = {"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}
    return {"trigger_context": tc, "decision_schema": decision.DECISION_SCHEMA}


def _get_decision_schema() -> dict:
    """Return the FR-23 decision output contract (action/rationale/cited_factors)."""
    return decision.DECISION_SCHEMA


def _validate(decision_obj: dict) -> dict:
    """Validate an agent decision; return a structured result, never raise.

    ``{"ok": True, "error": None}`` when the decision satisfies the contract,
    ``{"ok": False, "error": "<message>"}`` otherwise. A tool must not raise out to
    the MCP transport, so a malformed agent response is reported structurally.

    Type-guard non-dict input FIRST: ``decision.validate_decision`` opens with
    ``"action" not in obj``, which raises ``TypeError`` (not ``ValueError``) when
    ``obj`` is ``None``/scalar/list — the most likely malformed LLM responses. The
    validator is only contracted to defend dict inputs, so the wrapper owns dict-ness.
    """
    if not isinstance(decision_obj, dict):
        return {
            "ok": False,
            "error": f"decision must be a JSON object, got {type(decision_obj).__name__}",
        }
    try:
        decision.validate_decision(decision_obj)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "error": None}


# --------------------------------------------------------------------------- #
# Server construction (requires the optional `mcp` extra)
# --------------------------------------------------------------------------- #


def build_server():
    """Build and return the configured FastMCP server.

    Imports the ``mcp`` SDK lazily so that merely importing this module never requires
    the optional extra. Raises ``ImportError`` if ``mcp`` is not installed.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(SERVER_NAME)

    @server.tool()
    def get_context(symbol: str) -> dict:
        """Signals, portfolio position, and the factor menu for one coin (offline)."""
        return _get_context(symbol)

    @server.tool()
    def prepare_decision(symbol: str, why_now: str) -> dict:
        """Build the trigger context + decision schema for an event-driven decision."""
        return _prepare_decision(symbol, why_now)

    @server.tool()
    def get_decision_schema() -> dict:
        """Return the JSON schema an agent decision must validate against."""
        return _get_decision_schema()

    @server.tool()
    def validate_decision(decision: dict) -> dict:
        """Validate an agent decision against the contract; returns {ok, error}."""
        return _validate(decision)

    return server


def run() -> None:
    """Launch the FastMCP server over stdio. Requires the ``mcp`` extra."""
    build_server().run()
