# Implementation Index — Domdhi.Crypto

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Generated** | 2026-06-06 |
| **Source of truth** | [todo/_backlog.md](todo/_backlog.md) |
| **Status** | Brownfield — Phases 0–3 shipped, Phase 4 open |
| **Scope** | 5 phases · 9 epics · 21 stories (17 shipped · 4 todo) |

> PM-level epic index. Story-level checkboxes live in the per-epic checklist files
> under [`todo/`](todo/). This file tracks **epics and phases only**.

---

## Phase Map

| Phase | Name | Goal | Epics | Stories | Done | Status |
|-------|------|------|-------|---------|------|--------|
| 0 | Foundation & Configuration | Packaging, path/config resolver, idempotent SQLite schema — the foundation every module depends on | 3 | 7 | 7 | ✅ shipped |
| 1 | Data & Core Ingestion | CoinGecko client (demo/pro, backoff) + ingest orchestration with per-coin failure isolation | 2 | 5 | 5 | ✅ shipped |
| 2 | Technical Analysis | Hand-rolled auditable indicators and the signal rules that turn them into plain-language calls | 1 | 2 | 2 | ✅ shipped |
| 3 | Dashboard & Reporting | Offline self-contained HTML/SVG dashboard + terminal TA and portfolio reports | 2 | 3 | 3 | ✅ shipped |
| 4 | Polish & Gaps | Close validated gaps: `paths.py` test, `--version` path + CLI helper test, CI `dev`-group install | 1 | 4 | 1 | 🔄 in progress |
| **Total** | | | **9** | **21** | **17** | **4 todo** |

---

## Epic Index

| Epic | Title | Stories | Est. (h) | Status | Checklist |
|------|-------|---------|----------|--------|-----------|
| 0 | Packaging & Project Bootstrap | 2 | ~2 | [x] | [todo/TODO_epic00_packaging.md](todo/TODO_epic00_packaging.md) |
| 1 | Paths & Config Resolution | 2 | ~2 | [x] | [todo/TODO_epic01_paths-config.md](todo/TODO_epic01_paths-config.md) |
| 2 | SQLite Schema & Idempotent Storage | 3 | ~4 | [x] | [todo/TODO_epic02_storage.md](todo/TODO_epic02_storage.md) |
| 3 | CoinGecko Client | 2 | ~3 | [x] | [todo/TODO_epic03_coingecko.md](todo/TODO_epic03_coingecko.md) |
| 4 | Ingest Orchestration | 3 | ~4 | [x] | [todo/TODO_epic04_ingest.md](todo/TODO_epic04_ingest.md) |
| 5 | Indicators & Signals | 2 | ~5 | [x] | [todo/TODO_epic05_indicators.md](todo/TODO_epic05_indicators.md) |
| 6 | Offline HTML Dashboard | 1 | ~3 | [x] | [todo/TODO_epic06_dashboard.md](todo/TODO_epic06_dashboard.md) |
| 7 | Terminal Reports | 2 | ~2 | [x] | [todo/TODO_epic07_reports.md](todo/TODO_epic07_reports.md) |
| 11 | Test & Release Hardening | 4 | ~3 | [x] | [todo/TODO_epic11_hardening.md](todo/TODO_epic11_hardening.md) |

> **ID note:** Epic 11 is the 9th epic but keeps the ID `11` exactly as the backlog
> assigns it. The numbering gap (epics 0–7 then 11) is a known, intentional finding —
> consistency of the ID across all files outweighs renumbering.

---

## Cross-Epic Dependencies

Only real dependencies from the backlog are listed. The dominant structure is the
strict phase ordering (each phase is a capability milestone the next builds on),
plus one intra-Epic-11 sequencing edge driven by shared file ownership.

| Dependency | Type | Reason |
|------------|------|--------|
| Phase 0 → Phase 1 | Phase gate | Ingestion (Epics 3–4) needs the package entry point, config resolver, and SQLite schema from Epics 0–2 |
| Phase 1 → Phase 2 | Phase gate | Indicators (Epic 5) consume the gap-filled close series produced by ingestion + storage |
| Phase 2 → Phase 3 | Phase gate | Dashboard (Epic 6) and reports (Epic 7) render the signals produced by Epic 5 |
| Phase 3 → Phase 4 | Phase gate | Hardening (Epic 11) pins/extends the shipped surface; it runs only after the pipeline is in place |
| Epic 11 (E11-S3 → E11-S2) | Story sequence | E11-S3 tests the `--version` resolver E11-S2 introduces; both relate to `cli.py`, so they MUST be sequenced, never run in the same parallel wave |

> **Within-phase note:** In the live Phase 4 wave, E11-S1 (`tests/test_paths.py`) and
> E11-S4 (`.github/workflows/ci.yml`) own unique files and may run fully in parallel
> with each other and with E11-S2. E11-S3 follows E11-S2 per the edge above.

---

## Optimization

> **`/review:optimize-backlog` has NOT been run on this backlog.**
> Run `/review:optimize-backlog` for a cross-epic optimization pass — parallel-wave
> packing, file-ownership conflict detection across all phases, dependency-graph
> validation, and estimate calibration. Until then, treat the phase/wave ordering
> above as the authoritative sequencing.

---

## Phase Gates

A phase is complete only when every story in its epics meets its acceptance criteria
and the gate condition below holds.

| Phase | Gate condition | State |
|-------|----------------|-------|
| 0 | Package installs (`pip install -e .`), CI matrix green, schema inits idempotently | ✅ met |
| 1 | `ingest` pulls demo/pro data with backoff; per-coin failures isolated; rows persist | ✅ met |
| 2 | Indicators match textbook references within tolerance; signals emit correct calls | ✅ met |
| 3 | `dashboard` writes a self-contained offline HTML; `ta`/`report` print correct readouts | ✅ met |
| 4 | New `paths.py` + `cli.py` tests pass (additive, ≥27 total); `--version` prints from metadata; CI installs from `dev` group; gate stays ruff+pytest | ⬜ open |

---

## Next Steps

1. Generate the per-epic story checklists: **`/create:project-epics-todo all`** —
   this expands every epic above into its `todo/TODO_epicNN_*.md` checklist with
   story-level checkboxes and acceptance criteria.
2. (Optional, recommended) Run **`/review:optimize-backlog`** to add the optimization
   summary this index currently defers.
3. Execute the open Phase 4 wave (Epic 11) once checklists exist.

> Shipped epics (0–7) are recorded for FR traceability and are **inert** — their
> checklists document done work and should not be re-dispatched as live build waves.
