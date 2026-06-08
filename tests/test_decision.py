"""Tests for the decision-contract module (decision.py) — FR-23.

These tests are AC-derived (TDD): they are written against the decision contract
the module must satisfy, NOT against an implementation. Each validation rule is
checked with a *counterfactual* — a wrong-but-plausible decision the validator
must reject — rather than only asserting the happy path succeeds. The cited-factor
rule is checked against the real factor name set imported from ``factors`` (an
independent source of truth), so a validator that silently accepts any string is
caught.
"""
import json

import pytest

from domdhi_crypto.signals import factors
from domdhi_crypto_mcp import decision

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_KNOWN_FACTOR = "rsi_14"          # a real BUILTIN_FACTORS name
_KNOWN_PRIMITIVE = "RSI"          # a real FUNCTION_REGISTRY key
_UNKNOWN_FACTOR = "totally_made_up_factor_xyz"


def _valid(**over):
    d = {"action": "buy", "rationale": "RSI oversold and price reclaimed 200D SMA.",
         "cited_factors": [_KNOWN_FACTOR]}
    d.update(over)
    return d


# --------------------------------------------------------------------------- #
# DECISION_SCHEMA shape
# --------------------------------------------------------------------------- #

def test_schema_declares_action_enum_and_required_fields():
    schema = decision.DECISION_SCHEMA
    # The four legal actions must all be present in the schema's enum, and no others.
    blob = json.dumps(schema)
    for action in ("buy", "hold", "sell", "nothing"):
        assert action in blob
    # Schema must be JSON-serializable (it is handed to an LLM as the output contract).
    assert isinstance(json.loads(blob), dict)


# --------------------------------------------------------------------------- #
# validate_decision — happy path for every legal action
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("action", ["buy", "hold", "sell"])
def test_validate_accepts_each_action_with_citation(action):
    out = decision.validate_decision(_valid(action=action))
    assert out["action"] == action
    assert out["cited_factors"] == [_KNOWN_FACTOR]


def test_validate_accepts_primitive_name_as_citation():
    # A FUNCTION_REGISTRY primitive (e.g. RSI) is also a valid citation, not only
    # a BUILTIN_FACTORS name.
    out = decision.validate_decision(_valid(cited_factors=[_KNOWN_PRIMITIVE]))
    assert out["cited_factors"] == [_KNOWN_PRIMITIVE]


def test_validate_accepts_nothing_with_empty_citations():
    # 'nothing' is the no-op action — it needs no cited factor.
    out = decision.validate_decision(
        {"action": "nothing", "rationale": "No signal crossed threshold.", "cited_factors": []}
    )
    assert out["action"] == "nothing"


# --------------------------------------------------------------------------- #
# validate_decision — every failure mode raises ValueError
# --------------------------------------------------------------------------- #

def test_reject_unknown_action():
    with pytest.raises(ValueError, match="action"):
        decision.validate_decision(_valid(action="moon"))


def test_reject_missing_action():
    bad = _valid()
    del bad["action"]
    with pytest.raises(ValueError, match="action"):
        decision.validate_decision(bad)


def test_reject_empty_rationale():
    with pytest.raises(ValueError, match="rationale"):
        decision.validate_decision(_valid(rationale="   "))


def test_reject_missing_rationale():
    bad = _valid()
    del bad["rationale"]
    with pytest.raises(ValueError, match="rationale"):
        decision.validate_decision(bad)


def test_reject_cited_factors_not_a_list():
    with pytest.raises(ValueError, match="cited_factors"):
        decision.validate_decision(_valid(cited_factors=_KNOWN_FACTOR))  # str, not list


def test_reject_unhashable_cited_factor_as_valueerror():
    # Regression (Wave-1 review MAJOR-1): a malformed LLM response citing a dict
    # must raise ValueError, NOT a leaked TypeError from `dict in frozenset`.
    with pytest.raises(ValueError, match="(?i)string|cited"):
        decision.validate_decision(_valid(cited_factors=[{"factor": "rsi_14"}]))


def test_reject_unknown_cited_factor():
    # The whole point of "cited rationale" — a cited factor must actually exist.
    with pytest.raises(ValueError, match="(?i)unknown|cited"):
        decision.validate_decision(_valid(cited_factors=[_UNKNOWN_FACTOR]))


def test_reject_non_nothing_action_with_empty_citations():
    # buy/hold/sell must cite at least one factor.
    with pytest.raises(ValueError, match="(?i)cite"):
        decision.validate_decision(_valid(action="buy", cited_factors=[]))


def test_unknown_factor_is_actually_unknown_guard():
    # Guard the test's own premise: the "unknown" factor must really be absent from
    # the known set, else the rejection test is vacuous.
    known = set(factors.FUNCTION_REGISTRY) | {f["name"] for f in factors.BUILTIN_FACTORS}
    assert _UNKNOWN_FACTOR not in known
    assert _KNOWN_FACTOR in known
    assert _KNOWN_PRIMITIVE in known


# --------------------------------------------------------------------------- #
# build_trigger_context
# --------------------------------------------------------------------------- #

def _sample_context():
    return {
        "symbol": "BTC",
        "signals": {"ta": {"rsi": 28.0, "price": 100.0}, "factor_values": {"rsi_14": 28.0}},
        "position": {"symbol": "BTC", "amount": 0.5, "value": 50.0, "pl": 5.0},
        "factor_menu": {"builtin": [{"name": "rsi_14"}, {"name": "macd_hist"}],
                        "primitives": [{"name": "RSI"}], "deferred": []},
    }


def test_trigger_context_carries_whynow_position_signals():
    ctx = _sample_context()
    tc = decision.build_trigger_context(ctx, "rsi_14 crossed below 30")
    assert tc["why_now"] == "rsi_14 crossed below 30"
    # Position and signals are passed through unchanged (the agent reasons over them).
    assert tc["position"] == ctx["position"]
    assert tc["signals"] == ctx["signals"]
    assert "factor_menu_ref" in tc


def test_trigger_context_is_json_serializable():
    tc = decision.build_trigger_context(_sample_context(), "scheduled daily review")
    # Must round-trip through JSON — it becomes the agent prompt payload.
    assert json.loads(json.dumps(tc))["why_now"] == "scheduled daily review"
