# Product Requirements Document: Domdhi.Crypto — Cycle 3 (See It & Prove It)

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Version** | 3.0 |
| **Status** | Active — cycle 3 planning |
| **Author** | product-strategist (via `/evolve` cycle 2→3) |
| **Date** | 2026-06-06 |
| **Tech Stack** | Python ≥3.11 (src-layout CLI + MCP server) · requests / pandas / numpy (no `pandas-ta`) · SQLite (stdlib) · hatchling · ruff · pytest · **vendored uPlot (dashboard charts, not a Python dep — ADR-009)** |

> **Delta PRD, evidence-seeded.** This regenerates the requirements for cycle 3 from `docs/.output/work/260606-2135/evolve-evidence.md` + `docs/todo/_feature-ideas.md` + the in-session ADR-009 decision. It assumes cycles 1–2's shipped FRs (FR-1…FR-27) as the **foundation** (preserved in the archives) and specifies only the *new* cycle-3 surface. Cycle 2 PRD: `docs/todo/_archive/cycle-2-260606-2135-decision-cortex/_project-requirements.md`. New FR IDs continue at **FR-28**.

---

## Executive Summary

Cycles 1–2 shipped a complete local-first decision cortex (CoinGecko → SQLite → hand-rolled TA → factor substrate → IC/ICIR + look-ahead-safe backtest → MCP agent interface → digest → thin ledger + risk), green at 308 tests. But the cortex is **headless** — its visual surface (`dashboard.py`) still shows only Cycle-1 price/RSI visuals — and **unproven on real data** (every test mocks the network). Cycle 3 closes both gaps: a **Decision Dashboard** that surfaces the cycle-2 layer in the offline HTML (interactive uPlot charts, ADR-009); an **"Alpha Arena for one"** that runs the pipeline on real history and paper-trades the cortex vs buy-and-hold to *prove edge*; and a **hardening** pass that ties off carried-forward debt. The DNA (local-first, offline, pure-numpy, 3-dep core, single-user, not-financial-advice) carries forward unchanged. The one new structural decision is ADR-009 (vendored uPlot, no framework/server).

---

## User Personas

Unchanged — the single self-custody technical holder, now an *agent operator* who wants to **see** and **trust** the cortex. No second persona. See the cycle-1 PRD (archived) for the full profile.

---

## User Flows

Both flows are single-user, local, and offline-after-ingest. The operator runs CLI subcommands; the only network hop is `ingest`.

### Flow 1 — See the cortex (Decision Dashboard, Epic 18)

1. Operator runs `domdhi-crypto ingest` then `ta` (populates the local DB).
2. Operator runs `domdhi-crypto dashboard` → a self-contained `dashboard.html` is generated with the uPlot blob inlined.
3. Operator opens `dashboard.html` in a browser **with the network disabled** and explores: price/RSI (carried forward), NAV + P/L, risk (correlation/vol/beta/drawdown), triggered signals, and (if a backtest exists) the equity curve + attribution. Charts are interactive (zoom/cursor/tooltip).

**Error / empty branches:**
- *No transactions or holdings* → NAV + P/L panel renders empty / "n/a", never errors (FR-29).
- *Under-window inputs* (risk math returns NaN) → surfaces as "n/a", never a fabricated number or crash (FR-30).
- *No backtest run on disk* → equity-curve panel is omitted/empty without error (FR-32).
- *Network accidentally left enabled* → makes no difference; the page references no external resource (NFR-C3-1).

### Flow 2 — Prove edge (Alpha Arena, Epic 19)

1. Operator sets `config.local.json` + `coins.local.json` to a small real coin set.
2. Operator runs the full pipeline on real CoinGecko history: `ingest → ta → factors → backtest → digest`. Each stage completes and produces non-degenerate output (see FR-33). The run is captured as a short, repeatable run record.
3. Operator runs `domdhi-crypto arena` → the cortex's decisions are paper-traded over the real history alongside buy-and-hold and ≥1 rule baseline; the arena reports each equity curve, relative performance, and per-factor attribution for the cortex.

**Error / failure branches:**
- *CoinGecko unreachable / rate-limited during ingest* → ingest surfaces the network error and stops; no partial-garbage downstream (the only network-dependent step).
- *A stage emits degenerate output on real data* (empty/NaN/constant series — see FR-33 definition) → the run record flags it as a finding rather than reporting false success.
- *A stablecoin symbol is passed to `factors`/`backtest`* → a clear "stablecoin — no TA/factors" message instead of the ingest dead-end (FR-37).
- *Any computation attempts to read beyond the evaluation timestamp* → blocked by the tested time-gated provider; the look-ahead guard holds (NFR-C3-4).

---

## Functional Requirements

> New work extends `src/domdhi_crypto/`, preserving the strictly-acyclic import graph (`ta`, `risk` are leaves; `cli`/MCP server are apex). `dashboard.py` may newly import `ledger`, `risk`, `factors`, `digest`, `backtest` (it currently imports only `db, ta, paths`).

### Epic 18 — Decision Dashboard (`dashboard.py` + vendored uPlot)

#### FR-28: Vendored uPlot charting substrate
- **Priority**: Must Have
- **Description**: Vendor uPlot (MIT, ~40KB minified, zero runtime deps) as a static asset committed to the repo with recorded version + source URL; `dashboard.py` inlines it into a `<script>` tag at generation time, exactly as it already inlines its `<style>` block. uPlot is **not** added to `pyproject.toml` dependencies.
- **Acceptance Criteria**:
  - Given the generated `dashboard.html`, When opened with the network disabled, Then interactive charts (zoom/cursor/tooltip) render — no CDN, no build step, no server.
  - Given `pyproject.toml`, When inspected, Then the runtime core dependency set is unchanged (3 deps; ADR-007 preserved).
  - Given the vendored blob, When committed, Then its uPlot version + source URL + license are recorded adjacent to it (ADR-009 maintenance note).

#### FR-29: NAV + P/L panel
- **Priority**: Must Have
- **Description**: Render `ledger.nav_series` as an interactive NAV-over-time line chart and `ledger.realized_pl`/`unrealized_pl` as a P/L summary in the dashboard.
- **Acceptance Criteria**:
  - Given a populated DB + `coins_cfg`, When the dashboard builds, Then a dated NAV curve and realized/unrealized P/L figures appear, sourced from `ledger.py`.
  - Given no transactions/holdings, When the dashboard builds, Then the panel degrades gracefully (empty/"n/a") rather than erroring.

#### FR-30: Risk panel
- **Priority**: Must Have
- **Description**: Render `risk.py` outputs — correlation matrix, portfolio volatility, beta-to-BTC, max-drawdown — in the dashboard.
- **Acceptance Criteria**:
  - Given ≥2 non-stable coins with history, When the dashboard builds, Then a correlation view + vol + beta + max-drawdown render from `risk.py`.
  - Given under-window inputs (NaN from `risk.py`), When rendered, Then NaN surfaces as "n/a", never a fabricated number or a crash.

#### FR-31: Triggered-signals view
- **Priority**: Must Have
- **Description**: Show which factors/digest signals are currently triggered (the "why now" the agent sees), surfaced for the human in the dashboard.
- **Acceptance Criteria**: Given a populated DB, When the dashboard builds, Then currently-triggered signals (from `factors.py`/`digest.py`) are listed per coin with their values.

#### FR-32: Backtest equity curve + attribution
- **Priority**: Should Have
- **Description**: Render a `backtest/` run's equity curve and its by-factor attribution as interactive charts in the dashboard.
- **Acceptance Criteria**: Given a backtest result, When rendered, Then an equity curve and per-factor attribution appear; absent a run, the panel is omitted/empty without error.

### Epic 19 — "Alpha Arena for one" (real-data validation + paper-trade arena)

#### FR-33: Real-data end-to-end validation
- **Priority**: Must Have
- **Description**: Run the full `ingest → ta → factors → backtest → digest` pipeline on a real (small) coin set against live CoinGecko history; confirm each module produces sane output on real data (the first time the cortex touches non-mocked data).
- **Acceptance Criteria**:
  - Given real `config.local.json` + `coins.local.json`, When the pipeline runs end-to-end, Then every stage completes without error and produces **non-degenerate output**.
  - Given the run, When complete, Then results are documented (a short real-data run record) so the validation is repeatable.
- **"Non-degenerate output" — defined** (the per-stage bar for this AC):
  - **ingest/ta**: price series is non-empty, dates are strictly monotonic, and values are not all-equal or all-NaN; the expected number of bars (within the requested window) is present.
  - **factors**: factor values are finite and vary across rows (not a single constant or all-NaN column) for at least the factors whose lookback window is satisfied.
  - **backtest**: the equity curve is populated for the full evaluation range (no all-flat-from-bar-0 artifact) and at least one trade/position change occurs.
  - **digest**: a brief is produced whose triggered-signal set reflects the real data (not the empty/default set), or explicitly reports "no signals triggered" as a real result.
  - Any stage that fails this bar is recorded as a **finding** in the run record (FR-33 surfaces real-data defects; it does not paper over them).

#### FR-34: Local paper-trade arena vs baselines
- **Priority**: Should Have
- **Description**: A local, offline arena that paper-trades the cortex's decisions over real history alongside a buy-and-hold baseline (and ≥1 simple rule baseline, e.g. SMA-cross), scored with the existing look-ahead-safe backtester and by-factor attribution. The "walk" rung as a feature. Reuses `backtest/` and `decision.py`; adds no live-exchange calls.
- **Acceptance Criteria**:
  - Given real history, When the arena runs, Then it reports the cortex equity curve vs each baseline's curve, plus relative performance.
  - Given the arena run, When scored, Then per-factor attribution is reported for the cortex strategy.
  - Given the arena, When it executes, Then the look-ahead guard holds (no future-bar reads; reuses the tested time-gated provider).

### Epic 20 — Hardening & Debt

#### FR-35: Complete the HammerGPT factor-library port
- **Priority**: Should Have
- **Description**: Finish lifting the Apache-2.0 HammerGPT factor *strings* (the full ~64-factor set) onto the hand-rolled pure-numpy primitives — as data, not new Python per factor.
- **Acceptance Criteria**: Given the built-in factor set, When loaded, Then the full HammerGPT-derived factor set evaluates correctly over the registry; license attribution is recorded (NOTICE).

#### FR-36: Provider abstraction for prices
- **Priority**: Could Have
- **Description**: Refactor `coingecko.py` behind a small `prices`-provider seam so the single-vendor coupling (Architecture Risk #2) can be swapped without touching `db`/`ta`/callers.
- **Acceptance Criteria**: Given the provider seam, When ingest runs, Then behavior is unchanged with CoinGecko as the default provider; the seam is covered by tests with the network mocked.

#### FR-37: Stablecoin CLI guard
- **Priority**: Should Have
- **Description**: `cmd_factors`/`cmd_backtest` should detect a stablecoin symbol and emit a clear message instead of the misleading "Run: domdhi-crypto ingest" dead-end (stables are intentionally not ingested). Mirrors the `cmd_ta` guard at `cli.py:125`.
- **Acceptance Criteria**: Given a stablecoin symbol, When `factors`/`backtest` runs, Then a clear "stablecoin — no TA/factors" style message is shown (not the ingest dead-end); covered by a CLI test.

#### FR-38: Transaction-sequence validation (thin ledger)
- **Priority**: Could Have
- **Description**: An optional validation path for the thin ledger to flag/reject incoherent transaction sequences (e.g. oversell), preserving the documented default clamp behavior unless validation is requested. The Epic-16 deferred follow-up.
- **Acceptance Criteria**: Given an incoherent sequence (e.g. sell-before-buy / oversell), When validation is enabled, Then it is reported/rejected; When disabled, Then the existing documented clamp behavior (characterization-tested) is unchanged.

---

## Data Model

**No schema change is required this cycle.** Cycle 3 is a surface-and-prove cycle: Epic 18 reads existing tables (`coins`, `prices`/OHLC, and the `transactions` table shipped in Epic 16 per ADR-008) and renders them; Epic 19 reads real history through the existing time-gated provider and writes only a Markdown run record + a new `arena.py` leaf (no persistence). The SQLite DB remains a **partial source of truth** — the `transactions` table is the sole user-entered, mutable entity; all other tables are derived/ingested.

If any story does turn out to need a column (none is currently anticipated — E20-S4's optional ledger validation reads the existing `transactions` schema, it does not extend it), it MUST go through `db.migrate()` as an **add-only** migration (NFR-C3-6, ADR-008). The canonical entity definitions live in [_project-architecture.md](_project-architecture.md) (Data Architecture section).

---

## Non-Functional Requirements

- **NFR-C3-1 (Offline dashboard, no framework)**: The dashboard remains a single self-contained offline HTML file — no server, no CDN, no Node toolchain, no build step. Interactive charts use a **vendored** uPlot blob inlined at generation time (ADR-009).
- **NFR-C3-2 (Core stays minimal)**: The runtime core stays 3-dep (ADR-007). uPlot is shipped as a string in generated output, never a Python dependency.
- **NFR-C3-3 (Auditability)**: All factor/indicator/IC/risk math stays pure, inspectable pandas/numpy. **No `pandas-ta`** (ADR-001).
- **NFR-C3-4 (Look-ahead safety)**: The arena and any backtest reuse the tested time-gated provider; no computation reads beyond the evaluation timestamp.
- **NFR-C3-5 (Local-first / offline / privacy)**: All rendering, scoring, and arena runs are offline against local state; network is hit only on `ingest`. Keys/holdings never leave the machine.
- **NFR-C3-6 (Data integrity)**: Schema change (if any) goes through `db.migrate()` add-only migrations; the DB stays a partial source-of-truth (ADR-008).
- **NFR-C3-7 (Quality bar)**: ruff + pytest green on 3.11/3.12/3.13; no static type-checking added (ADR-006).
- **NFR-C3-8 (Not financial advice)**: The arena is paper-trading only; live execution stays gated and out of scope.

---

## Success Criteria (Cycle-3 Definition of Done)

Cycle 3 is **done** when all of the following hold:

1. **All Must-Have FRs shipped** — FR-28, FR-29, FR-30, FR-31, FR-33 implemented and demonstrated (Should/Could items FR-32/34/35/37/36/38 are bonus, not gating).
2. **See it** — `dashboard.html` opens with the network disabled and renders interactive (zoom/cursor/tooltip) NAV+P/L, risk, and triggered-signals panels sourced from `ledger`/`risk`/`factors`/`digest`; empty/NaN inputs degrade to "n/a" rather than erroring.
3. **Prove it** — the full `ingest → ta → factors → backtest → digest` pipeline has run once on **real** CoinGecko history with a documented, repeatable run record, and every stage met the FR-33 non-degenerate bar (or its misses are recorded as findings).
4. **Constraints held** — runtime core stays 3-dep (ADR-007); no `pandas-ta` (ADR-001); uPlot shipped only as inlined output, never a Python dep (ADR-009); any schema change went through `db.migrate()` add-only (ADR-008); look-ahead guard intact (NFR-C3-4).
5. **Quality bar green** — `ruff check` clean and `pytest` green on the 3.11/3.12/3.13 matrix; no new flaky/network-dependent unit tests (the real-data run is a documented manual validation, not a CI unit test).
6. **Docs reconciled** — backlog stories closed against shipped reality; architecture/PRD updated for any decision made mid-cycle.

---

## Assumptions & Dependencies

**Assumptions:**
- Cycles 1–2 are shipped and green (308 tests); the modules Cycle 3 surfaces and exercises — `ledger`, `risk`, `factors`, `digest`, `backtest/`, `decision`, `context` — exist and behave as their tests assert.
- The single-operator, local, self-custody model holds; no multi-user, auth, or hosting concerns enter scope.
- A small real coin set is sufficient to validate the pipeline end-to-end (FR-33 does not require exhaustive coverage of all coins).
- The dashboard's consumers (`ledger`/`risk` etc.) already return JSON-/render-safe outputs, including NaN sentinels for under-window inputs.

**Dependencies:**
- **CoinGecko** reachable for the one real-data ingest (the sole network dependency; NFR-C3-5). The real-data run is gated on live API availability/rate limits.
- **Vendored uPlot** (MIT) blob committed to `vendor/` with recorded version + source URL + license (ADR-009) — a build-time/static dependency, not a runtime Python dep.
- **HammerGPT factor strings** (Apache-2.0) available to complete the FR-35 port as data; attribution recorded in `NOTICE`.
- **Existing time-gated provider** in `backtest/` is reused unchanged by the arena (FR-34) to preserve look-ahead safety.

---

## Out of Scope (this cycle)
Live trading / order placement (FR-27 gated adapter still deferred); a served/dynamic web app or any frontend framework / Node toolchain (ADR-009 rejects them); reinventing tracking (Ghostfolio) or execution engines (Freqtrade); multi-user/SaaS/mobile; `pandas-ta`.

## Related Documents
- Brief: [_project-brief.md](_project-brief.md) · Architecture (carried forward; ADR-009 added): [_project-architecture.md](_project-architecture.md)
- Evidence digest: [.output/work/260606-2135/evolve-evidence.md](.output/work/260606-2135/evolve-evidence.md)
- Feature ideas: [todo/_feature-ideas.md](todo/_feature-ideas.md) · Backlog: [todo/_backlog.md](todo/_backlog.md)
