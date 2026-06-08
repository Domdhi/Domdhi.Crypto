# TODO — Epic 2: SQLite Schema & Idempotent Storage

**Parent:** [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
**Phase:** 0 — Foundation & Configuration
**Status:** Complete (shipped)
**Stories:** E2-S1, E2-S2, E2-S3
**Last Updated:** 2026-06-06

---

## Executive Summary

Epic 2 is the storage layer at the center of the Phase 0 board: the four-table SQLite schema, every write made idempotent, and the gap-filled daily close series that the indicators and dashboard consume. It is the single dependency that ingestion (Phase 1), analysis (Phase 2), and reporting (Phase 3) all stand on. This epic is **brownfield — already shipped** at commit `ad85772` and covered by passing unit tests; the checklist below records reality for traceability, not work to be re-implemented. A build wave that picks up any task here treats it as a verification/no-op unless a regression surfaces.

The epic delivers three contracts: (1) re-runnable schema init that never drops data, (2) upserts where re-ingesting overlapping date ranges can never duplicate or corrupt rows, and (3) a read-time series repair that hands rolling-window indicators a calendar-correct, gap-free input without mutating stored rows.

### Key Deliverables

- **`db.py` — four-table schema:** `coins`, `prices`, `ohlc`, `snapshots`, created with `CREATE TABLE IF NOT EXISTS` so init is safe whether the DB is fresh or already populated.
- **`db.py` — ON CONFLICT upserts:** `upsert_coin` / `upsert_prices` / `upsert_ohlc` keyed for idempotent overwrite; `insert_snapshot` as `ON CONFLICT DO NOTHING` on `(coin_id, fetched_at)`.
- **`db.py` — `load_close_series` gap-fill + ffill:** reindex stored prices to a continuous daily calendar and forward-fill, read-time only (raw rows untouched); returns `None` for a coin with no stored prices. Companions `load_ohlc` / `latest_snapshot_price`.

### Optimization Summary

Storage is consolidated in a single leaf module (`db.py`) with a strictly-acyclic import graph: it depends only on `paths` (for the DB location) and stdlib `sqlite3` — no internal dependency on the client, CLI, or TA layers. Idempotency is pushed down to SQL (`ON CONFLICT`) rather than read-modify-write in Python, so overlapping re-ingests are correct and cheap. Gap repair is deferred to read time, keeping the on-disk price table a faithful record of what the API actually returned.

---

## Execution Log

| Date | Story | Action | Result |
|------|-------|--------|--------|
| (pre-2026-06-06) | E2-S1 | Schema init implemented & shipped | Complete (shipped) |
| (pre-2026-06-06) | E2-S2 | Idempotent upserts implemented & shipped | Complete (shipped) |
| (pre-2026-06-06) | E2-S3 | Gap-filled close series implemented & shipped | Complete (shipped) |
| 2026-06-06 | — | Per-epic checklist generated from `_backlog.md` | Recorded for traceability |

---

## Key Decisions

- **Idempotency lives in SQL, not Python.** `ON CONFLICT` upserts make overlapping date-range re-ingestion safe by construction, with no row-count drift. (FR-9, NFR-R1)
- **Snapshots are insert-once.** `insert_snapshot` uses `ON CONFLICT DO NOTHING` on `(coin_id, fetched_at)` so a repeated snapshot is a no-op. (ADR-005)
- **Gap repair is read-time only.** `load_close_series` reindexes to a continuous daily range and forward-fills on read; stored `prices` rows are never mutated. (NFR-R4)
- **`init_db()`/`connect()` accept an explicit path.** Enables `:memory:`/temp-file testing without touching the real `crypto.db`.
- **Single-file storage module, leaf in the import graph.** `db.py` depends only on `paths` + stdlib, keeping the DAG acyclic. (NFR-M1)

---

## AI Task Management Protocol

- This file is the per-epic checklist; `docs/todo/_backlog.md` remains the **source of truth** for stories and acceptance criteria.
- Brownfield epic: all tasks are `[x]` and status is **Complete (shipped)**. Do not re-implement; verify only if a regression is suspected.
- Acceptance criteria below are reproduced **verbatim** from the backlog — do not paraphrase or edit them here.
- If a regression is found, log it in the Execution Log and open a new Phase 4 story rather than mutating a shipped story's contract.

### Key (legend)

- `[x]` — task complete (shipped / verified)
- `[ ]` — task open (none in this epic)
- `(Database)` — domain tag routing the story to the data-access implementation agent
- `S` / `M` / `L` / `XL` — estimate (effort/complexity flag, not a time box)

---

## Context

Epic 2 sits in **Phase 0 — Foundation & Configuration**, alongside packaging (Epic 0) and path/config resolution (Epic 1). Its objective: the four-table schema created idempotently, idempotent upsert ingestion, and the gap-filled daily close series the indicators depend on. All three stories own slices of one physical file, `src/domdhi_crypto/db.py`, with distinct, non-overlapping function surfaces — safe here only because all are shipped/inert, not live parallel-wave work. The whole epic depends on `E1-S1` (the path resolver that locates `crypto.db`).

---

## Story E2-S1: Idempotent four-table schema init

- **Dependencies:** E1-S1
- **Unblocks:** E2-S2, E2-S3 (and transitively all of Phases 1–3)
- **Track:** Foundation / Storage
- **Domain:** (Database)
- **Estimate:** S
- **Status:** Complete (shipped)

**As a** self-custody technical holder,
**I want** `domdhi-crypto init` to create the schema safely whether the DB is fresh or already exists,
**So that** I can re-run setup without fear of dropping data.

### Acceptance Criteria

- Given no DB file, When `init` runs, Then `crypto.db` is created with `coins`, `prices`, `ohlc`, `snapshots`. *(FR-8, test_db)*
- Given an existing schema, When `init_db()` runs again, Then it succeeds without dropping/altering data (`CREATE TABLE IF NOT EXISTS`).
- Given a test, When `connect()`/`init_db()` are called with an explicit path, Then they operate against that path (`:memory:`/temp).

### Tasks

- [x] Define the four-table schema (`coins`, `prices`, `ohlc`, `snapshots`) in `db.py`
- [x] Create tables with `CREATE TABLE IF NOT EXISTS` so re-running `init` never drops or alters data
- [x] Provide `connect()` / `init_db()` accepting an explicit DB path for `:memory:`/temp-file use
- [x] Wire the `init` subcommand to `init_db()` against the resolved `crypto.db` location
- [x] Verify idempotent re-init under test (`test_db`)

---

## Story E2-S2: Idempotent upsert ingestion

- **Dependencies:** E2-S1
- **Unblocks:** E4-S3 (ingest orchestration relies on safe overlapping writes)
- **Track:** Foundation / Storage
- **Domain:** (Database)
- **Estimate:** M
- **Status:** Complete (shipped)

**As a** self-custody technical holder,
**I want** every write to be idempotent,
**So that** re-ingesting overlapping date ranges never duplicates or corrupts rows.

### Acceptance Criteria

- Given an existing `(coin_id, date)` price row, When the same key is upserted, Then the row count is unchanged and values are updated. *(FR-9, NFR-R1, test_db)*
- Given `ingest` run twice over an overlapping range, When the second completes, Then no duplicate `prices`/`ohlc` rows exist.
- Given an existing `(coin_id, fetched_at)` snapshot, When re-inserted, Then it is a no-op (`ON CONFLICT DO NOTHING`). *(ADR-005)*

### Tasks

- [x] Implement `upsert_coin` with conflict-keyed overwrite
- [x] Implement `upsert_prices` keyed on `(coin_id, date)` — overlapping re-ingest updates in place, no duplicates
- [x] Implement `upsert_ohlc` with the same idempotent overwrite semantics
- [x] Implement `insert_snapshot` as `ON CONFLICT DO NOTHING` on `(coin_id, fetched_at)`
- [x] Verify row-count stability and no-duplicate guarantees under test (`test_db`)

---

## Story E2-S3: Gap-filled daily close series

- **Dependencies:** E2-S1
- **Unblocks:** E5-S2, E6-S1, E7-S2 (indicators, dashboard, and report all consume the repaired series)
- **Track:** Foundation / Storage
- **Domain:** (Database)
- **Estimate:** M
- **Status:** Complete (shipped)

**As a** self-custody technical holder,
**I want** the analysis series reindexed to a continuous daily range and forward-filled,
**So that** rolling-window indicators receive a calendar-correct, gap-free series.

### Acceptance Criteria

- Given stored prices with missing calendar days, When `load_close_series()` is called, Then the returned series has a continuous daily index with gaps forward-filled. *(FR-10, NFR-R4, test_db)*
- Given the raw `prices` table, When the series is loaded, Then stored rows are not mutated (gap repair is read-time only).
- Given a coin with no stored prices, When `load_close_series()` is called, Then it returns `None`.

### Tasks

- [x] Implement `load_close_series` reindexing stored prices to a continuous daily calendar with forward-fill
- [x] Ensure gap repair is read-time only — never mutate the raw `prices` table
- [x] Return `None` when a coin has no stored prices
- [x] Implement companion readers `load_ohlc` and `latest_snapshot_price`
- [x] Verify continuous-index gap-fill and the no-mutation guarantee under test (`test_db`)

---

## Validation

- **Build / lint:** `ruff check src tests` — passes clean (rules `E/F/W/I/UP/B`, line 110, target py311).
- **Test:** `pytest` — green. `tests/test_db.py` covers this epic's contracts: upsert idempotency (row-count stability over overlapping re-ingest) and `load_close_series` gap-fill (continuous daily index, forward-fill, `None` on empty, raw rows unmutated).

---

## Work Document References

- Source of truth (stories + AC): [_backlog.md](_backlog.md) — Epic 2, stories E2-S1 / E2-S2 / E2-S3
- PRD: [../_project-requirements.md](../_project-requirements.md) — FR-8, FR-9, FR-10; NFR-R1, NFR-R4
- Architecture: [../_project-architecture.md](../_project-architecture.md) — ADR-005 (snapshot insert-once)
- Implementation: `src/domdhi_crypto/db.py`
- Tests: `tests/test_db.py`

---

## Dependencies to Next

- **Phase 1 — Epic 4 (Ingest Orchestration):** `E4-S3` depends on `E2-S2` for safe overlapping-range writes and per-coin commit.
- **Phase 2 — Epic 5 (Indicators & Signals):** `E5-S2` depends on `E2-S3` for the gap-filled close series feeding signal generation.
- **Phase 3 — Epics 6 & 7 (Dashboard & Reports):** `E6-S1` and `E7-S2` depend on `E2-S3` for chart/report series.
- Within this epic: `E2-S1` unblocks both `E2-S2` and `E2-S3`; the two are independent of each other.
