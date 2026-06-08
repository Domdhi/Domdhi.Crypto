# Epic 4: Ingest Orchestration - Implementation Checklist

**Parent Document**: [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
**Phase**: 1 — Data & Core Ingestion
**Status**: Complete (shipped)
**Stories**: E4-S1, E4-S2, E4-S3
**Last Updated**: 2026-06-06

---

## Executive Summary

Epic 4 is the orchestration layer that turns the CoinGecko client (Epic 3) and the SQLite storage layer (Epic 2) into a usable command-line ritual. It exposes the `ingest` subcommand that drives the client → DB pipeline, resolving each coin by id or ticker, fetching a `--days` window of daily history, and persisting both live snapshots and historical rows — with per-coin failure isolation so one bad coin never aborts the whole run.

This epic is **brownfield and shipped** (commit `ad85772`); it is recorded here for FR traceability and verification, not for re-implementation. A wave that picks up these stories should treat them as no-ops unless a regression is found.

### Key Deliverables

- `cli.py` `ingest` subcommand orchestrating the coingecko → db pipeline (snapshot + daily history)
- Five argparse subcommands (`init`, `ingest`, `ta`, `report`, `dashboard`) driven from one console script, with a `--days` window (default 365) on `ingest`
- Case-insensitive coin resolution by CoinGecko id or ticker symbol
- Per-coin failure isolation (per-coin commit) and stablecoin history-skip, with stablecoins still valued in `report`/`dashboard`

---

## Optimization Summary

### Critical Path (~4h, 3 stories)

```
E4-S1 → E4-S2 → E4-S3
```

E4-S1 establishes the subcommand wiring every other handler hangs off; E4-S2 adds id/symbol resolution that `ingest`/`ta`/`report` all call; E4-S3 wraps the resolved coins in the failure-isolated ingest loop. (Cross-epic: E4-S3 also requires E3-S1's client and E2-S2's idempotent upsert.)

### Bottleneck Stories (High Fan-Out)

| Story | Title | Dependents | Blocked Hours |
|-------|-------|------------|---------------|
| E4-S1 | Subcommand-driven CLI workflow | E4-S2, E4-S3, E7-S1, E7-S2, E11-S2 | ~3h |
| E4-S2 | Coin resolution by id or symbol | E4-S3, E7-S1, E7-S2, E11-S3 | ~2h |

### Parallel Workstreams

| Track | Key Stories | Est. Hours |
|-------|-------------|-----------|
| A: CLI orchestration | E4-S1 → E4-S2 → E4-S3 | ~4h |

All three stories share `cli.py` (distinct, non-overlapping function surfaces) and sit on one strictly-ordered track — no intra-epic parallelism. Shipped/inert, so no live wave conflict.

---

## Execution Log

| # | Story | Date(s) | Session | Notes |
|---|-------|---------|---------|-------|
| 1 | E4-S1 | pre-`ad85772` | shipped | Verified for traceability |
| 2 | E4-S2 | pre-`ad85772` | shipped | Verified for traceability |
| 3 | E4-S3 | pre-`ad85772` | shipped | Verified for traceability |

---

## Key Decisions

- Coin selection is case-insensitive across both id and symbol so `ta BTC` and `ta bitcoin` resolve to the same coin.
- Ingest commits per coin, so a later coin's fetch failure leaves earlier coins' rows persisted rather than rolling back the whole run.
- Stablecoins (`"stable": true`) skip `market_chart`/`ohlc` history fetches but still contribute `amount × price` to portfolio value in `report`/`dashboard`.

---

## AI Task Management Protocol

1. **Review Current State:** Examine the entire TO-DO list.
2. **Identify Progress:** Note which tasks are marked as `[x]` (Completed) and which are `[ ]` (Pending).
3. **Prioritize & Select:** Choose the next logical `[ ]` task to address based on dependency order.
4. **Execute Task:** Perform the development work required.
5. **Update TO-DO List:** Upon completion, change the task's status to `[x]`.
6. **Document Changes:** Update relevant documentation.

---

**Key:**
* `[ ]` - Task Pending
* `[x]` - Task Completed
* `[>]` - Task In Progress
* `[~]` - Task Deferred
* `[!]` - Task Blocked
* `[*]` - Task Persistent/Ongoing
* `[B]` - Backend Responsibility
* `[C]` - Complex task (may need breakdown)

---

## Context

- **Epic**: Epic 4: Ingest Orchestration
- **Phase**: Phase 1: Data & Core Ingestion
- **Checklist location**: `docs/todo/TODO_epic04_ingest.md`
- **Related docs**: [_backlog.md](_backlog.md), [_project-architecture.md](../_project-architecture.md)
- **Dependencies**: E0-S1 (package entry point), E3-S1 (CoinGecko client), E2-S2 (idempotent upsert)
- **Critical Rules**: All three stories share the physical file `src/domdhi_crypto/cli.py` but own distinct, non-overlapping function surfaces. Phase 4 stories E11-S2 (`--version`) and E11-S3 (helper test) later touch `cli.py`; this epic is shipped/inert so there is no live conflict.

---

## Story E4-S1: Subcommand-driven CLI workflow BOTTLENECK

**Dependencies:** E0-S1
**Unblocks:** E4-S2, E4-S3, E7-S1, E7-S2, E11-S2
**Track:** A (CLI orchestration)
**Domain:** Backend
**Estimate:** M

**As a** self-custody technical holder, **I want** five argparse subcommands (`init`, `ingest`, `ta`, `report`, `dashboard`), **So that** the whole ritual is driven from one command.

**Acceptance Criteria:**
- Given the package is installed, When `domdhi-crypto <subcommand>` runs, Then the matching `cmd_*` handler executes and exits `0` on success. *(FR-1)*
- Given no/unknown subcommand, When the CLI parses args, Then argparse prints usage/help rather than a traceback (`required=True` on the subparser).
- Given `ingest`, When invoked, Then it accepts `--days` (default 365); `ta` requires a `<symbol>`; `dashboard` accepts `--open`.

**Tasks:**
- [x] Wire `main` to an argparse subparser dispatching `init`, `ingest`, `ta`, `report`, `dashboard` to their `cmd_*` handlers
- [x] Mark the subparser `required=True` so a missing/unknown subcommand prints usage instead of a traceback
- [x] Add the `--days` option (default 365) to `ingest`, the required `<symbol>` positional to `ta`, and the `--open` flag to `dashboard`
- [x] Ensure successful handlers exit `0`

---

## Story E4-S2: Coin resolution by id or symbol BOTTLENECK

**Dependencies:** E4-S1
**Unblocks:** E4-S3, E7-S1, E7-S2, E11-S3
**Track:** A (CLI orchestration)
**Domain:** Backend
**Estimate:** S

**As a** self-custody technical holder, **I want** to target a coin by CoinGecko id or ticker, case-insensitively, **So that** `ta BTC` and `ta bitcoin` select the same coin.

**Acceptance Criteria:**
- Given `coins.local.json` lists `{"id":"bitcoin","symbol":"BTC"}`, When `ta BTC` or `ta bitcoin` runs, Then the same coin is selected. *(FR-2)*
- Given an unknown symbol/id, When `ta` runs against it, Then `SystemExit` names the unknown coin (no empty output).
- Given `coins.local.json` is missing, When `load_coins` runs, Then `SystemExit` names `coins.example.json → coins.local.json`. *(FR-16, coins side)*

**Tasks:**
- [x] Implement `_resolve` to match a target against both coin id and symbol, case-insensitively
- [x] Raise `SystemExit` naming the unknown coin when no match is found
- [x] Implement `load_coins` to read `coins.local.json` fresh and raise `SystemExit` naming the copy-the-example fix when missing

---

## Story E4-S3: Per-coin failure isolation + stablecoin skip during ingest

**Dependencies:** E4-S1, E3-S1, E2-S2
**Unblocks:** (terminal within Phase 1 ingest track)
**Track:** A (CLI orchestration)
**Domain:** Backend
**Estimate:** M

**As a** self-custody technical holder, **I want** one coin's fetch failure to not abort the rest, and stablecoins skipped for history, **So that** a single bad coin doesn't lose the whole run and pegged assets don't show meaningless signals.

**Acceptance Criteria:**
- Given a multi-coin run where one coin's history fetch raises, When `ingest` runs, Then a `! …failed` warning prints and other coins still ingest and commit. *(FR-3, NFR-R3)*
- Given an earlier coin committed before a later failure, When the run ends, Then the earlier coin's rows persist (per-coin commit).
- Given a coin with `"stable": true`, When `ingest` runs, Then no `market_chart`/`ohlc` history is fetched for it, but its `amount × price` still counts toward portfolio value in `report`/`dashboard`. *(FR-4)*

**Tasks:**
- [x] Implement `cmd_ingest` to loop resolved coins, fetching snapshot + daily history via the CoinGecko client
- [x] Isolate per-coin failures: catch a coin's fetch error, print a `! …failed` warning, and continue with the remaining coins
- [x] Commit per coin so earlier coins persist even when a later coin fails
- [x] Skip `market_chart`/`ohlc` history (`_daily_rows`) for `"stable": true` coins while still recording their snapshot price for valuation

---

## Validation

- [x] Build succeeds: `ruff check src tests`
- [x] Tests pass: `pytest`
- [x] Documentation updated
- [x] Patterns extracted to memory (if applicable)

---

## Work Document References

| Date | Document | Story | Topic |
|------|----------|-------|-------|
| - | - | - | Shipped pre-`ad85772`; no work documents |

---

## Dependencies to Next

Completing Epic 4 closes Phase 1 (Data & Core Ingestion): the DB can now be populated with snapshots and gap-fillable daily history. This unblocks Phase 2 — Epic 5 (Indicators & Signals) consumes the gap-filled close series produced by ingestion, and downstream Phase 3 reports/dashboard (Epics 6–7) reuse this epic's coin-resolution and `cli.py` wiring. In Phase 4, E11-S2 (`--version`) and E11-S3 (CLI helper test) extend the `cli.py` surface this epic established.

---

**Last Updated:** 2026-06-06
