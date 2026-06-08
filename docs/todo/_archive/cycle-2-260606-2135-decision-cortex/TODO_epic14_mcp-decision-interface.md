# TODO: Epic 14 — MCP Decision Interface

| Attribute | Value |
|-----------|-------|
| **Status** | Complete — all 4 stories shipped |
| **Author** | Dom |
| **Created** | 2026-06-06 |

---

## Executive Summary

Expose the Epic-12 factor substrate + Epic-13 effectiveness/backtest substrate to an LLM agent (Claude)
over MCP, and define the decision contract it must return. Two pure, offline, fully-tested modules
(`context.py` assembles signals + positions + factor menu; `decision.py` is the JSON decision schema +
validator + trigger-context builder) sit under a FastMCP stdio server (`mcp_server.py`) wired in as an
**optional `[mcp]` dependency extra** so the core package stays 3-dep (requests/pandas/numpy, ADR-001).
A `domdhi-crypto mcp` subcommand launches the server. Realizes FR-22 (signal+context surface) and FR-23
(decision contract).

---

## Dependency Graph

```
Wave 1 (parallel, independent)        Wave 2              Wave 3
┌─────────────────────────────┐
│ E14-S1  context.py          │──┐
│         (signals/positions/ │  │
│          factor menu)       │  │
└─────────────────────────────┘  │   ┌──────────────────────┐   ┌──────────────────────────┐
                                  ├──▶│ E14-S3  mcp_server.py │──▶│ E14-S4  cli `mcp` cmd +   │
┌─────────────────────────────┐  │   │  (FastMCP stdio +     │   │  docs + E2E verify        │
│ E14-S2  decision.py         │──┘   │   [mcp] extra)        │   └──────────────────────────┘
│         (schema/validate/   │      └──────────────────────┘
│          trigger context)   │
└─────────────────────────────┘

Critical path: (E14-S1 ∥ E14-S2) → E14-S3 → E14-S4
```

---

## Phase 6: Agent Decision Interface

**Goal:** Let an LLM agent consume the substrate + portfolio context over MCP and return explainable,
schema-valid decisions — entirely offline against local state.

---

### Epic E14: MCP Decision Interface

**Objective:** Expose signals/context to Claude (FR-22) and define the decision output contract (FR-23),
with execution out of scope (delegated/gated, later cycle).

---

* **Story E14-S1 (M): Context provider module**
  * **As an** agent operator, **I want** a pure function that assembles signals + positions + the factor
    menu for a coin into one schema-valid structured object, **So that** the MCP server can hand Claude a
    complete, offline snapshot to reason over.
  * **AC:**
    * [x] `context.build_context(symbol, *, conn, coins_cfg)` returns a dict with keys `symbol`, `signals`,
      `position`, `factor_menu` and validates against a module-level `CONTEXT_SCHEMA` (hand-rolled validator,
      stdlib only — no `jsonschema`).
    * [x] `signals` includes the `ta.analyze(series["close"])` summary (rsi, macd_hist, sma20/50/200,
      bb_pctb, volatility_annual, human-readable `signals[]`) AND a `factor_values` map of the latest
      non-NaN value of each `factors.BUILTIN_FACTORS` entry (key = factor name, value = float or null).
    * [x] Factor-value extraction reuses the `backtest/engine.py:156-169` guard pattern: skip on
      `ValueError`/`IndexError` from `factors.evaluate`, skip non-Series results (`hasattr(s,"iloc")`), and
      emit `null` (not NaN) for a NaN latest value — output is JSON-serializable (no NaN, no pandas objects).
    * [x] `position` is built from `coins_cfg` for the resolved coin: `{symbol, amount, avg_entry, stable,
      price, value, cost, pl, pl_pct}`, priced via `db.latest_snapshot_price(conn, id)` mirroring
      `cli.cmd_report` (price `None` → `price`/`value`/`pl` null, not a crash; `cost==0` → `pl_pct` 0.0).
    * [x] `factor_menu` serializes `factors.FUNCTION_REGISTRY` (emit ONLY `name`/`signature`/`description`/
      `example`/`category` — NOT the `fn` callable) plus `factors.BUILTIN_FACTORS` and `DEFERRED_FACTORS`.
    * [x] Unknown symbol → returns a structured error result (e.g. `{"error": "..."}`), NOT `SystemExit`
      (a server tool must never exit the process on bad input). Stablecoin → `position` populated,
      `signals.factor_values` empty/`null` and a `note` explaining no history.
    * [x] `tests/test_context.py` covers: happy path (validates against `CONTEXT_SCHEMA`, JSON-serializable
      via `json.dumps`), unknown symbol, stablecoin, missing-snapshot (price None), and the factor-menu
      shape (no callables leak). Uses an in-memory/temp DB via `db.connect(path)` and an inline coins dict.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/context.py` — NEW: `build_context`, `CONTEXT_SCHEMA`, `_validate_context` helper.
    * `tests/test_context.py` — NEW: coverage per AC.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** Positions are config, not DB (architecture line 251). Reuse `cli.cmd_report`
    pricing (cli.py:163-184), `ta.analyze` (ta.py:75), `db.load_close_series`/`latest_snapshot_price`.
    `build_context` takes `conn` + `coins_cfg` as params (no internal `load_coins()`/`db.connect()`) so it
    is pure and testable; the server/CLI layer owns IO. Do NOT import `mcp` here. Heed memory
    `frozen-dataclass-field-name-contract-gap`: emit the literal `FactorFunction` field names.

* **Story E14-S2 (M): Decision contract module**
  * **As an** agent operator, **I want** a JSON decision schema, a validator, and a trigger-context builder,
    **So that** agent decisions are parseable, explainable, and carry their why-now context.
  * **AC:**
    * [x] `decision.DECISION_SCHEMA` defines: `action` ∈ {`buy`,`hold`,`sell`,`nothing`} (required),
      `rationale` (required, non-empty str), `cited_factors` (required, list of str).
    * [x] `decision.validate_decision(obj)` returns the validated dict on success and raises `ValueError`
      with a specific per-failure message (missing key, bad action enum, empty rationale, non-list
      cited_factors, unknown cited factor) — one error contract for callers to catch.
    * [x] `cited_factors` entries are validated against the known-name set
      `set(factors.FUNCTION_REGISTRY) | {f["name"] for f in factors.BUILTIN_FACTORS}`; an unknown name is a
      `ValueError` (a "cited" factor must exist). Empty `cited_factors` is allowed only when
      `action == "nothing"` (a no-op needs no citation); otherwise ≥1 cited factor is required.
    * [x] `decision.build_trigger_context(context, why_now)` returns `{why_now, position, signals,
      factor_menu_ref}` derived from an E14-S1 context dict — the event-driven prompt payload (why-now +
      signal values + position). It does NOT call the agent; it only assembles the request payload.
    * [x] All functions are pure/stdlib (import only `json` + `factors`); JSON-serializable in/out; no `mcp`,
      no network, no DB.
    * [x] `tests/test_decision.py` covers: each valid action validates; every failure mode raises with the
      expected message substring; unknown cited factor rejected; `nothing` with empty citations accepted;
      `build_trigger_context` round-trips a sample context.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/decision.py` — NEW: `DECISION_SCHEMA`, `validate_decision`, `build_trigger_context`.
    * `tests/test_decision.py` — NEW: coverage per AC.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** Hand-rolled validation (no `jsonschema`) keeps ADR-001's dependency-minimal ethos.
    Independent of `context.py` — `build_trigger_context` consumes a context *dict* by shape, so the two
    Wave-1 stories share no file and no import. Known-name set comes from `factors` (a leaf — import is safe).

* **Story E14-S3 (M): FastMCP stdio server + optional `[mcp]` extra**
  * **As an** agent operator, **I want** a FastMCP stdio server exposing context + decision tools, installed
    via an optional extra, **So that** Claude Desktop/Code can call them locally without bloating core deps.
  * **AC:**
    * [x] `pyproject.toml` gains `[project.optional-dependencies]` with `mcp = ["mcp>=1.2"]`; the core
      `dependencies` list is UNCHANGED (still requests/pandas/numpy).
    * [x] `mcp_server.py` does NOT import `mcp` at module top. A `build_server()` function imports `mcp`
      lazily and constructs a `FastMCP("domdhi-crypto")` registering tools: `get_context(symbol)` →
      `context.build_context(...)` (opens `db.connect()`, calls `cli.load_coins()`, closes conn);
      `prepare_decision(symbol, why_now)` → `decision.build_trigger_context(context, why_now)` +
      `get_decision_schema()` → `decision.DECISION_SCHEMA`; `validate_decision(decision)` →
      `decision.validate_decision` returning `{ok: true}` or `{ok: false, error: "..."}` (it must NOT raise
      out of a tool).
    * [x] A `run()` entrypoint calls `build_server().run()` (stdio). Importing `mcp_server` with the extra
      absent must NOT raise (module import is `mcp`-free); only `build_server()`/`run()` touch `mcp`.
    * [x] Tool callables delegate to the pure `context`/`decision` functions and are individually testable
      WITHOUT `mcp` installed.
    * [x] `tests/test_mcp_server.py`: tests the pure delegation/wrapper logic always; gates server
      construction behind `pytest.importorskip("mcp")`; asserts module import succeeds with `mcp` absent.
      Gate (`pytest` on core deps only) stays green.
  * **Estimate:** M
  * **Dependencies:** E14-S1, E14-S2
  * **Files:**
    * `src/domdhi_crypto/mcp_server.py` — NEW: `build_server`, tool functions, `run`.
    * `tests/test_mcp_server.py` — NEW: coverage per AC.
    * `pyproject.toml` — MODIFY: add `[project.optional-dependencies] mcp`.
  * **Agent budget:** 1 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** The lazy-import-in-`build_server` pattern is the load-bearing decision — it lets the
    gate run without the extra (CI = `ruff check . && pytest` on core deps). Tools must return structured
    error dicts, never `SystemExit`/raise (server stability). `get_context` is the IO boundary that
    `build_context` (pure) deliberately avoids.

* **Story E14-S4 (S): `mcp` CLI launch command + docs + E2E verify**
  * **As an** operator, **I want** `domdhi-crypto mcp` to launch the server and the docs to reflect the new
    surface, **So that** the interface is discoverable and the dependency decision is recorded.
  * **AC:**
    * [x] `cli.cmd_mcp(args)` imports `mcp_server` and calls `run()`; an `ImportError` (extra not installed)
      is caught → `SystemExit("Install the MCP extra: pip install domdhi-crypto[mcp]")`. Wired into
      `main()`'s argparse as the `mcp` subcommand; the module docstring usage block gains the `mcp` line.
    * [x] `domdhi-crypto mcp --help` exits 0 and shows the subcommand (smoke-checkable without the extra).
    * [x] `CLAUDE.md` updated: CLI commands list gains `mcp`; Key Paths note `context.py`/`decision.py`/
      `mcp_server.py`; a one-line note that `mcp` is an optional extra (core stays 3-dep).
    * [x] `docs/_project-architecture.md` gains a component note for the three new modules and a documented
      decision (ADR-007 candidate): "MCP server via optional `mcp` extra — core stays 3-dep."
    * [x] Full gate green (`node .claude/core/gate.js test`) — `ruff check src tests` + `pytest`, all passing
      with the new tests, with and without the `[mcp]` extra installed.
  * **Estimate:** S
  * **Dependencies:** E14-S3
  * **Files:**
    * `src/domdhi_crypto/cli.py` — MODIFY: `cmd_mcp`, argparse wiring, docstring usage line.
    * `CLAUDE.md` — MODIFY: CLI commands + Key Paths + optional-extra note.
    * `docs/_project-architecture.md` — MODIFY: component notes + ADR-007 candidate.
  * **Agent budget:** 3 modified, 0 created — within ≤5/≤2 cap
  * **Research notes:** Mirror existing subcommand wiring in `cli.main()` (cli.py:303). The `cmd_mcp` guard
    mirrors the actionable-error style of `_load_series_or_exit`. Leave the CLAUDE.md "218 tests" figure
    correction to whatever the gate reports post-implementation (it currently lags at 225 actual).

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|--------------|
| E14-S1 | Context provider module | M | 1 | [x] | None |
| E14-S2 | Decision contract module | M | 1 | [x] | None |
| E14-S3 | FastMCP stdio server + `[mcp]` extra | M | 2 | [x] | E14-S1, E14-S2 |
| E14-S4 | `mcp` CLI command + docs + verify | S | 3 | [x] | E14-S3 |

**Total: 4 stories. Estimated: ~5 hours.**

---

## Wave Plan

**Shape:** file-overlap partitioned — the stories form a strict dependency layering (two independent pure
modules → server that imports both → CLI/docs that wires the server). Role-based (Tests/Code/Verify) would
break the intra-code ordering (the server's implementation needs `context`/`decision` to already exist);
single-hotspot does not apply (each story owns its own new file, no shared hotspot). Zero file overlap
within any wave.

### Wave 1 — Independent pure modules (parallel)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E14-S1 | general-purpose | `src/domdhi_crypto/context.py`, `tests/test_context.py` | 0/2 | Yes |
| E14-S2 | general-purpose | `src/domdhi_crypto/decision.py`, `tests/test_decision.py` | 0/2 | Yes |

### Wave 2 — Server wiring (depends on Wave 1)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E14-S3 | general-purpose | `src/domdhi_crypto/mcp_server.py`, `tests/test_mcp_server.py`, `pyproject.toml` | 1/2 | Yes |

### Wave 3 — CLI + docs + verify (depends on Wave 2)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E14-S4 | general-purpose | `src/domdhi_crypto/cli.py`, `CLAUDE.md`, `docs/_project-architecture.md` | 3/0 | No |

### Shared Hotspot Files
- **None.** No file is touched by more than one story. `pyproject.toml` (S3) and `cli.py` (S4) each appear
  in exactly one story.

### Critical Path & Parallel Workstreams (REQUIRED)
- **Critical path:** (E14-S1 ∥ E14-S2) → E14-S3 → E14-S4 — ~M + M + S ≈ 4–5 hours wall-clock floor.
- **Parallel workstreams:** 2 independent chains in Wave 1 — `context.py` (S1) ∥ `decision.py` (S2); they
  share no file and no import.
- **Max concurrent agents:** 2 (Wave 1).
- **Bottleneck:** E14-S3 — it imports both Wave-1 modules and introduces the optional-dependency/lazy-import
  contract every downstream piece relies on. If its lazy-import discipline slips, the gate breaks for anyone
  without the `[mcp]` extra and S4 cannot verify green.

---

## Key Findings from Research

1. **Positions are config, not DB** — holdings/avg-entry/`stable` live in `coins.local.json`
   (`cli.load_coins()`), priced via `db.latest_snapshot_price`; no new table needed
   (`docs/_project-architecture.md:251`, `cli.cmd_report` cli.py:163-184).
2. **`mcp` is optional** — not installed; must be a `[mcp]` extra with lazy import inside `build_server()`,
   and `mcp`-touching tests must `pytest.importorskip("mcp")` so the gate (core deps only) stays green.
3. **Pure-module / IO-boundary split** — `context.build_context` and all of `decision.py` are pure and
   param-injected (`conn`, `coins_cfg`); the server/CLI own `db.connect()`/`load_coins()`. This is what lets
   the two Wave-1 stories run in parallel and be tested without a server or `mcp`.
4. **Factor menu must not leak callables** — emit only `FactorFunction`'s name/signature/description/example/
   category, plus `BUILTIN_FACTORS` + `DEFERRED_FACTORS`; everything JSON-serializable, no NaN
   (emit `null`). Reuse `backtest/engine.py:156-169` for safe latest-value extraction.
5. **Tools never exit/raise** — bad input returns a structured error dict (servers must not `SystemExit`);
   contrast with the CLI's `_load_series_or_exit` which intentionally `SystemExit`s.

---

## Execution Log

- **2026-06-06 — Wave 1 (E14-S1, E14-S2):** Both pure modules shipped via parallel Sonnet dev agents
  (tests written by lead first, TDD). `context.build_context` (signals/position/factor_menu, JSON-safe) and
  `decision.py` (DECISION_SCHEMA + validate_decision + build_trigger_context). Adversarial code review caught
  **1 CRITICAL + 1 MAJOR** behind the green suite: (CRITICAL) `math.isnan` lets `±Infinity` leak — the
  `vol_adj_momentum` factor produces `+inf` on a flat-plateau series and broke `json.dumps(allow_nan=False)`;
  fixed with `math.isfinite` guards in the factor loop + ta passthrough, plus a self-enforcing
  `json.dumps(allow_nan=False)` gate inside `_validate_context`. (MAJOR) `validate_decision` raised
  `TypeError` (not `ValueError`) on an unhashable cited factor `[{...}]`; fixed with an `isinstance(str)`
  guard before set membership. Two regression tests added. Gate green at **254/254**. Promoted memory
  `constraints/json-safety-isnan-misses-infinity`. **Known follow-up:** `ta.py:_f` has the same
  isnan-misses-inf latent bug (other consumers: `cmd_ta`, dashboard) — left unfixed (non-owned file, out of
  Wave-1 scope); context's payload is fully protected by the coercion + validator gate.
- **2026-06-06 — Wave 2 (E14-S3):** `mcp_server.py` (FastMCP) + optional `[mcp]` extra in `pyproject.toml`.
  4 tools (`get_context`, `prepare_decision`, `get_decision_schema`, `validate_decision`) delegating to the
  pure modules; `mcp` lazy-imported in `build_server()`. Installed `mcp` in the local venv (uv) so the
  importorskip-gated build test runs for real (all 4 tools register). Review caught **1 MAJOR** — `_validate`
  leaked `TypeError` on non-dict input (caught only `ValueError`); fixed with an `isinstance(dict)` guard +
  regression test. Gate 263/263. Promoted memory
  `patterns/boundary-validator-must-guard-nondict-before-membership`.
- **2026-06-06 — Wave 3 (E14-S4):** `cli.cmd_mcp` (`mcp` subcommand; `ImportError`→`SystemExit` pip-install
  hint) + docstring usage line; `CLAUDE.md` (CLI list + Key Paths + optional-extra note + test-count fix
  218→266) and `_project-architecture.md` (agent-interface component section + **ADR-007**: optional `mcp`
  extra, core stays 3-dep). 3 CLI tests (registered / `--help` exits 0 / missing-extra guard). S-size →
  no code review. Gate **green at 266/266** (265 + 1 mcp-gated). Epic 14 complete.
