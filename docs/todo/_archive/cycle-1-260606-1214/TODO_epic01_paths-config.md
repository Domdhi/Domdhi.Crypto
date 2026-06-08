# TODO — Epic 1: Paths & Config Resolution

| Attribute | Value |
|-----------|-------|
| **Parent** | [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md) |
| **Phase** | Phase 0 — Foundation & Configuration |
| **Status** | Complete (shipped) |
| **Stories** | E1-S1, E1-S2 |
| **Last Updated** | 2026-06-06 |

---

## Executive Summary

Epic 1 owns the two leaf concerns every other module leans on: **where** runtime files live and **whether** the files needed to run are actually present and valid. Story E1-S1 makes the whole tool relocatable — all runtime filenames resolve from a single `paths` module rooted at `$DOMDHI_CRYPTO_HOME` (or the current working directory). Story E1-S2 makes first-run failures legible — missing or placeholder config/holdings fail fast with an exact "copy-the-example" fix message instead of a traceback.

This epic is **brownfield**: both stories are already implemented and verified at commit `ad85772`. The checklist below is recorded for FR traceability — each task documents a contract that holds in the shipped code, not work to be executed. A build wave that picks this epic up should treat it as a verification/no-op unless a regression is found.

### Key Deliverables

- A `paths` module that is the single source of every runtime file location (`$DOMDHI_CRYPTO_HOME` vs CWD, fixed filenames). *(E1-S1, FR-15)*
- Fail-fast credential loading: missing/empty/`PASTE` `config.local.json` exits with a copy-the-example fix. *(E1-S2, FR-7)*
- Fail-fast holdings loading on missing `coins.local.json`, read fresh each run with no caching. *(E1-S2, FR-16)*
- No module hard-codes a runtime filename — all locations flow through `paths.*`. *(E1-S1, NFR-M1)*

---

## Optimization Summary

`/review:optimize-backlog` has **not** been run on this backlog. Sequencing here follows the backlog's dependency ordering as authoritative: E1-S1 (the resolver) lands before E1-S2 (config loading), because fail-fast loading reads its file locations from the resolver. Both stories own distinct, non-overlapping files (`paths.py` vs `coingecko.py` + example JSON), so no within-epic file conflict exists. Phase 4 story **E11-S1** later adds the missing dedicated `paths.py` test against a *new* test file — no source overlap with E1-S1.

---

## Execution Log

| Date | Story | Event |
|------|-------|-------|
| (pre-`ad85772`) | E1-S1 | Implemented and shipped — `paths.py` resolver in place. |
| (pre-`ad85772`) | E1-S2 | Implemented and shipped — fail-fast `load_config` + example JSON in place. |
| 2026-06-06 | — | Checklist generated from backlog for FR traceability; epic marked Complete (shipped). |

---

## Key Decisions

- **Single resolver, no hard-coded filenames.** All runtime file locations flow through `paths.*` constants/helpers so the tool is relocatable into an Obsidian vault or any chosen folder. *(NFR-M1)*
- **Fail fast, never traceback.** Missing/placeholder config and holdings raise `SystemExit` with an explicit copy-the-example fix rather than producing a stack trace on first run. *(FR-7, FR-16)*
- **Read fresh, no caching.** Config and holdings are read on each run so edits take effect without restart concerns. *(FR-16)*
- **Split ownership of FR-16.** `coingecko.py` here owns the `config.local.json` credential side; `coins.local.json` holdings loading (`load_coins`) lives in `cli.py` and is exercised under Epic 2 / Epic 4 — called out to keep file ownership clean.

---

## AI Task Management Protocol

- Work one story at a time, top to bottom; respect the Dependencies line before starting.
- A story is done only when **every** acceptance criterion has a checked task and Validation passes.
- This epic is **shipped/inert**: do not re-dispatch as live build work. If a task's contract no longer holds, that is a regression — flag it rather than silently re-checking.
- Do not edit acceptance criteria here; the backlog (`_backlog.md`) is the source of truth. Changes flow backlog → checklist, never the reverse.

### Key

- `[x]` — done / shipped and verified
- `[ ]` — open / not started
- `[~]` — in progress
- `[!]` — blocked (see note)

---

## Context

This epic produces the **foundation leaf** that the data, ingest, analysis, and presentation layers all sit on top of.

- `paths.py` resolves the data directory from `$DOMDHI_CRYPTO_HOME`, falling back to `Path.cwd()` when the variable is unset, and joins it with the fixed filenames: `config.local.json`, `coins.local.json`, the SQLite `crypto.db`, and the generated dashboard HTML.
- Config/holdings loading reads `config.local.json` (credentials, via `coingecko.py`'s `load_config`) and `coins.local.json` (holdings), failing fast with copy-the-example guidance when a file is missing or still holds placeholder values.
- Example files `config.example.json` and `coins.example.json` are the templates users copy on first run.

---

## Story E1-S1: Relocatable data-directory resolver

| Field | Value |
|-------|-------|
| **Dependencies** | None |
| **Unblocks** | E1-S2, E2-S1, E6-S1, E11-S1 |
| **Track** | Foundation |
| **Domain** | Config |
| **Estimate** | S |
| **Status** | Complete (shipped) |

**As a** self-custody technical holder,
**I want** all runtime files resolved from `$DOMDHI_CRYPTO_HOME` (or the CWD),
**So that** I can point the tool at an Obsidian vault or any folder I choose.

### Acceptance Criteria

- [x] Given `$DOMDHI_CRYPTO_HOME` is set, When any path helper resolves a file, Then it is under that folder. *(FR-15)*
- [x] Given `$DOMDHI_CRYPTO_HOME` is unset, When a path helper resolves a file, Then it falls back to `Path.cwd()`.
- [x] Given the codebase, When searched, Then file locations come only from `paths.*` constants/helpers — no other module hard-codes a runtime filename. *(NFR-M1)*

### Tasks

- [x] Resolve the data directory from `$DOMDHI_CRYPTO_HOME` when the variable is set, returning a path under that folder.
- [x] Fall back to `Path.cwd()` for the data directory when `$DOMDHI_CRYPTO_HOME` is unset.
- [x] Expose fixed-filename helpers for config, holdings, the SQLite DB, and the dashboard HTML, each joined onto the resolved directory.
- [x] Ensure no other module hard-codes a runtime filename — every location flows through `paths.*`. *(NFR-M1)*

### Files

- `src/domdhi_crypto/paths.py`

> **Note:** Phase 4 story **E11-S1** adds the missing dedicated test for this file (read-only over `paths.py` itself; it owns a *new* test file, no source overlap).

---

## Story E1-S2: Fail-fast config/holdings loading with copy-the-example errors

| Field | Value |
|-------|-------|
| **Dependencies** | E1-S1 |
| **Unblocks** | E3-S1 |
| **Track** | Foundation |
| **Domain** | Config |
| **Estimate** | S |
| **Status** | Complete (shipped) |

**As a** self-custody technical holder,
**I want** missing/placeholder config to fail with an exact fix-it message,
**So that** first-run setup mistakes are obvious instead of producing a traceback.

### Acceptance Criteria

- [x] Given no `coins.local.json`, When a command needs holdings, Then `SystemExit` names `coins.example.json → coins.local.json` as the fix. *(FR-16)*
- [x] Given no `config.local.json`, an empty `api_key`, or a key containing `"PASTE"`, When credentials load, Then `SystemExit` tells the user to copy the example / set the key. *(FR-7)*
- [x] Given valid files, When a command runs, Then current file contents are read fresh each run (no caching). *(FR-16)*

### Tasks

- [x] Raise `SystemExit` naming `coins.example.json → coins.local.json` as the fix when holdings are needed but `coins.local.json` is absent. *(FR-16)*
- [x] Raise `SystemExit` with copy-the-example / set-the-key guidance when `config.local.json` is missing, `api_key` is empty, or the key contains `"PASTE"`. *(FR-7)*
- [x] Read config/holdings file contents fresh on each run with no caching. *(FR-16)*
- [x] Ship `config.example.json` and `coins.example.json` as the templates users copy.

### Files

- `src/domdhi_crypto/coingecko.py` (`load_config`)
- `config.example.json`
- `coins.example.json`

> **Note:** `load_coins` (the `coins.local.json` side of FR-16) lives in `cli.py` and is exercised under Epic 2 / Epic 4; `coingecko.py` here owns only the `config.local.json` credential side.

---

## Validation

| Gate | Command | State |
|------|---------|-------|
| Build / Lint | `ruff check src tests` | ✅ passing |
| Test | `pytest` | ✅ passing (27 tests; `paths.py`-dedicated test added later under E11-S1) |

---

## Work Document References

- Backlog (source of truth): [_backlog.md](_backlog.md) — Phase 0 › Epic 1
- Parent index: [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
- PRD: [../_project-requirements.md](../_project-requirements.md) — FR-7, FR-15, FR-16, NFR-M1
- Architecture: [../_project-architecture.md](../_project-architecture.md)

---

## Dependencies to Next

- **E2-S1 (Idempotent four-table schema init)** depends on E1-S1 — the schema initializer resolves the `crypto.db` location through `paths.*`.
- **E3-S1 (Tiered demo/pro client wiring)** depends on E1-S2 — the CoinGecko client is constructed from the credentials `load_config` validates.
- **E6-S1 (Offline HTML dashboard)** depends on E1-S1 — the dashboard output path resolves through `paths.*`.
- **E11-S1 (Dedicated `paths.py` test, Phase 4)** depends on E1-S1 — it pins the resolver contract this epic established.
