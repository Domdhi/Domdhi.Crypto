# Cycle 1 Summary — Domdhi.Crypto (MVP: portfolio + TA engine)

**Closed:** 2026-06-06  ·  **Span:** 2026-06-05 → 2026-06-06  ·  **Stamp:** 260606-1214
**Completion:** 130 done / 0 open / 0 deferred / 0 blocked  (**100%**)

> Self-contained close-out record for cycle 1. The full backlog, master index, per-epic checklists, and the cycle's `_project-brief.md` + `_project-requirements.md` snapshots live alongside this file in the archive.

## What shipped

The complete local-first crypto portfolio + technical-analysis engine (`CoinGecko → SQLite → hand-rolled TA → offline HTML dashboard`), delivered as one MVP commit plus a test/release-hardening epic:

- **Epic 0 — Packaging & Bootstrap** (22 tasks): src-layout package, `domdhi-crypto` console script, ruff + pytest gate, 3.11/3.12/3.13 CI matrix.
- **Epic 1 — Paths & Config** (14): relocatable data-dir resolver, fail-fast copy-the-example config loading.
- **Epic 2 — SQLite Storage** (15): idempotent four-table schema, upsert ingestion, gap-filled daily close series.
- **Epic 3 — CoinGecko Client** (12): tiered demo/pro wiring, 429 backoff, polite pacing.
- **Epic 4 — Ingest Orchestration** (15): subcommand CLI, id/symbol resolution, per-coin failure isolation + stablecoin skip.
- **Epic 5 — Indicators & Signals** (17): hand-rolled RSI/MACD/Bollinger/ATR/vol + `analyze`/`_signals` (NaN on partial windows).
- **Epic 6 — Offline HTML Dashboard** (9): single-file inline-SVG dashboard, fully offline.
- **Epic 7 — Terminal Reports** (14): `ta <symbol>` + `report` readouts.
- **Epic 11 — Test & Release Hardening** (12): `tests/test_paths.py` (E11-S1), `--version` path (E11-S2), `tests/test_cli.py` (E11-S3), CI `--group dev` install (E11-S4). 27 → **38 tests**.
- **Triage intake** (post-MVP): T.1 (CLAUDE.md stale-gate-note fix) + T.2 (backlog status reconcile), both done.

Headline commits: `e860239` (MVP pipeline) · `d918d57`/`2fb9fe4`/`ecdb48d` (Epic 11) · `f72a6cc` (/end — Epic 11 complete, repo published).

## What production is telling us  (from /listen intake 2026-06-06 + this session's research)

- The original 4 signals were resolved: fixture path leak (killed — accepted), CLAUDE.md stale gate note (fixed, T.1), transient sub-second gate failures (deferred — revisit if recur), backlog status drift (fixed, T.2).
- **The dominant new signal is strategic, not a bug:** market/prior-art research (Ghostfolio, Freqtrade/Jesse, Moon Dev, nof1 Alpha Arena, HammerGPT) converged on a clear next direction — pivot from "portfolio + TA tool" to a **local-first, agent-native crypto decision cortex.** Captured in full in `docs/todo/_feature-ideas.md` (13 ideas across 7 categories) and the project memory store.

## Lessons  (from 1 retro — template-validation, thin on product retros)

- The only retro present is `retro-template-validation.md` (Domdhi.Agents harness validation), so product-level lessons are thin. Relevant carry-overs:
  - **Hand-rolled TA (ADR-001) is an asset, not just a cost** — its auditability becomes the differentiator for an agent that must *cite why* a signal fired.
  - **Gate false-green (C11)** and the look-ahead-bias trap reinforce: cycle 2's edge-validation work must verify computations rigorously (no 0-collected false greens; no future-data leakage).

## Carried forward to cycle 2

- **Deferred (triage ledger):** transient sub-second `gate:test` failures — revisit only if they recur.
- **Feature-ideas (the cortex roadmap):** Signal Substrate (expression-factor registry + IC/ICIR), Edge Validation (look-ahead-safe backtester + attribution), Agent Decision Interface (MCP), Output Channel (alerts/digest), thin Portfolio Context, the "Alpha Arena for one" capstone, and a gated execution adapter (deferred to a later version).
- **Unfinished, carried forward (`--force`):** none — cycle closed at 100%, no override used.
