# TODO: Epic 15 — Alerts & Scheduled Digest

| Attribute | Value |
|-----------|-------|
| **Status** | Specification Complete |
| **Author** | Dom |
| **Created** | 2026-06-06 |

---

## Executive Summary

Add a `digest` CLI command that loops the configured coins, reuses the existing `ta`/`context` signal layer to find coins with triggered (non-neutral) signals, and writes a locally-composed Markdown brief (triggered signals + position P/L + key factor values as rationale prose) to `data_dir()/digest.md` — so `/schedule` can drop a daily brief into the user's vault. Fully offline: no server, no push, no live LLM call (FR-24, NFR-C2-3). For v1 the "threshold rules" are the defaults already encoded in `ta._signals` (RSI 70/30, Bollinger breakouts, regime/cross flags) — no new config format; a coin is "triggered" iff its `signals` list contains any non-neutral string.

> Wave shape note: research flagged this as single-hotspot (everything centers on `digest.py`), but it is split into 2 linear waves rather than collapsed to one — because `digest.py` is only *modified* by Wave 1 (Wave 2 merely *imports* it), so there is no shared-hotspot file, and the split cleanly enforces the digest.py-before-cli.py-import ordering hazard while keeping the core engine and CLI wiring independently reviewable.

---

## Dependency Graph

```
Wave 1 (core engine)            Wave 2 (CLI surface)
┌────────────────────────┐      ┌────────────────────────┐
│ E15-S1.1 (M)           │      │ E15-S1.2 (S)           │
│ digest.py + paths.py   │ ───► │ cli.py + .gitignore    │
│ + tests/test_digest.py │      │ + test_cli.py          │
└────────────────────────┘      └────────────────────────┘
   builds digest.build()           imports digest, wires
   pure + IO wrapper               `digest` subcommand

Hard ordering: digest.py MUST exist before cli.py's aggregate import
is edited, or every test in test_cli.py breaks on import collection.
The Wave-2-depends-on-Wave-1 edge enforces this.
```

---

## Phase 1: Alerts & Scheduled Digest

**Goal:** Ship a working, tested `digest` command that turns the DB + existing signals into a Markdown brief.

---

### Epic E15: Alerts & Scheduled Digest

**Objective:** A local-first `digest` command summarizing triggered signals + rationale to a Markdown file for `/schedule`.

---

* **Story E15-S1.1 (M): Digest engine + output path**
  * **As a** holder, **I want** a `digest.build()` that renders triggered signals and rationale to a Markdown string and writes it to disk, **So that** a daily brief can be generated from the populated DB with no network or LLM.
  * **AC:**
    * [x] `digest.py` exposes a **pure** builder `build_digest(coins_cfg: dict, *, conn) -> str` returning a Markdown string (no IO), and an **IO wrapper** `build(*, out_path: Path | None = None) -> Path` that owns `db.connect()` + `load_coins()`, calls the pure builder, writes the string with `Path.write_text(..., encoding="utf-8")`, and returns the path — mirroring `dashboard.build()` (`dashboard.py:145–258`).
    * [x] The brief contains a dated top-level header (e.g. `# Domdhi Crypto Digest — {YYYY-MM-DD}`).
    * [x] For each configured coin whose `context.build_context(symbol, conn=conn, coins_cfg=coins_cfg)["signals"]["ta"]["signals"]` list contains at least one non-neutral signal string, the brief emits a section listing those triggered signal strings verbatim.
    * [x] Each triggered-coin section embeds the position P/L (from the context `position` block) and the top factor values (from the context `factor_values` block) as locally-composed Markdown prose — the "agent rationale" is composed in-process from context, with **no** live LLM/API call.
    * [x] Coins with no triggered signal are NOT given a full section — they are summarized in a single "quiet coins" line (comma-joined symbols), or omitted if none.
    * [x] When NO coin has any triggered signal, `build_digest` still returns a valid non-empty Markdown document with the dated header and an explicit `_No signals triggered._` body line (never an empty string / empty file).
    * [x] Every numeric value rendered into the brief is finite — non-finite floats (NaN / ±inf) are coerced to `"n/a"` (or `—`) before rendering, using a `math.isfinite` guard (NOT `math.isnan`; per memory `json-safety-isnan-misses-infinity`).
    * [x] `paths.py` adds `DIGEST_FILE = "digest.md"` and `digest_path() -> Path` returning `data_dir() / DIGEST_FILE` (mirrors the existing `DASHBOARD_FILE` / `dashboard_path`).
    * [x] `build()` defaults `out_path` to `paths.digest_path()` when called with `out_path=None`.
    * [x] `tests/test_digest.py` covers `build_digest` with an injected `conn` (real `tmp_path` SQLite, network mocked) + an in-memory `coins_cfg`: (a) a coin seeded into a triggered state appears with its exact signal strings; (b) a coin seeded into a neutral state does NOT get a section; (c) the zero-trigger case returns the document containing `No signals triggered`. Assertions compare against independently-constructed expected strings/counts — no tautological `assert non-empty` / `assert isfinite` only.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/digest.py` — NEW. Pure `build_digest(coins_cfg, *, conn) -> str` + IO `build(*, out_path=None) -> Path`. Imports `context`, `db`, `paths`, the coins loader, `math`.
    * `src/domdhi_crypto/paths.py` — MODIFY (+2 lines): `DIGEST_FILE` constant + `digest_path()`.
    * `tests/test_digest.py` — NEW. Unit tests for `build_digest` (injected conn/coins_cfg) + the empty-trigger case.
  * **Agent budget:** 1 modified (`paths.py`), 2 created (`digest.py`, `tests/test_digest.py`) — within ≤5/≤2 cap.
  * **Research notes:** `ta.analyze(close)` (`ta.py:75–96`) returns `{"signals": list[str]}` already in plain English ("RSI 72 - overbought", "above 200D SMA (bull regime)"). `context.build_context(symbol, *, conn, coins_cfg)` (`context.py:239–288`) surfaces these at `result["signals"]["ta"]["signals"]` and 44 factor values at `result["factor_values"]`; it also returns a `position` block. Render pattern to copy: `dashboard.build()` (`dashboard.py:145–258`) — open coins cfg + DB, loop coins, f-string concat, `write_text`, return path. The coins loader + `db.connect()` are the IO boundary owned by `build()` (keep `build_digest` pure with injected `conn`/`coins_cfg`, mirroring the `context.py`/`mcp_server.py` pure-vs-IO split from Epic 14). Optional structuring helper available but NOT required: `decision.build_trigger_context(context, why_now)` (`decision.py:164–196`) returns `{why_now, position, signals, factor_menu_ref}` — it's the LLM *prompt* payload, not the rationale; the digest composes its own prose. Do not invoke `DECISION_SCHEMA` / `validate_decision`. Full research: `docs/.output/work/2026-06-06/epic15-alerts-digest/1815-research-codebase.md`.

---

* **Story E15-S1.2 (S): `digest` CLI command + wiring**
  * **As a** holder, **I want** a `digest` subcommand, **So that** I can run `domdhi-crypto digest` (and `/schedule` can call it) to write the brief.
  * **AC:**
    * [x] `cli.py` imports `digest` by adding it to the existing aggregate `from . import ...` line (`cli.py:23`) — done only AFTER `digest.py` exists (Wave-1 dependency) so `test_cli.py` collection does not break on import.
    * [x] `cmd_digest(args)` calls `digest.build(out_path=args.out)` and prints `Wrote {path}` — a thin command that delegates the DB lifecycle to `digest.build()`, exactly like `cmd_dashboard`.
    * [x] A `digest` subparser is registered in `main()`: `sub.add_parser("digest", ...)` with an optional `--out PATH` argument (default `None` → resolves to `paths.digest_path()` inside `build()`), and `.set_defaults(func=cmd_digest)`.
    * [x] The `cli.py` module docstring usage line lists `digest` among the subcommands (alongside init/ingest/ta/report/dashboard/factors/backtest/mcp).
    * [x] `.gitignore` adds `digest.md` (runtime artifact; mirrors the existing dashboard-output ignore).
    * [x] A CLI integration test added to `tests/test_cli.py` drives `digest` end-to-end via `cli.main()` + `sys.argv`, monkeypatching `cli.load_coins` and `cli.db.connect` against a `tmp_path` SQLite (same shape as the `factors_env` fixture, `test_cli.py:53`), and asserts: the command exits 0, writes a file at the resolved path, and prints a line starting with `Wrote `.
    * [x] `ruff check src tests` is clean and `pytest` is green (prior 268 tests + the new digest tests all pass).
  * **Estimate:** S
  * **Dependencies:** E15-S1.1
  * **Files:**
    * `src/domdhi_crypto/cli.py` — MODIFY: add `digest` to the aggregate import, add `cmd_digest`, add the `digest` subparser + `--out`, update the docstring usage line.
    * `.gitignore` — MODIFY (+1 line): `digest.md`.
    * `tests/test_cli.py` — MODIFY: add one `digest` CLI integration test.
  * **Agent budget:** 3 modified (`cli.py`, `.gitignore`, `tests/test_cli.py`), 0 created — within ≤5/≤2 cap.
  * **Research notes:** CLI pattern (`cli.py`): `cmd_*(args)` functions are thin; `sub.add_parser("name").set_defaults(func=cmd_name)`; commands get IO via `db.connect()` / `load_coins()` but here `digest.build()` owns that, so `cmd_digest` stays a 2-liner like `cmd_dashboard`. Test pattern (`test_cli.py`): pytest + `tmp_path` real SQLite, monkeypatch `cli.load_coins` + `cli.db.connect`, drive via `sys.argv` + `cli.main()`, capture with `capsys`. GUARD-TEST CHECK (research Q10): no test asserts an exact subcommand set/count, so adding `digest` breaks nothing — the ONLY ordering hazard is the import line (covered by the Wave-1 dependency). Full research: `docs/.output/work/2026-06-06/epic15-alerts-digest/1815-research-codebase.md`.

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|--------------|
| E15-S1.1 | Digest engine + output path | M | 1 | [x] | None |
| E15-S1.2 | `digest` CLI command + wiring | S | 2 | [x] | E15-S1.1 |

**Total: 2 stories. Estimated: ~2–3 hours.**

---

## Wave Plan

**Shape:** file-overlap partitioned — 2 stories, zero file overlap, strictly linear (S1.2 imports the module S1.1 creates). This is NOT parallelizable; the split exists to (a) enforce the digest.py-before-cli.py-import ordering hazard via the wave dependency, and (b) give a clean core-engine-vs-CLI-wiring review boundary. Each wave is a single story → `/run-todo` runs each Main-Agent-direct (Path A), no delegation overhead.

### Wave 1 — Core engine
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E15-S1.1 | general-purpose | `src/domdhi_crypto/digest.py`, `src/domdhi_crypto/paths.py`, `tests/test_digest.py` | 1/2 | Yes |

### Wave 2 — CLI surface (depends on Wave 1)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E15-S1.2 | general-purpose | `src/domdhi_crypto/cli.py`, `.gitignore`, `tests/test_cli.py` | 3/0 | Yes |

### Shared Hotspot Files
- None. `digest.py` is created in Wave 1 and only *imported* (not modified) in Wave 2 — no file is modified by both waves. Zero overlap.

### Critical Path & Parallel Workstreams (REQUIRED)
- **Critical path:** E15-S1.1 → E15-S1.2 — the entire TODO is one linear chain; ~2–3 hours. This is the wall-clock floor.
- **Parallel workstreams:** none — the two stories are strictly sequential (S1.2 imports S1.1's module). Adding agents cannot speed this up.
- **Max concurrent agents:** 1.
- **Bottleneck:** E15-S1.1 — it creates `digest.py` and `paths.digest_path()` that S1.2 imports and wires. If its public surface (`build`/`build_digest` signatures, `--out` semantics) changes, S1.2's command + test change with it.

---

## Key Findings from Research

1. **No new threshold-config format needed (v1)** — `config.local.json` holds only `{api_key, tier}` and `coins.local.json` holds coin metadata only. The "threshold rules" are the defaults already in `ta._signals` (RSI 70/30, Bollinger breakouts, regime/cross flags). A coin is "triggered" iff its `signals` list has a non-neutral entry. Future user-tunable rules → `digest_rules.local.json` via `paths.data_dir()` is the documented extension point (out of scope here).
2. **"Agent rationale" = locally-composed prose, not an LLM call** — there is no in-process LLM (offline, NFR-C2-3). `decision.build_trigger_context` (`decision.py:164–196`) builds the LLM *prompt* payload `{why_now, position, signals, factor_menu_ref}`; the digest renders its own Markdown rationale from the same `context` data. `DECISION_SCHEMA`/`validate_decision` are NOT used.
3. **Signals are already human-readable** — `ta.analyze` returns plain-English signal strings; `context.build_context` exposes them at `result["signals"]["ta"]["signals"]` plus 44 factor values and a `position` block. The digest is a filter-and-render layer over `build_context`, not new analysis.
4. **`dashboard.build()` is the exact render+IO pattern to copy** (`dashboard.py:145–258`): open coins cfg + DB, loop coins, f-string assemble, `Path.write_text(..., encoding="utf-8")`, return path. Keep `build_digest` pure (injected `conn`/`coins_cfg`) per the Epic-14 pure-vs-IO split; `build()` is the IO boundary.
5. **Output location** — `paths.digest_path()` → `data_dir() / "digest.md"`, mirroring `DASHBOARD_FILE`/`dashboard_path`; `digest.md` is git-ignored runtime state.
6. **Only one ordering hazard** — write `digest.py` before editing `cli.py`'s aggregate import, or `test_cli.py` fails at collection. Enforced by the Wave-2→Wave-1 dependency. No subcommand-count guard test exists, so nothing else breaks.

---

## Execution Log

- **2026-06-06 — Wave 1 (E15-S1.1):** Built `digest.py` (`build_digest` pure + `build` IO wrapper), added
  `paths.DIGEST_FILE` + `paths.digest_path()`, and `tests/test_digest.py` (12 tests). Gate green
  (280 passed). Code review DONE_WITH_CONCERNS → fixed the one MINOR (`$n/a` money-token sigil) +
  a NIT (double `_fmt_num` call) before commit via `_fmt_money`/`_fmt_pct` helpers.
  - **Key decision (deviation note):** `build()` signature is `build(out_path=None, *, conn=None, coins_cfg=None)`
    (superset of the TODO's `build(*, out_path=None)`) — the `conn`/`coins_cfg` injection is the
    research-Appendix test contract and keeps `build_digest` pure. `build()` loads coins via an inline
    `_load_coins()` (mirrors `dashboard.build`) rather than `cli.load_coins` to avoid a circular import
    (`cli` imports `digest`).
  - **Product observation (for v2 tuning):** with the v1 "any non-neutral signal" rule, every coin with a
    real price series triggers (its MACD/regime/cross strings are always directional); only stables and
    un-ingested coins are "quiet". This is the deliberate Option-C scope (research §2). The documented
    extension point for selective rules is `digest_rules.local.json`.
- **2026-06-06 — Wave 2 (E15-S1.2):** Wired the `digest` subcommand into `cli.py` (aggregate import + thin
  `cmd_digest` + `--out` subparser + docstring usage line), added `digest.md` to `.gitignore`, and added 3
  CLI tests to `tests/test_cli.py` (registered-handler, end-to-end write, `--out` override). Gate green
  (283 passed). S-sized → code review skipped per `/run-todo` rule.
  - **AC-6 deviation note:** the AC said monkeypatch `cli.load_coins` + `cli.db.connect`; the test instead
    patches `digest._load_coins` + `db.connect` — those are the actual loader/connector `digest.build()`
    uses (it avoids importing `cli` to prevent a circular import). Same intent (drive end-to-end against a
    tmp SQLite, no real config/network), correct target.
