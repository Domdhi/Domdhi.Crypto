# TODO — Epic 11: Test & Release Hardening

**Parent:** [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
**Phase:** 4 — Polish & Gaps
**Status:** Complete — 4 / 4 (E11-S1, E11-S2, E11-S3, E11-S4 ✅)
**Stories:** E11-S1, E11-S2, E11-S3, E11-S4
**Last Updated:** 2026-06-06

---

## Executive Summary

Epic 11 closes the real, validated gaps left after Phases 0–3 shipped. The shipped pipeline's runtime behavior does not change; this epic only hardens tests and release ergonomics. It adds a dedicated `paths.py` unit test, surfaces the installed package version via a `--version` CLI path, pins that path (plus the existing coin resolver) with a focused CLI helper test, and aligns CI's dev-tool install with the project's single declared `dev` dependency group.

This is the **only epic with genuinely open work** in the backlog. Phases 0–3 are recorded for FR traceability only and are inert. These four stories are real `⬜ todo` work a build wave will implement.

### Key Deliverables

- **E11-S1** — New `tests/test_paths.py` pinning the data-directory contract (`$DOMDHI_CRYPTO_HOME` vs CWD, fixed filenames).
- **E11-S2** — `domdhi-crypto --version` path in `cli.py`, sourcing the version from package metadata (single source of truth).
- **E11-S3** — New `tests/test_cli.py` covering the `_resolve` helper and the version resolver introduced by E11-S2.
- **E11-S4** — CI `ci.yml` install step aligned to the PEP 735 `[dependency-groups] dev` group, with the quality gate held to ruff + pytest only.

---

## Optimization Summary

- **Critical path:** E11-S2 → E11-S3. E11-S3 tests the version resolver that E11-S2 introduces, so S3 must land after S2.
- **Parallel tracks:** E11-S1 (Track A) and E11-S4 (Track C) are independent and can run fully in parallel with each other and with E11-S2 (Track B).
- **cli.py sequencing (wave safety):** E11-S2 modifies `src/domdhi_crypto/cli.py` and E11-S3 tests the helper it introduces. Even though E11-S3 only *adds* a new test file, the dependency edge (E11-S3 → E11-S2) keeps them sequenced. **E11-S2 and E11-S3 must NOT be dispatched in the same parallel wave.**

### Recommended lead order

1. Lead wave (parallel): **E11-S1** (Track A), **E11-S2** (Track B), **E11-S4** (Track C).
2. Follow wave: **E11-S3** (after E11-S2 completes).

---

## Execution Log

| Date | Story | Event | Notes |
|------|-------|-------|-------|
| 2026-06-06 | — | Epic checklist created | All four stories Not Started. |
| 2026-06-06 | E11-S1 | Completed (`/do`) | `tests/test_paths.py` added (5 tests); suite 27→32. AC verified by direct `pytest` run — the gate could not verify it (build leg fails on pre-existing ruff-format+mypy debt, C1–C3; test leg false-greens on `-q` output, C11). |
| 2026-06-06 | E11-S2 | Completed (`/run-todo` W1) | `_version()` helper + `--version` argparse path in `cli.py`. AC verified live: `domdhi-crypto --version` → `domdhi-crypto 0.1.0` (exit 0); version single-sources from package metadata == pyproject `0.1.0`; no-arg invocation still exits 2 (required subparser intact). Gate GREEN (build PASS, 32 tests). |
| 2026-06-06 | E11-S4 | Completed (`/run-todo` W1) | `ci.yml` install step switched to PEP 735 `--group dev` (drops hand-listed `pip install pytest ruff`). Gate kept ruff+pytest only — no mypy/format-check added. AC1/AC2 are CI-runtime (verified by inspection; `--group` needs pip ≥25.1, satisfied by the `--upgrade pip` step). |
| 2026-06-06 | E11-S3 | Completed (`/run-todo` W2) | `tests/test_cli.py` added (6 tests): `_resolve` by symbol/id/case/miss + `_version()` == package metadata. Suite 32→38, all green. Sequenced after E11-S2 per the shared-`cli.py` edge. |

---

## Key Decisions

- **Quality gate stays ruff + pytest only.** Per ADR-006 / NFR-Q4, no mypy step and no ruff-format-check step may be added to CI. E11-S4 keeps the gate as-is and is explicitly forbidden from broadening it.
- **Version is single-sourced.** E11-S2 reads the version from package metadata (`importlib.metadata.version("domdhi-crypto")`) so it equals `pyproject.toml`'s `[project].version` — never a hard-coded duplicate.
- **Tests are additive.** New tests must not remove or alter existing ones; the passing-test count increases from the current 27.

---

## AI Task Management Protocol

- Work stories in dependency-optimized order. Do not start a story whose dependencies are unmet.
- Never dispatch E11-S2 and E11-S3 in the same parallel wave (shared `cli.py` surface; sequenced by dependency edge).
- Mark a task `[x]` only when its acceptance criteria are verifiably met.
- Run the validation commands before marking a story complete.
- Do not broaden scope: each story owns exactly the file(s) named in its section.

### Key Legend

- `[ ]` — pending / not started
- `[x]` — complete
- `[~]` — in progress
- `[!]` — blocked

---

## Context

### Dependencies

- **E11-S3 → E11-S2** (intra-epic): E11-S3 tests the version resolver E11-S2 introduces; sequence S3 after S2, never same wave.
- E11-S1 depends on shipped **E1-S1** (relocatable data-directory resolver — inert).
- E11-S2 depends on shipped **E4-S1** (subcommand-driven CLI workflow — inert).
- E11-S3 depends on **E11-S2** and shipped **E4-S2** (coin resolution by id/symbol — inert).
- E11-S4 depends on shipped **E0-S2** (CI matrix + quality gate — inert).

### Critical Rules

- **Quality gate stays ruff + pytest only** — no mypy step, no format-check step (ADR-006 / NFR-Q4).
- **Zero same-wave file overlap.** E11-S2 and E11-S3 both relate to `cli.py`; the dependency edge keeps them sequenced.
- **No runtime behavior change** to the shipped pipeline.

---

## Story E11-S1: Add a dedicated `paths.py` unit test

- **Dependencies:** E1-S1 (shipped, inert)
- **Unblocks:** Nothing further in Epic 11 (leaf story).
- **Track:** A (independent — parallel-safe)
- **Domain:** Test
- **Estimate:** S

**As a** maintainer,
**I want** `paths.py` covered by its own test file,
**So that** the data-directory contract (`$DOMDHI_CRYPTO_HOME` vs CWD, fixed filenames) is pinned like the other core modules.

### Acceptance Criteria

- Given a new `tests/test_paths.py`, When `pytest` runs, Then it passes and exercises `paths` only (no network, no real filesystem writes outside `tmp_path`/monkeypatched env).
- Given `monkeypatch.setenv("DOMDHI_CRYPTO_HOME", tmp)`, When `data_dir()` is called, Then it returns `Path(tmp)`; with the env unset, When called, Then it returns `Path.cwd()`. *(FR-15)*
- Given each path helper, When called, Then `config_path`/`coins_path`/`db_path`/`dashboard_path` join the resolved dir with the correct fixed filename constant.
- Given the suite, When run, Then total passing tests increase from 27 (new tests are additive, none removed).

### Tasks

- [x] Add the new test module `tests/test_paths.py` covering the data-directory resolution contract (env-set vs env-unset).
- [x] Cover each path helper against its correct fixed filename constant, using `tmp_path` / monkeypatched env only (no network, no real FS writes).
- [x] Confirm the suite remains additive — existing tests untouched, total passing count increases from 27.

---

## Story E11-S2: Add a `--version` / version-display path

- **Dependencies:** E4-S1 (shipped, inert)
- **Unblocks:** E11-S3 (the helper test that covers this story's version resolver)
- **Track:** B (critical path — leads, then E11-S3 follows)
- **Domain:** Backend
- **Estimate:** S

**As a** self-custody technical holder,
**I want** `domdhi-crypto --version` to print the installed package version,
**So that** I can confirm which build I'm running when reporting an issue.

### Acceptance Criteria

- Given the installed package, When `domdhi-crypto --version` runs, Then it prints the version from package metadata (e.g. `importlib.metadata.version("domdhi-crypto")`) and exits `0`.
- Given the version source, When inspected, Then the displayed version equals `pyproject.toml`'s `[project].version` (single source of truth — not a hard-coded duplicate). *(FR-1)*
- Given `--version` is added, When any existing subcommand runs, Then behavior is unchanged (argparse `required=True` subparser still applies to non-version invocations).

### Tasks

- [x] In `src/domdhi_crypto/cli.py`, add a `--version` path to `main` that prints the version sourced from package metadata and exits `0`.
- [x] Ensure the displayed version single-sources from `pyproject.toml`'s `[project].version` (no hard-coded duplicate).
- [x] Verify existing subcommands are unaffected — `required=True` subparser still applies to non-version invocations.

---

## Story E11-S4: Align CI dev-tool install with the declared `dev` group

- **Dependencies:** E0-S2 (shipped, inert)
- **Unblocks:** Nothing further in Epic 11 (leaf story).
- **Track:** C (independent — parallel-safe)
- **Domain:** DevOps
- **Estimate:** S

**As a** maintainer,
**I want** CI to install dev tools from the PEP 735 `dev` group instead of an ad-hoc `pip install pytest ruff`,
**So that** the build bar matches the project's single declared dependency source (no version drift between CI and local).

### Acceptance Criteria

- Given `.github/workflows/ci.yml`, When the install step runs, Then dev tools come from the declared `[dependency-groups] dev` (e.g. `pip install --group dev` / `uv sync`) rather than a hand-listed `pip install pytest ruff`.
- Given the change, When CI runs on 3.11/3.12/3.13, Then `ruff check .` and `pytest` still run and the matrix stays green (no mypy step, no format-check step added). *(NFR-PO1, NFR-Q1, NFR-Q2, ADR-006)*
- Given the diff, When reviewed, Then it is scoped to the install step only — no new gate, no new dependency added to the `dev` group.

### Tasks

- [x] In `.github/workflows/ci.yml`, switch the dev-tool install step to source from the declared `[dependency-groups] dev` group instead of a hand-listed `pip install pytest ruff`.
- [x] Keep the gate at ruff + pytest only across the 3.11/3.12/3.13 matrix — **do NOT add a mypy step or a ruff-format-check step** (ADR-006 / NFR-Q4).
- [x] Confirm the diff is scoped to the install step only — no new gate, no new dependency added to the `dev` group.

---

## Story E11-S3: Focused helper test for `cli.py`

- **Dependencies:** E11-S2 (must complete first — same `cli.py` surface, sequenced), E4-S2 (shipped, inert)
- **Unblocks:** Nothing further in Epic 11 (leaf story).
- **Track:** B follow-up (runs after E11-S2; NEVER in the same wave as E11-S2)
- **Domain:** Test
- **Estimate:** S

**As a** maintainer,
**I want** a unit test for a pure `cli.py` helper (`_resolve` and/or the `--version` resolver),
**So that** the CLI's id/symbol resolution and version path are pinned without invoking the network.

### Acceptance Criteria

- Given a new `tests/test_cli.py`, When `pytest` runs, Then it passes with no network calls.
- Given a coins list, When `_resolve(coins, "BTC")` and `_resolve(coins, "bitcoin")` are called, Then both return the same coin; `_resolve(coins, "nope")` returns `None`. *(FR-2)*
- Given the version resolver added in E11-S2, When tested, Then it returns the same string as `importlib.metadata.version("domdhi-crypto")`. *(FR-1)*

### Tasks

- [x] Add the new test module `tests/test_cli.py` (depends on E11-S2's resolver — do not start until E11-S2 is complete).
- [x] Cover `_resolve` for id, symbol, and miss cases (`"BTC"` and `"bitcoin"` resolve to the same coin; `"nope"` returns `None`), with no network calls.
- [x] Cover the version resolver introduced by E11-S2 against `importlib.metadata.version("domdhi-crypto")`.

---

## Validation

- **Build:** `ruff check src tests` — must pass clean.
- **Test:** `pytest` — full suite must pass; new tests (`tests/test_paths.py`, `tests/test_cli.py`) must pass and the total passing count must increase from 27 (additive only).
- The quality gate stays ruff + pytest only — no mypy, no format-check step is introduced by this epic.

---

## Work Document References

- **Backlog (source of truth):** [docs/todo/_backlog.md](./_backlog.md) — Phase 4, Epic 11, stories E11-S1..E11-S4.
- **Parent checklist:** [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
- **Architecture / ADRs:** `docs/_project-architecture.md` (ADR-006 — quality gate scope).
- **Requirements:** `docs/_project-requirements.md` (FR-1, FR-2, FR-15; NFR-Q1/Q2/Q4, NFR-PO1).

---

## Dependencies to Next

Epic 11 is Phase 4, the final and only live build wave. No downstream epic depends on its completion. Completing all four stories closes the validated test-and-release gaps and leaves the quality gate intact (ruff + pytest only).
