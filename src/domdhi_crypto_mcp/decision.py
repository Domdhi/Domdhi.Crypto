"""Decision-contract module for FR-23 — the JSON output contract an LLM agent must return.

This module is the boundary between the Domdhi.Crypto signal layer and any
LLM-based decision agent. It defines three things:

1. ``DECISION_SCHEMA`` — a JSON-serializable dict that describes the exact shape
   an agent must return. This is handed to the agent as its output schema/contract.

2. ``validate_decision(obj)`` — validates a raw agent response against the
   contract, raising ``ValueError`` with a specific, human-readable message for
   every distinct failure mode. Callers catch exactly one error type.

3. ``build_trigger_context(context, why_now)`` — assembles the event-driven
   prompt payload from an E14-S1 context dict, without calling any agent or
   touching any network/DB. Pure function: dict in, dict out.

Contract invariants
-------------------
- ``cited_factors`` entries are validated against the live known-name set:
  ``set(factors.FUNCTION_REGISTRY) | {f["name"] for f in factors.BUILTIN_FACTORS}``.
  Hardcoded name lists would drift; the live set cannot.
- ``cited_factors`` may be empty ONLY when ``action == "nothing"``. Any other
  action requires at least one cited factor.
- Whitespace-only rationale is treated as empty and is rejected.
- This module imports only ``json`` and ``factors`` — no DB, no network, no
  pandas/numpy, no MCP. It is a pure, stdlib-only leaf.
"""
import json

from domdhi_crypto.signals import factors

# --------------------------------------------------------------------------- #
# Output schema (handed to the agent as its output contract)
# --------------------------------------------------------------------------- #

DECISION_SCHEMA: dict = {
    "type": "object",
    "description": (
        "The structured decision an agent must return after evaluating the "
        "trigger context. Every field is required."
    ),
    "required": ["action", "rationale", "cited_factors"],
    "properties": {
        "action": {
            "type": "string",
            "enum": ["buy", "hold", "sell", "nothing"],
            "description": (
                "The trading action to take. Use 'nothing' when no threshold "
                "is crossed and no position change is warranted."
            ),
        },
        "rationale": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Human-readable explanation of why this action was chosen. "
                "Must reference the signals and factors that drove the decision."
            ),
        },
        "cited_factors": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Factor names (from BUILTIN_FACTORS or FUNCTION_REGISTRY) that "
                "directly support this decision. Must contain at least one entry "
                "for any action other than 'nothing'."
            ),
        },
    },
}

# Verify the schema is JSON-serializable at import time — catches any accidental
# non-serializable additions before they surface in an agent call.
json.dumps(DECISION_SCHEMA)

# --------------------------------------------------------------------------- #
# Known-name set helper
# --------------------------------------------------------------------------- #

_VALID_ACTIONS = frozenset({"buy", "hold", "sell", "nothing"})


def _known_factor_names() -> frozenset:
    """Return the live set of valid cited-factor names.

    Computed on each call so it stays in sync with the live registries without
    caching staleness. Real callers invoke ``validate_decision`` once per agent
    response, so the cost is negligible.
    """
    return frozenset(factors.FUNCTION_REGISTRY) | frozenset(
        f["name"] for f in factors.BUILTIN_FACTORS
    )


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def validate_decision(obj: dict) -> dict:
    """Validate a raw agent response dict against the decision contract.

    Returns the validated dict unchanged on success.

    Raises ``ValueError`` for every contract violation, with a message that
    contains the key substring the caller or test expects:

    - ``"action"``        — missing key or value not in the enum
    - ``"rationale"``     — missing key or whitespace-only value
    - ``"cited_factors"`` — missing key or value is not a list
    - ``"unknown cited factor: '...'"`` — entry not in the known-name set
    - ``"cite"`` (substring)            — buy/hold/sell action with zero citations
    """
    # ---- action ----------------------------------------------------------- #
    if "action" not in obj:
        raise ValueError("action is required but missing from the decision")
    action = obj["action"]
    if action not in _VALID_ACTIONS:
        raise ValueError(
            f"action must be one of buy/hold/sell/nothing, got {action!r}"
        )

    # ---- rationale -------------------------------------------------------- #
    if "rationale" not in obj:
        raise ValueError("rationale is required but missing from the decision")
    rationale = obj["rationale"]
    if not isinstance(rationale, str) or rationale.strip() == "":
        raise ValueError("rationale must be a non-empty string")

    # ---- cited_factors ---------------------------------------------------- #
    if "cited_factors" not in obj:
        raise ValueError("cited_factors is required but missing from the decision")
    cited = obj["cited_factors"]
    if not isinstance(cited, list):
        raise ValueError(
            f"cited_factors must be a list, got {type(cited).__name__!r}"
        )

    # Validate each entry against the live known-name set. Check the item TYPE
    # before membership: an unhashable item (e.g. a dict from a malformed LLM
    # response) would raise TypeError on `name not in frozenset`, leaking a
    # non-ValueError and breaking the module's single-error-contract promise.
    known = _known_factor_names()
    for name in cited:
        if not isinstance(name, str):
            raise ValueError(
                f"cited_factors entries must be strings, got {type(name).__name__}"
            )
        if name not in known:
            raise ValueError(f"unknown cited factor: {name!r}")

    # Non-nothing actions must cite at least one factor.
    if action != "nothing" and len(cited) == 0:
        raise ValueError(
            f"{action}/hold/sell decisions must cite at least one factor"
        )

    return obj


# --------------------------------------------------------------------------- #
# Trigger-context builder
# --------------------------------------------------------------------------- #

def build_trigger_context(context: dict, why_now: str) -> dict:
    """Assemble the event-driven prompt payload from an E14-S1 context dict.

    This is a pure function: it does NOT call any agent, touch the DB, or make
    network requests. It only restructures the context dict into the shape the
    agent prompt expects.

    Parameters
    ----------
    context:
        An E14-S1 context dict. Required keys accessed: ``position``,
        ``signals``. Optional key: ``factor_menu`` (a dict with a ``builtin``
        list, each entry having a ``"name"`` key). Absent ``factor_menu``
        defaults ``factor_menu_ref`` to ``[]``.
    why_now:
        A human-readable string describing the event or condition that triggered
        this decision request. Echoed verbatim into the output.

    Returns
    -------
    dict
        ``{why_now, position, signals, factor_menu_ref}`` — JSON-serializable.
    """
    factor_menu = context.get("factor_menu", {})
    builtin_entries = factor_menu.get("builtin", [])
    factor_menu_ref = [entry["name"] for entry in builtin_entries]

    return {
        "why_now": why_now,
        "position": context["position"],
        "signals": context["signals"],
        "factor_menu_ref": factor_menu_ref,
    }
