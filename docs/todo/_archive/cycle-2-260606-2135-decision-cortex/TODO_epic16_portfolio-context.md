# TODO: Epic 16 — Portfolio Context (thin)

| Attribute | Value |
|-----------|-------|
| **Status** | Specification Complete |
| **Author** | Dom |
| **Created** | 2026-06-06 |

---

## Executive Summary

Add just-enough portfolio context to weight decisions: (1) a real **schema-migration scaffold**
(`schema_version` + ordered migrations) so the DB can safely hold non-regenerable user data; (2) a **thin
ledger** (`ledger.py`) giving NAV-over-time + derived realized/unrealized P/L from a new `transactions` table;
and (3) a **portfolio-risk leaf** (`risk.py`) computing correlation / vol / beta-to-BTC / drawdown across
holdings. This is position context, **not** a tax tracker, rebalancer, or execution engine (Epic 17 is deferred).

> **Architectural note (must read):** ADR-002/-003 declare the DB a *regenerable cache with no migration
> framework* ("delete and re-ingest" on incompatible change). Epic 16 deliberately **amends** this for
> user-entered data: the `transactions` table cannot be re-fetched from CoinGecko, so the DB becomes a
> **partial source of truth** (NFR-C2-5) — which is exactly why E16-S1 adds migrations. Price/snapshot/ohlc
> tables stay regenerable cache; only the migration scaffold + `transactions` are source-of-truth. A follow-up
> **ADR addendum** to record this evolution is tracked in Key Findings (out of scope for this TODO).

---

## Dependency Graph

```
Wave 1 (parallel-safe, disjoint files)        Wave 2 (depends on Wave 1)
┌──────────────────────────┐
│ E16-S1 (M)               │   db.py / test_db.py
│ migrations scaffolding    │ ───────────────┐
└──────────────────────────┘                 │   ┌──────────────────────────┐
┌──────────────────────────┐                 └──►│ E16-S2 (L)               │
│ E16-S3 (M)               │   risk.py /          │ transactions + ledger.py │
│ portfolio risk (leaf)     │   test_risk.py       └──────────────────────────┘
└──────────────────────────┘                          db.py, ledger.py, tests

Hard ordering: E16-S2's `transactions` table is added via a MIGRATION, so the
E16-S1 scaffolding (schema_version + migrate()) must exist first.
E16-S3 is a pure leaf with no DB-schema dependency → runs alongside E16-S1.
```

---

## Phase 7: Output & Portfolio Context

**Goal:** Add just-enough portfolio context (NAV, ledger, risk) to weight decisions, on a regenerable-cache DB
that can now also hold a thin slice of user source-of-truth data.

---

### Epic E16: Portfolio Context (thin)

**Objective:** Schema migrations + thin NAV/ledger + portfolio-level risk (FR-25, FR-26, NFR-C2-5).

---

* **Story E16-S1 (M): Schema-migration scaffolding**
  * **As a** maintainer, **I want** a `schema_version` table + ordered, idempotent migrations, **So that** the
    DB can hold non-regenerable user data without a destructive "delete and re-ingest."
  * **AC:**
    * [x] `db.py` defines a `schema_version` table (single integer `version`, default/baseline `0`) and an
      ordered `MIGRATIONS` registry of `(version: int, sql: str)` entries applied in ascending order.
    * [x] `db.migrate(conn) -> int` applies every migration whose `version` is greater than the DB's current
      version inside a single transaction, records the new current version, and returns it. It reads the
      current version as `0` when `schema_version` is empty/absent.
    * [x] `migrate()` is **idempotent**: a second call on an already-current DB applies nothing — the returned
      version is unchanged AND row counts in `coins`/`prices`/`snapshots` are unchanged (asserted, not assumed).
    * [x] `db.init_db()` runs the baseline `SCHEMA` (unchanged `CREATE TABLE IF NOT EXISTS`) and THEN
      `migrate(conn)`, so both fresh and pre-existing DBs converge to the latest version.
    * [x] **Data preserved:** a DB populated with prices + snapshots, then run through `migrate()`, retains every
      pre-existing row (verified by row-count + spot value, not just "no error").
    * [x] No existing test breaks — `test_init_db_creates_all_tables` uses a `<=` subset check, so the new table
      is additive. Confirm the full suite stays green.
    * [x] `tests/test_db.py` adds: (a) `migrate()` sets `version` to the latest registered migration; (b)
      re-running `migrate()` is a no-op (version + data unchanged) — assert against an independently-counted row
      total, not a tautology; (c) a populated-then-migrated DB keeps all rows.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/db.py` — MODIFY: add `schema_version` table, `MIGRATIONS` registry, `migrate()`, wire into `init_db()`.
    * `tests/test_db.py` — MODIFY: add migration idempotency / version-tracking / data-preserved tests.
  * **Agent budget:** 2 modified (`db.py`, `test_db.py`), 0 created — within ≤5/≤2 cap.
  * **Research notes:** Current `db.py` (145 lines): module-level `SCHEMA` string + `init_db` runs
    `executescript(SCHEMA)`. Migration shape: keep `SCHEMA` as baseline, add `MIGRATIONS` list; `migrate()` reads
    `SELECT MAX(version) FROM schema_version` (0 if none), applies pending SQL in one transaction, inserts the new
    version. `init_db` = `executescript(SCHEMA)` then `migrate(conn)`. Migrations must only ADD (never DROP/rewrite
    price data) to preserve the regenerable-cache invariant for cache tables. `test_db.py` fixture
    `conn(tmp_path)` = `db.init_db(...)` → `db.connect`; idempotency pattern = call twice, assert `COUNT(*)`
    unchanged. Full research: `docs/.output/work/2026-06-06/epic16-portfolio-context/1848-research-codebase.md`.

---

* **Story E16-S2 (L): NAV-over-time + thin ledger (`ledger.py`)**
  * **As a** holder, **I want** NAV history plus derived realized/unrealized P/L from recorded transactions,
    **So that** decisions are position-aware. (Explicitly **not** a tax/rebalancing tracker.)
  * **AC:**
    * [x] A `transactions` table is added **via an E16-S1 migration** (NOT a raw `SCHEMA` edit):
      `(id INTEGER PRIMARY KEY AUTOINCREMENT, coin_id TEXT, ts TEXT, side TEXT CHECK(side IN ('buy','sell')),
      amount REAL, price REAL, fee REAL)`. The migration bumps the schema version.
    * [x] `db.py` adds `insert_transaction(conn, coin_id, ts, side, amount, price, fee)` and
      `load_transactions(conn, coin_id=None)` (rows ordered by `ts`; all coins when `coin_id` is None). The
      `CHECK` constraint rejects a side other than buy/sell (asserted in a test).
    * [x] `ledger.py` exposes a **pure** `nav_series(conn, coins_cfg) -> pd.Series` (dated index): for each date in
      the aligned daily close range, the sum across coins of `holding_amount * close` (reuse
      `db.load_close_series`; stables valued at `amount * price_or_1`). No module-level IO — injected `conn` +
      `coins_cfg` (Epic-14 pure-vs-IO split). Empty/no-data → an empty Series, never an exception.
    * [x] `ledger.py` exposes pure `realized_pl(conn, coins_cfg=None)` and `unrealized_pl(conn, coins_cfg)` derived
      from `transactions` on an **average-cost** basis (matches existing `context._build_position` avg-entry
      semantics): realized from matched sells, unrealized from the remaining open position vs
      `db.latest_snapshot_price`. Every returned/rendered float is finite-guarded with `math.isfinite`
      (memory `json-safety-isnan-misses-infinity`); avoid float-overshoot when summing position amounts
      (memory `allin-buy-sizing-float-overshoot`).
    * [x] `tests/test_ledger.py` (NEW): (a) `nav_series` for a 2-coin seeded tmp DB equals an independently
      hand-computed dated series (not "non-empty"); (b) a known buy→buy→sell sequence yields hand-computed
      realized + unrealized P/L on average-cost basis; (c) an empty DB returns empty/zero and does not raise.
    * [x] `tests/test_db.py` adds transaction-layer tests: insert + `load_transactions` round-trips ordered by
      `ts`, and the `CHECK(side …)` rejects an invalid side (expects `sqlite3.IntegrityError`).
    * [x] `ruff check src tests` clean and `pytest` green (prior suite + new ledger/transaction tests).
  * **Estimate:** L
  * **Dependencies:** E16-S1
  * **Files:**
    * `src/domdhi_crypto/db.py` — MODIFY: add the `transactions` migration entry + `insert_transaction` / `load_transactions` helpers.
    * `src/domdhi_crypto/ledger.py` — NEW: pure `nav_series`, `realized_pl`, `unrealized_pl` (injected conn/coins_cfg).
    * `tests/test_ledger.py` — NEW: NAV + P/L unit tests (tmp SQLite, in-memory coins_cfg).
    * `tests/test_db.py` — MODIFY: transactions insert/load + CHECK-rejects-bad-side tests.
  * **Agent budget:** 2 modified (`db.py`, `test_db.py`), 2 created (`ledger.py`, `test_ledger.py`) — within ≤5/≤2 cap.
  * **Research notes:** `snapshots` are sparse (one row per ingest), so NAV-over-time derives from the **daily
    `prices` close series** × holdings (richer + continuous) rather than the literal "snapshots" wording in the
    backlog — note the deviation + rationale. Holdings/avg_entry/stable come from `coins.local.json`; keep
    `ledger` pure with injected `conn`/`coins_cfg` exactly like `context.build_context` /
    `digest.build_digest`. Average-cost basis chosen over FIFO to match `context._build_position`'s avg_entry
    model. `db.load_close_series` already reindexes to a continuous daily range + ffills close.
    Full research: `docs/.output/work/2026-06-06/epic16-portfolio-context/1848-research-codebase.md`.

---

* **Story E16-S3 (M): Portfolio-level risk (`risk.py` leaf)**
  * **As a** holder, **I want** correlation / vol / beta-to-BTC / drawdown across holdings, **So that** I can see
    real diversification rather than a list of independent positions.
  * **AC:**
    * [x] `risk.py` exposes a **pure** `correlation_matrix(conn, coins_cfg) -> pd.DataFrame` of pairwise daily
      log-return correlations across the configured non-stable coins, aligned on a common (inner-join) date index.
    * [x] `risk.py` exposes `portfolio_vol(conn, coins_cfg) -> float`: annualized portfolio volatility weighted by
      each holding's value share (reuse the annualization convention from `ta.annualized_vol` for consistency).
    * [x] `risk.py` exposes `beta_to_btc(conn, coins_cfg) -> dict[str, float]`: `cov(asset, BTC)/var(BTC)` of daily
      returns, benchmark = the coin with symbol `BTC` / id `bitcoin`; returns `{}` (or NaN values) when no BTC
      benchmark is configured. Beta-to-BTC-itself ≈ 1.0 (asserted).
    * [x] `risk.py` exposes a dependency-free pure `max_drawdown(series) -> float` operating on ANY value series
      (so portfolio-NAV drawdown is `max_drawdown(ledger.nav_series(...))` at the call site — `risk.py` does NOT
      import `ledger`, keeping this story a parallel-safe leaf).
    * [x] **Under-window → NaN:** fewer than 2 aligned return points (or a single-coin portfolio for correlation)
      yields `NaN`/empty rather than an exception (mirror `ta.analyze`'s None-on-thin-data discipline).
    * [x] `risk.py` imports numpy/pandas + `db` only — no new dependency (3-dep core preserved, ADR-001).
    * [x] `tests/test_risk.py` (NEW): correlation of two identical series == 1.0; `beta_to_btc` of BTC against
      itself ≈ 1.0; `max_drawdown` of a known series matches a hand-computed value; insufficient-data → NaN.
      Assertions use independently-derived reference values, not tautologies.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/risk.py` — NEW: `correlation_matrix`, `portfolio_vol`, `beta_to_btc`, `max_drawdown` (pure leaf).
    * `tests/test_risk.py` — NEW: risk-metric unit tests with independent reference values.
  * **Agent budget:** 0 modified, 2 created (`risk.py`, `test_risk.py`) — within ≤5/≤2 cap.
  * **Research notes:** Inputs are ≥2 coins' daily close series via `db.load_close_series` (None on empty),
    aligned inner-join, converted to daily log returns. `correlation_matrix` = pandas `.corr()`. `portfolio_vol`
    weights by holding value (`amount * latest_price`). `beta_to_btc` needs a benchmark = the coin resolving to
    BTC/bitcoin; absent → empty. Mirror `ta.annualized_vol` for annualization. Pure leaf, no CLI surface in this
    epic (CLI wiring deferred — backlog AC is backend-only). The title mentions "drawdown"; AC adds a generic
    `max_drawdown(series)` so it's available without coupling to `ledger.py`. Full research:
    `docs/.output/work/2026-06-06/epic16-portfolio-context/1848-research-codebase.md`.

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|--------------|
| E16-S1 | Schema-migration scaffolding | M | 1 | [x] | None |
| E16-S3 | Portfolio-level risk (`risk.py` leaf) | M | 1 | [x] | None |
| E16-S2 | NAV-over-time + thin ledger (`ledger.py`) | L | 2 | [x] | E16-S1 |

**Total: 3 stories. Estimated: ~5–7 hours.**

---

## Wave Plan

**Shape:** file-overlap partitioned — E16-S1 (db migrations) and E16-S3 (risk leaf) own disjoint file sets and
run in parallel in Wave 1; E16-S2 (transactions + ledger) depends on the E16-S1 migration scaffolding and runs
in Wave 2. Role-based (Tests/Code/Verify) was rejected: the stories are heterogeneous backend slices with a hard
schema dependency, and `/run-todo`'s per-wave TDD step already writes tests before each story's implementation.

### Wave 1 — Independent foundations (parallel)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E16-S1 | general-purpose | `src/domdhi_crypto/db.py`, `tests/test_db.py` | 2/0 | Yes |
| E16-S3 | general-purpose | `src/domdhi_crypto/risk.py`, `tests/test_risk.py` | 0/2 | Yes |

### Wave 2 — Ledger on the migration scaffold (depends on Wave 1)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E16-S2 | general-purpose | `src/domdhi_crypto/db.py`, `src/domdhi_crypto/ledger.py`, `tests/test_ledger.py`, `tests/test_db.py` | 2/2 | Yes |

### Shared Hotspot Files
- **`src/domdhi_crypto/db.py`** & **`tests/test_db.py`** — touched by E16-S1 (Wave 1) and E16-S2 (Wave 2). In the
  file-overlap shape they sit in different waves, so there is no in-wave concurrent write. E16-S2 edits db.py only
  AFTER E16-S1's migration scaffolding lands (enforced by the Wave-2→Wave-1 dependency).

### Critical Path & Parallel Workstreams (REQUIRED)
- **Critical path:** E16-S1 → E16-S2 (M → L) — the migration scaffold gates the `transactions` migration and the
  ledger; ~3.5–5.5h. This is the wall-clock floor.
- **Parallel workstreams:** E16-S3 (risk leaf) runs concurrently with E16-S1 in Wave 1 — a disjoint chain (own
  files, no DB-schema dependency).
- **Max concurrent agents:** 2 (Wave 1: E16-S1 ∥ E16-S3).
- **Bottleneck:** E16-S1 — its `schema_version`/`migrate()` API is what E16-S2's `transactions` migration plugs
  into; if its migration shape changes, E16-S2's migration entry changes with it.

---

## Key Findings from Research

1. **Architectural evolution to flag (ADR addendum follow-up).** ADR-002/-003 + Architecture §"Rollback &
   Migration" (`_project-architecture.md:362,408,586`) declare the DB a regenerable cache with no migrations.
   Epic 16 intentionally makes it a *partial source of truth* for the user-entered `transactions` table — the
   migration scaffold (E16-S1) is the sanctioned mechanism. Price/snapshot/ohlc remain regenerable cache. A
   short ADR addendum should record this; it is **out of scope** for this TODO but tracked here.
2. **No guard test breaks.** `tests/test_db.py::test_init_db_creates_all_tables` asserts a `<=` subset of table
   names, so adding `schema_version` + `transactions` is additive. No test enumerates an exact table set or a
   subcommand count.
3. **NAV source deviation.** Snapshots are sparse (one row per ingest); a meaningful NAV-over-time uses the daily
   `prices` close series × holdings (reuses `db.load_close_series`, which already gap-fills to a continuous daily
   index). Noted as a deliberate deviation from the backlog's "from snapshots" wording.
4. **Pure-vs-IO continuity.** `ledger.py` and `risk.py` follow the Epic-14/15 split: pure functions take an
   injected `conn` (+ `coins_cfg`); no module-level `db.connect()`/coins-load inside the compute layer. This
   keeps them unit-testable against a tmp SQLite without monkeypatching.
5. **No new CLI surface in this epic.** The backlog AC for all three stories is backend/database only — no
   `cmd_*` handlers are required. CLI exposure of NAV/risk is a separate, later concern.
6. **3-dep core preserved (ADR-001).** Both new modules import only numpy/pandas + first-party `db` — no new
   third-party dependency.

---

## Execution Log

- **2026-06-06 — Wave 1 (E16-S1, E16-S3) complete.** Path B, 2 Sonnet agents parallel, TDD (tests pre-written
  by Main Agent). E16-S1: `schema_version` table + empty `MIGRATIONS` registry + `migrate(conn)->int` wired
  into `init_db`. E16-S3: new `risk.py` leaf — `correlation_matrix`, `portfolio_vol`, `beta_to_btc`,
  `max_drawdown` (pure, symbol-keyed, under-window→NaN, no `ledger` import). Gate green **296/296** (+13:
  6 migration + 7 risk). Code review: DONE_WITH_CONCERNS, 0 CRITICAL/MAJOR; fixed `migrate()` docstring's
  false "single transaction" claim (executescript implicit-commit — promoted as a memory). E2E leg SKIP→PASS
  (no E2E suite). AC: 14/14 verified.

### Key Decisions
- **risk metric keys = coin SYMBOL** (BTC/ETH), not coin id — `correlation_matrix` index/columns and
  `beta_to_btc` keys are symbols for human-meaningful output.
- **`portfolio_vol` uses log returns** (consistent with correlation/beta) while honoring `ta.annualized_vol`'s
  √365 annualization convention — accepted by review as a deliberate, defensible choice.
- **`MIGRATIONS` ships empty in Wave 1**; E16-S2 (Wave 2) appends the first real entry (transactions DDL). The
  engine is proven via a monkeypatched throwaway migration in `test_db.py`.

- **2026-06-06 — Wave 2 (E16-S2) complete.** Path A (Main Agent direct). `db.py`: `transactions` table via
  `MIGRATIONS[(1, …)]` (version 1) + `insert_transaction`/`load_transactions`. `ledger.py` (NEW): pure
  `nav_series` (daily prices × holdings, stables at amount×price_or_1), `realized_pl`/`unrealized_pl`
  (average-cost, fee-aware, `math.isfinite`-guarded). Two Wave-1 migration tests revised for the now-non-empty
  registry (empty-table-reads-0 via DELETE; throwaway migration at version 999). Gate green **308/308** (+12:
  4 transaction + 8 ledger). Code review DONE_WITH_CONCERNS, 0 blocking — documented thin-ledger boundaries
  (oversell clamps to flat, leading-sell uses zero basis, NAV leading-gap undercount, realized-includes-stables
  asymmetry) and pinned each with a characterization test. AC: 7/7.

### Deferred follow-ups (tracked, out of scope)
- **Transaction-sequence validation** (reject oversell / sell-before-buy) — deliberately omitted from this thin
  ledger; a future story if position integrity is needed. Behaviors are documented + characterization-tested.
- **ADR addendum** recording the DB as a *partial source of truth* (the `transactions` table) — see Key Findings #1.
