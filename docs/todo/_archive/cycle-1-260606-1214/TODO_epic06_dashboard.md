# TODO — Epic 6: Offline HTML Dashboard

**Parent:** [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
**Phase:** 3 — Dashboard & Reporting
**Status:** Complete (shipped)
**Stories:** E6-S1
**Last Updated:** 2026-06-06

---

## Executive Summary

Epic 6 delivers the project's primary visual surface: a single self-contained `dashboard.html` that an owner can open straight from disk with no network, no server, no CDN, and no JavaScript framework. All data is baked into the file at build time. This is the apex of the rendering layer — it consumes the gap-filled close series (Epic 2), the signal layer (Epic 5), and the path/config resolver (Epic 1), and turns them into a portfolio-at-a-glance report.

This epic is **brownfield / already-shipped**. The code exists at commit `ad85772`, works end-to-end, and is exercised by the standing test suite. Every task below is recorded `[x]` for traceability — completing this checklist is a verification pass, not a re-implementation. A wave that picks it up should treat it as a no-op unless a regression surfaces.

### Key Deliverables

- **`dashboard.py`** — single-command builder that writes one self-contained offline `dashboard.html` and returns its path.
- **Inline SVG price charts** — per-coin price line with SMA20 / SMA50 / SMA200 overlays, drawn as inline SVG (no chart library, no external assets).
- **RSI strip** — per-coin RSI sub-chart rendered alongside the price chart.
- **Allocation bars** — portfolio allocation visualized as horizontal bars.
- **Holdings table** — per-coin rows with profit/loss and a 90-day price sparkline.
- **Dark theme** — fully inlined styling; no external stylesheet link.
- **`--open` flag** — builds the file and launches it via `webbrowser`.
- **Fail-fast on missing `coins.local.json`** — `SystemExit` with the copy-the-example fix.

---

## Optimization Summary

This epic is positioned at the end of Phase 3 because it is a pure consumer — it depends on a populated DB, the daily close series, and the signal layer all being in place, and it unblocks nothing downstream (the terminal reports of Epic 7 are a sibling rendering path, not a dependent). Placing it after Epics 2 and 5 means it never blocks parallel work. As the only story in the epic, sized **L**, it bundles several rendering concerns (cards, allocation, holdings, charts, RSI) into one self-contained file; the deliberate "no external assets" constraint (ADR-004) is what makes the single-file approach correct rather than a chart-library integration. No decomposition was required because the file is cohesive and ships green.

---

## Execution Log

| Date | Story | Event |
|------|-------|-------|
| (pre-`ad85772`) | E6-S1 | Implemented and shipped — `dashboard.py` builds offline `dashboard.html` with inline SVG, allocation, holdings + P/L, RSI strip, dark theme. |
| 2026-06-06 | E6-S1 | Recorded in per-epic checklist for traceability; status confirmed Complete (shipped). |

---

## Key Decisions

- **Single self-contained file (ADR-004 / NFR-PR3 / NFR-PO3).** Everything is baked into `dashboard.html` — no `<script src=…>` CDN reference and no external stylesheet link — so the report opens fully offline from disk. This is a hard constraint, not a preference.
- **Inline SVG over a charting library.** Price+SMA overlays, the RSI strip, and the 90-day sparkline are hand-drawn SVG, keeping the dependency surface limited to `requests`/`pandas`/`numpy` and preserving the no-framework promise.
- **Consumer-only positioning.** E6-S1 sits at the rendering apex of the import graph and depends on E2-S3, E5-S2, and E1-S1; it owns its own file (`dashboard.py`) with no overlap.
- **Stablecoins still count toward value.** Pegged assets are skipped for history/signals upstream but their `amount × price` is included in portfolio value here (consistent with FR-4).

---

## AI Task Management Protocol

- Work one story at a time, top to bottom within the story's task list.
- Mark a task `[x]` only when its slice is implemented and the story's validation commands pass.
- Do not mark a story Complete until every Acceptance Criterion is verifiably met.
- This epic is shipped/inert: treat task execution as verification. If a check fails, that is a regression — stop and report it rather than silently rewriting shipped behavior.
- Respect file ownership: this epic owns `src/domdhi_crypto/dashboard.py` only.

### Key legend

- `[ ]` — not started
- `[~]` — in progress
- `[x]` — complete
- `[!]` — blocked

---

## Context

Domdhi.Crypto is a self-hosted, local-first crypto portfolio and technical-analysis engine. Phase 3 (Dashboard & Reporting) renders results two ways: this epic's offline HTML/SVG dashboard, and Epic 7's terminal reports. Epic 6 is the visual report — one file, all data inlined, openable offline. It reads the gap-filled daily close series and OHLC from SQLite, the per-coin signals from the analysis layer, and the holdings/paths from config, then writes `dashboard.html` to the resolved data directory.

---

## Story E6-S1: Single-file offline HTML/SVG dashboard

- **Dependencies:** E2-S3 (gap-filled daily close series), E5-S2 (signal generation rules), E1-S1 (relocatable data-directory resolver)
- **Unblocks:** None (terminal reports in Epic 7 are a sibling rendering path, not a dependent)
- **Track:** Phase 3 — Dashboard & Reporting
- **Domain:** Frontend
- **Estimate:** L

**As a** self-custody technical holder,
**I want** one `dashboard.html` with all data baked in,
**So that** I can open it from disk with no network, server, CDN, or JS framework.

### Acceptance Criteria

- Given a populated `crypto.db` and `coins.local.json`, When `dashboard` runs, Then a single `dashboard.html` is written and its path returned. *(FR-13)*
- Given the file, When opened from disk offline, Then all cards, allocation bars, holdings table, and every chart render (data baked in). *(NFR-PR3, NFR-PO3)*
- Given the file's contents, When inspected, Then there is no `<script src=…>` CDN ref and no external stylesheet link (fully self-contained). *(ADR-004)*
- Given `--open`, When `dashboard --open` runs, Then the file is built and launched via `webbrowser`.
- Given missing `coins.local.json`, When `dashboard` runs, Then `SystemExit` names the copy-the-example fix.

### Tasks

- [x] Build the `dashboard` command path that reads the populated DB and `coins.local.json`, writes a single `dashboard.html`, and returns its path.
- [x] Bake all data inline so the file renders fully offline from disk — no network, server, or CDN dependency.
- [x] Render summary cards and horizontal allocation bars from portfolio holdings and live values.
- [x] Render the holdings table with per-coin profit/loss and a 90-day price sparkline.
- [x] Render per-coin inline-SVG price charts with SMA20 / SMA50 / SMA200 overlays.
- [x] Render the per-coin RSI strip alongside each price chart.
- [x] Apply the dark theme with fully inlined styles — no external stylesheet link and no `<script src=…>` CDN reference.
- [x] Wire the `--open` flag to build the file and launch it via `webbrowser`.
- [x] Fail fast with `SystemExit` naming the copy-the-example fix when `coins.local.json` is missing.

### Validation

- **Build / Lint:** `ruff check src tests`
- **Test:** `pytest`

### Work Document References

- Backlog (source of truth): [_backlog.md](./_backlog.md) — Epic 6, Story E6-S1
- PRD: [../_project-requirements.md](../_project-requirements.md) — FR-13
- Architecture: [../_project-architecture.md](../_project-architecture.md) — ADR-004 (self-contained offline file)

---

## Dependencies to Next

- **Epic 7 (Terminal Reports)** is a sibling rendering path in the same phase — it does not depend on this epic and can render independently.
- This epic unblocks no downstream story; it is a terminal consumer at the apex of the rendering layer.
- File ownership: this epic owns `src/domdhi_crypto/dashboard.py` exclusively — no overlap with any other epic.
