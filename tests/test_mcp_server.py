"""Tests for the FastMCP server module (mcp_server.py) — E14-S3.

The server wraps the pure ``context``/``decision`` functions as MCP tools. The
``mcp`` SDK is an OPTIONAL dependency (`pip install domdhi-crypto[mcp]`), so:

- Importing ``mcp_server`` must NOT require ``mcp`` (no top-level mcp import) — the
  module exposes pure delegation helpers (``_get_context``, ``_prepare_decision``,
  ``_get_decision_schema``, ``_validate``) that are tested here WITHOUT mcp.
- Only ``build_server()`` / ``run()`` touch ``mcp``; the server-construction test is
  gated behind ``pytest.importorskip("mcp")`` so the gate stays green without the extra.

The delegation helpers accept injected ``conn``/``coins_cfg`` so they are testable
against a temp DB without hitting the real data directory.
"""
import json

import numpy as np
import pandas as pd
import pytest

from domdhi_crypto.shared import db
from domdhi_crypto_mcp import server as mcp_server

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _closes(n=260):
    vals = np.cumsum(np.sin(np.arange(n) / 5.0) + np.cos(np.arange(n) / 3.0)) + 200.0
    return [float(v) for v in vals]


@pytest.fixture()
def seeded(tmp_path):
    path = str(tmp_path / "crypto.db")
    db.init_db(path)
    conn = db.connect(path)
    closes = _closes()
    dates = pd.date_range("2023-01-01", periods=len(closes), freq="D").strftime("%Y-%m-%d")
    rows = [(d, c, 1000.0 + i, c * 10) for i, (d, c) in enumerate(zip(dates, closes, strict=True))]
    db.upsert_coin(conn, "bitcoin", "BTC", "BTC")
    db.upsert_prices(conn, "bitcoin", rows)
    db.insert_snapshot(conn, "bitcoin", "2023-09-18T00:00:00Z", 60_000.0, 1e12, 1.0, 2.0, 3.0)
    conn.commit()
    cfg = {"vs_currency": "usd",
           "coins": [{"id": "bitcoin", "symbol": "BTC", "amount": 0.5, "avg_entry": 50_000.0}]}
    yield conn, cfg
    conn.close()


# --------------------------------------------------------------------------- #
# Module import safety — must NOT require mcp
# --------------------------------------------------------------------------- #

def test_module_imports_without_mcp():
    # If this test runs at all, the import at the top of the file already succeeded
    # with mcp absent. Assert the public surface exists.
    for attr in ("build_server", "run", "_get_context", "_prepare_decision",
                 "_get_decision_schema", "_validate"):
        assert hasattr(mcp_server, attr)


def test_no_top_level_mcp_import():
    # mcp must only be imported lazily inside build_server/run — never at module load.
    import inspect
    src = inspect.getsource(mcp_server)
    # The only mentions of mcp-the-sdk should be inside a function body (indented).
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("import mcp") or stripped.startswith("from mcp"):
            assert line[0] in (" ", "\t"), f"mcp imported at module top: {line!r}"


# --------------------------------------------------------------------------- #
# Delegation helpers — tested WITHOUT mcp
# --------------------------------------------------------------------------- #

def test_get_context_delegates_and_is_json_safe(seeded):
    conn, cfg = seeded
    ctx = mcp_server._get_context("BTC", conn=conn, coins_cfg=cfg)
    assert ctx["symbol"] == "BTC"
    assert set(ctx) >= {"symbol", "signals", "position", "factor_menu"}
    json.dumps(ctx, allow_nan=False)


def test_get_context_unknown_symbol_is_structured_error(seeded):
    conn, cfg = seeded
    ctx = mcp_server._get_context("DOGE", conn=conn, coins_cfg=cfg)
    assert "error" in ctx  # never raises / SystemExit


def test_get_context_never_raises_on_missing_config(seeded, monkeypatch):
    # Regression (sweep F-2): load_coins() raises SystemExit when coins.local.json is
    # absent. A tool must convert that to a structured error, never let it reach the
    # transport. coins_cfg=None forces the load_coins() path.
    conn, _ = seeded

    def _boom():
        raise SystemExit("Missing coins.local.json")

    monkeypatch.setattr(mcp_server, "load_coins", _boom)
    ctx = mcp_server._get_context("BTC", conn=conn)
    assert "error" in ctx and "config" in ctx["error"].lower()


def test_get_context_never_raises_on_malformed_config(seeded):
    # Regression (sweep F-3): a coins_cfg entry missing "symbol"/"id" must come back
    # as a structured error, not a leaked KeyError.
    conn, _ = seeded
    bad_cfg = {"vs_currency": "usd", "coins": [{"id": "bitcoin"}]}  # no "symbol"
    ctx = mcp_server._get_context("BTC", conn=conn, coins_cfg=bad_cfg)
    assert "error" in ctx


def test_prepare_decision_bundles_trigger_and_schema(seeded):
    conn, cfg = seeded
    out = mcp_server._prepare_decision("BTC", "rsi_14 crossed below 30", conn=conn, coins_cfg=cfg)
    assert out["trigger_context"]["why_now"] == "rsi_14 crossed below 30"
    assert out["decision_schema"] == mcp_server._get_decision_schema()
    json.dumps(out, allow_nan=False)


def test_get_decision_schema_is_the_contract():
    schema = mcp_server._get_decision_schema()
    blob = json.dumps(schema)
    for action in ("buy", "hold", "sell", "nothing"):
        assert action in blob


def test_validate_returns_ok_dict_never_raises():
    valid = {"action": "hold", "rationale": "no threshold crossed", "cited_factors": ["rsi_14"]}
    assert mcp_server._validate(valid) == {"ok": True, "error": None}
    # Invalid input must come back as a structured failure, NOT an exception.
    bad = mcp_server._validate({"action": "moon", "rationale": "x", "cited_factors": []})
    assert bad["ok"] is False
    assert bad["error"]  # non-empty message


def test_validate_non_dict_input_is_structured_not_typeerror():
    # Regression (Wave-2 review MAJOR): a non-dict agent response (null/scalar/list —
    # routine malformed LLM output) must return {ok:False}, NOT leak a TypeError out
    # of the tool to the MCP transport.
    for bad in (None, 42, ["action"], "hold"):
        r = mcp_server._validate(bad)
        assert r["ok"] is False and r["error"], bad


# --------------------------------------------------------------------------- #
# Server construction — requires the optional mcp extra
# --------------------------------------------------------------------------- #

def test_build_server_constructs_when_mcp_present():
    pytest.importorskip("mcp")
    srv = mcp_server.build_server()
    # FastMCP stores the server name; assert the lazy import + construction worked.
    assert getattr(srv, "name", None) == "domdhi-crypto"
