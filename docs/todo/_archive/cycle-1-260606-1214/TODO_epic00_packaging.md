# TODO — Epic 0: Packaging & Project Bootstrap

| Field | Value |
|-------|-------|
| **Parent** | [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md) |
| **Phase** | Phase 0 — Foundation & Configuration |
| **Status** | Complete (shipped) |
| **Stories** | E0-S1, E0-S2 |
| **Last Updated** | 2026-06-06 |

---

## Executive Summary

Epic 0 is the opening move of the whole project: a pip-installable, src-layout Python package that exposes the `domdhi-crypto` console script, plus the lint + test quality gate that runs on every push across Python 3.11/3.12/3.13. Nothing else in the backlog can be built, run, or verified until this foundation exists — it is the center of the board.

This epic is **brownfield**: both stories already shipped at commit `ad85772` and are recorded here for traceability and verification, not re-implementation. The package installs, the console script resolves, and the CI matrix is green against 27 passing tests. A wave that picks this epic up treats it as a verification/no-op unless a regression is found.

### Key Deliverables

- A PEP 621 / hatchling src-layout package (`src/domdhi_crypto`) installable via `pip install -e .`.
- A `domdhi-crypto` console script resolving to `domdhi_crypto.cli:main`, with an identical `python -m domdhi_crypto` entry point.
- Runtime dependencies deliberately limited to `requests` / `pandas` / `numpy` (no `pandas-ta`, no web framework, no ORM).
- A GitHub Actions CI matrix (3.11/3.12/3.13) running `ruff check .` then `pytest`.
- A `ruff.toml` pinning line-length 110, target py311, rules `E/F/W/I/UP/B` — and a gate that is ruff + pytest only (no mypy, no format-check).

---

## Optimization Summary

These are shipped, low-complexity foundation stories (S and M). There is **no critical-path concern to optimize** — the work is already done and verified. Ordering within the epic is the only structural note: E0-S1 (the package) must precede E0-S2 (the gate that installs and tests that package), and that edge is already respected. No parallelization, splitting, or resequencing is required.

---

## Execution Log

| Date | Story | Event |
|------|-------|-------|
| (pre-2026-06-06) | E0-S1 | Shipped — src-layout package + console entry point landed at commit `ad85772`. |
| (pre-2026-06-06) | E0-S2 | Shipped — CI matrix + ruff/pytest quality gate landed at commit `ad85772`. |
| 2026-06-06 | — | Epic checklist generated for brownfield traceability; all tasks recorded complete. |

---

## Key Decisions

- **No `pandas-ta`, no heavy frameworks.** Runtime deps are pinned to `requests`/`pandas`/`numpy` to keep the portability promise installable on a clean Python 3.11+ across all three matrix versions.
- **hatchling + src-layout + PEP 621.** Single declarative `pyproject.toml` build, with the wheel target scoped to `src/domdhi_crypto`.
- **Two entry points, one handler.** Both the `domdhi-crypto` console script and `python -m domdhi_crypto` funnel through `cli:main` so behavior is identical regardless of invocation.
- **Gate is ruff + pytest only.** No mypy step and no `ruff format --check` step in CI (ADR-006 / NFR-Q4). This is intentional and must not be "polished" into existence.

---

## AI Task Management Protocol

- Work the checklist top-down within each story; respect the intra-epic order E0-S1 → E0-S2.
- Each `[ ]` is a discrete, verifiable unit; flip to `[x]` only when its acceptance evidence holds.
- Acceptance Criteria below are copied verbatim from `docs/todo/_backlog.md` (the source of truth) — do not edit them here; if reality diverges, fix the backlog first.
- This epic is shipped/inert: do not re-dispatch as live work. If a regression is found, open a new story rather than reopening these.

### Key Legend

- `[ ]` — Not started
- `[~]` — In progress
- `[x]` — Complete
- `[!]` — Blocked

---

## Context

Domdhi.Crypto is a self-hosted, local-first crypto portfolio and technical-analysis engine. The backlog is brownfield — Phases 0–3 are shipped and recorded for FR traceability, Phase 4 is the only open build wave. Epic 0 sits in Phase 0 (Foundation & Configuration) and is the dependency root for every other epic: packaging and the quality gate must exist before paths/config, storage, ingestion, indicators, dashboard, or reports can be built or proven.

Source of truth: [_backlog.md](_backlog.md). This file is a per-epic implementation checklist derived from it.

---

## Story E0-S1: src-layout package + console entry point

| Field | Value |
|-------|-------|
| **Dependencies** | None |
| **Unblocks** | E0-S2, E4-S1 (and transitively the rest of the backlog) |
| **Track** | Foundation |
| **Domain** | Config |
| **Estimate** | S |
| **Status** | Complete (shipped) |

**As a** self-custody technical holder,
**I want** to `pip install -e .` and get a `domdhi-crypto` command (and `python -m domdhi_crypto`),
**So that** I can run the whole tool from one entry point on my own machine.

### Acceptance Criteria

- [x] Given the repo, When `pip install -e .` runs, Then a `domdhi-crypto` console script is installed and resolves to `domdhi_crypto.cli:main`.
- [x] Given the installed package, When `python -m domdhi_crypto <cmd>` runs, Then it behaves identically to the console script (`__main__.py` → `cli.main`).
- [x] Given `pyproject.toml`, When inspected, Then it declares PEP 621 metadata, hatchling build backend, the `src/domdhi_crypto` wheel target, and runtime deps limited to `requests`/`pandas`/`numpy`. *(FR-1, NFR-PO2)*

### Tasks

- [x] Declare PEP 621 project metadata and the hatchling build backend in `pyproject.toml`.
- [x] Scope the wheel build target to `src/domdhi_crypto` (src-layout).
- [x] Limit runtime dependencies to `requests` / `pandas` / `numpy`.
- [x] Register the `domdhi-crypto` console script entry point resolving to `domdhi_crypto.cli:main`.
- [x] Provide `src/domdhi_crypto/__init__.py` for the package.
- [x] Provide `src/domdhi_crypto/__main__.py` so `python -m domdhi_crypto` routes to `cli.main`.
- [x] Verify `pip install -e .` installs the console script and both entry points behave identically.

**Files:** `pyproject.toml`, `src/domdhi_crypto/__init__.py`, `src/domdhi_crypto/__main__.py`

---

## Story E0-S2: CI matrix + ruff/pytest quality gate

| Field | Value |
|-------|-------|
| **Dependencies** | E0-S1 |
| **Unblocks** | E11-S4 |
| **Track** | Foundation |
| **Domain** | DevOps |
| **Estimate** | M |
| **Status** | Complete (shipped) |

**As a** maintainer,
**I want** lint + tests to run on every push/PR across Python 3.11/3.12/3.13,
**So that** the no-`pandas-ta` portability promise stays provably green.

### Acceptance Criteria

- [x] Given a push to `master` or a PR, When CI runs, Then a matrix over Python 3.11/3.12/3.13 installs the package and runs `ruff check .` then `pytest`. *(NFR-PO1, NFR-Q1, NFR-Q2)*
- [x] Given `ruff.toml`, When inspected, Then it pins line-length 110, target py311, rules `E/F/W/I/UP/B`.
- [x] Given the CI config, When inspected, Then there is no mypy step and no `ruff format --check` step (gate is ruff + pytest only). *(NFR-Q4, ADR-006)*

### Tasks

- [x] Add a GitHub Actions workflow triggered on push to `master` and on PRs.
- [x] Configure a Python matrix over 3.11 / 3.12 / 3.13.
- [x] Install the package and run `ruff check .` then `pytest` in each matrix leg.
- [x] Add `ruff.toml` pinning line-length 110, target py311, and rules `E/F/W/I/UP/B`.
- [x] Confirm the gate is ruff + pytest only — no mypy step, no `ruff format --check` step.
- [x] Wire `.pre-commit-config.yaml` to mirror the ruff gate for local runs.

**Files:** `.github/workflows/ci.yml`, `ruff.toml`, `.pre-commit-config.yaml`

---

## Validation

- [x] **Build / Lint:** `ruff check src tests` passes.
- [x] **Test:** `pytest` passes (27 tests, network mocked).
- [x] All E0-S1 and E0-S2 acceptance criteria verified against the shipped code at commit `ad85772`.

---

## Work Document References

- Source of truth backlog: [_backlog.md](_backlog.md)
- PRD: [../_project-requirements.md](../_project-requirements.md)
- Architecture: [../_project-architecture.md](../_project-architecture.md)
- Parent rollup: [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)

---

## Dependencies to Next

- **E0-S1 → E0-S2**: the quality gate installs and tests the package the entry-point story creates.
- **E0-S1 → E4-S1** (Phase 1, Ingest Orchestration): the subcommand-driven CLI depends on the console entry point.
- **E0-S2 → E11-S4** (Phase 4, Test & Release Hardening): the open story that aligns CI's dev-tool install with the declared `dev` group builds directly on this epic's CI file.
- Transitively, every other epic in Phases 0–4 depends on this packaging foundation existing first.
