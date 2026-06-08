# Product Backlog: Domdhi.Crypto — Cycle 3 (See It & Prove It)

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Version** | 3.0 |
| **Status** | ✅ Complete — cycle 3 (Epics 18–20) shipped 100%; archived 2026-06-07 |
| **Author** | project-planner (via `/evolve` cycle 2→3) |
| **Tech Stack** | Python ≥3.11 · requests / pandas / numpy (no `pandas-ta`) · SQLite · MCP server · **vendored uPlot (dashboard, ADR-009)** · hatchling · ruff · pytest |

---

## Executive Summary

Cycle 2 (the decision cortex — Epics 12–16) shipped **100% complete** (308 tests green) and is archived at `docs/todo/_archive/cycle-2-260606-2135-decision-cortex/`. The cortex *thinks* but is **headless and unproven on real data**. Cycle 3 makes it **visible** and **provable**.

The plan is seeded from evidence (`docs/.output/work/260606-2135/evolve-evidence.md`), the carried-forward `_feature-ideas.md`, the four cycle-2 retros, and the in-session **ADR-009** decision (vendored uPlot for dashboard charts — no framework, no server, no build step; core stays 3-dep). Architecture otherwise carries forward unchanged (no `--replan-arch`).

**Spine:** Surface it (Epic 18 — the lead) → Prove it (Epic 19) → Harden it (Epic 20).

**ID scheme:** `E{epic}-S{story}`, epic numbers continue from cycle 2 (next free = 18; Epic 17 reserved for the deferred execution adapter).

---

## Technology Stack

| Layer | Choice |
|-------|--------|
| Language / runtime | Python ≥3.11 (3.11/3.12/3.13) |
| Compute | pure pandas/numpy — **no `pandas-ta`** (ADR-001) |
| Dashboard | single offline HTML + **vendored uPlot** inlined at generation time (ADR-009); no server, no build, no Node |
| Storage | SQLite; partial source-of-truth via add-only migrations (ADR-008) |
| Agent interface | MCP server (local, offline; optional `[mcp]` extra, ADR-007) |
| Borrowed (Apache-2.0) | HammerGPT factor strings (complete the port) |
| Lint / test / CI | ruff + pytest, 3.11/3.12/3.13 matrix |

---

## Phase 8: Surface It (the lead)

**Goal:** Make the cortex visible — surface ledger/risk/factors/backtest in the offline dashboard via vendored uPlot. Everything to show already exists; this is wiring + rendering.

**Status:** ✅ done — the lead wave.

---

### Epic 18: Decision Dashboard

**Objective:** Surface the cycle-2 decision layer in `dashboard.html` with interactive uPlot charts, offline, no framework (FR-28…FR-32, ADR-009). `report/dashboard/` newly imports `ledger`, `risk`, `signals/factors`/`report/digest`, `backtest`.

* **Story E18-S1 (Frontend/Backend): Vendored uPlot charting substrate**
  * **As an** agent operator, **I want** the dashboard to render interactive charts offline, **So that** I can explore my data without a server or build step.
  * **AC:**
    * uPlot (MIT, ~40KB) vendored as a static asset with recorded version + source URL + license; inlined into `dashboard.html` at generation (like the existing `<style>` block).
    * Generated HTML opens with the network disabled and renders an interactive (zoom/cursor/tooltip) chart — no CDN, no build, no server.
    * `pyproject.toml` runtime core deps unchanged (3-dep; ADR-007). *(FR-28, NFR-C3-1/2, ADR-009)*
  * **Files:** `src/domdhi_crypto/report/dashboard/` (package: `__init__` · `theme` · `charts` · `panels` · `scaffold`), `src/domdhi_crypto/report/dashboard/vendor/uplot.min.js` (vendored asset + provenance note) · **Est:** M · **Status:** ✅ done · **Deps:** None

* **Story E18-S2 (Backend): NAV + P/L panel**
  * **As a** holder, **I want** my NAV curve and realized/unrealized P/L on the dashboard, **So that** I can see my position over time.
  * **AC:**
    * A dated NAV curve (from `ledger.nav_series`) and realized/unrealized P/L figures (`ledger.realized_pl`/`unrealized_pl`) render in the dashboard.
    * No transactions/holdings → panel degrades to empty/"n/a", never errors. *(FR-29)*
  * **Files:** `src/domdhi_crypto/report/dashboard/` · **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

* **Story E18-S3 (Backend): Risk panel**
  * **As a** holder, **I want** correlation/vol/beta/drawdown on the dashboard, **So that** I can see real diversification at a glance.
  * **AC:**
    * Correlation view + portfolio vol + beta-to-BTC + max-drawdown render from `risk.py`.
    * NaN (under-window) surfaces as "n/a", never fabricated, never a crash. *(FR-30)*
  * **Files:** `src/domdhi_crypto/report/dashboard/` · **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

* **Story E18-S4 (Backend): Triggered-signals view**
  * **As a** holder, **I want** to see which factor/digest signals are currently firing, **So that** the agent's "why now" is visible to me.
  * **AC:** Currently-triggered signals (from `signals/factors.py`/`report/digest.py`) are listed per coin with their values on the dashboard. *(FR-31)*
  * **Files:** `src/domdhi_crypto/report/dashboard/` · **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

* **Story E18-S5 (Backend): Backtest equity curve + attribution**
  * **As a** holder, **I want** a backtest's equity curve + by-factor attribution rendered, **So that** I can see strategy performance visually.
  * **AC:** A `backtest/` run's equity curve + per-factor attribution render as interactive charts; absent a run, the panel is omitted/empty without error. *(FR-32)*
  * **Files:** `src/domdhi_crypto/report/dashboard/` · **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

---

## Phase 9: Prove It

**Goal:** Run the cortex on real data for the first time, then paper-trade it against buy-and-hold to measure edge — the "walk" rung.

**Status:** ✅ done.

---

### Epic 19: "Alpha Arena for one"

**Objective:** Validate on real history, then a local offline paper-trade arena vs baselines (FR-33, FR-34). Reuses `backtest/` + `decision.py`; no live-exchange calls.

* **Story E19-S1 (Test): Real-data end-to-end run**
  * **As an** operator, **I want** the full pipeline run on real coins, **So that** I know the cortex works outside mocked tests.
  * **AC:**
    * `ingest → ta → factors → backtest → digest` runs end-to-end on a real (small) coin set against live CoinGecko history with no errors and **non-degenerate output** (per the per-stage bar defined in FR-33 — non-empty, monotonic dates, finite/varying values, populated equity curve).
    * The run is documented (a short repeatable real-data run record); any stage that misses the bar is logged as a finding. *(FR-33, NFR-C3-5)*
  * **Files:** `docs/app/` run record + any fixes surfaced by real data · **Est:** M · **Status:** ✅ done · **Deps:** None

* **Story E19-S2 (Backend): Local paper-trade arena vs baselines**
  * **As an** operator, **I want** the cortex paper-traded vs buy-and-hold (+ a rule baseline) over real history, **So that** I can prove edge before risking a cent.
  * **AC:**
    * Arena reports the cortex equity curve vs each baseline (buy-and-hold + ≥1 rule strategy), plus relative performance.
    * Per-factor attribution reported for the cortex strategy.
    * Look-ahead guard holds (reuses the tested time-gated provider; no future-bar reads). *(FR-34, NFR-C3-4/8)*
  * **Files:** `src/domdhi_crypto/backtest/arena.py` (new), `src/domdhi_crypto/cli.py` (new `arena` subcommand) · **Est:** L · **Status:** ✅ done · **Deps:** E19-S1

---

## Phase 10: Harden It

**Goal:** Tie off carried-forward debt — finish the factor port, de-risk the data provider, fix the stablecoin CLI dead-end, and add optional ledger validation.

**Status:** ✅ done.

---

### Epic 20: Hardening & Debt

**Objective:** Close cycle-2 carry-forward items (FR-35…FR-38). Independent stories, parallel-safe.

* **Story E20-S1 (Backend): Complete the HammerGPT factor-library port**
  * **As a** holder, **I want** the full HammerGPT factor set as data, **So that** I have a complete library, not a subset.
  * **AC:** The full ~64-factor HammerGPT-derived set evaluates correctly over the registry as data (no new Python per factor); Apache-2.0 attribution recorded in `NOTICE`. *(FR-35, ADR-001)*
  * **Files:** `src/domdhi_crypto/signals/factors.py` (builtin data), `NOTICE` · **Est:** M · **Status:** ✅ done · **Deps:** None

* **Story E20-S2 (Backend): Provider abstraction for prices**
  * **As a** maintainer, **I want** `coingecko.py` behind a `prices`-provider seam, **So that** single-vendor coupling (Architecture Risk #2) can be swapped without touching callers.
  * **AC:** Ingest behavior unchanged with CoinGecko as default; the seam is covered by tests with the network mocked. *(FR-36)*
  * **Files:** `src/domdhi_crypto/ingest/coingecko.py`, a small provider interface · **Est:** M · **Status:** ✅ done · **Deps:** None

* **Story E20-S3 (Backend): Stablecoin CLI guard**
  * **As a** holder, **I want** a clear message for stablecoins in `factors`/`backtest`, **So that** I'm not sent to a misleading "Run: ingest" dead-end.
  * **AC:** A stablecoin symbol yields a clear "stablecoin — no TA/factors" style message (mirrors `cmd_ta`, `cli.py:125`), covered by a CLI test. *(FR-37)*
  * **Files:** `src/domdhi_crypto/cli.py` · **Est:** S · **Status:** ✅ done · **Deps:** None

* **Story E20-S4 (Backend): Transaction-sequence validation (thin ledger)**
  * **As a** holder, **I want** optional validation of transaction sequences, **So that** incoherent input (e.g. oversell) can be caught when I want it.
  * **AC:** With validation enabled, incoherent sequences are reported/rejected; with it disabled, the existing documented clamp behavior (characterization-tested) is unchanged. *(FR-38)*
  * **Files:** `src/domdhi_crypto/portfolio/ledger.py`, `src/domdhi_crypto/shared/db.py` · **Est:** M · **Status:** ✅ done · **Deps:** None

---

## Deferred (Won't — this version)

### Epic 17: Gated Live Execution Adapter (FR-27)
Delegate paper-then-live orders to Freqtrade/CCXT behind a hard human gate (withdrawal-disabled, IP-allowlisted keys, hard caps, kill-switch). The distant "run" rung — captured, not scheduled. Revisit only after Epic 19's arena *proves* edge vs buy-and-hold.

---

## Story Index

| Story | Title | Phase | Epic | Estimate | Status | Dependencies |
|-------|-------|-------|------|----------|--------|-------------|
| E18-S1 | Vendored uPlot charting substrate | 8 | Decision Dashboard | M | ✅ done | None |
| E18-S2 | NAV + P/L panel | 8 | Decision Dashboard | M | ✅ done | E18-S1 |
| E18-S3 | Risk panel | 8 | Decision Dashboard | M | ✅ done | E18-S1 |
| E18-S4 | Triggered-signals view | 8 | Decision Dashboard | M | ✅ done | E18-S1 |
| E18-S5 | Backtest equity curve + attribution | 8 | Decision Dashboard | M | ✅ done | E18-S1 |
| E19-S1 | Real-data end-to-end run | 9 | Alpha Arena | M | ✅ done | None |
| E19-S2 | Local paper-trade arena vs baselines | 9 | Alpha Arena | L | ✅ done | E19-S1 |
| E20-S1 | Complete HammerGPT factor-library port | 10 | Hardening | M | ✅ done | None |
| E20-S2 | Provider abstraction for prices | 10 | Hardening | M | ✅ done | None |
| E20-S3 | Stablecoin CLI guard | 10 | Hardening | S | ✅ done | None |
| E20-S4 | Transaction-sequence validation | 10 | Hardening | M | ✅ done | None |

---

## FR Coverage Map

| Requirement | Priority | Story |
|-------------|----------|-------|
| FR-28 Vendored uPlot substrate | Must | E18-S1 |
| FR-29 NAV + P/L panel | Must | E18-S2 |
| FR-30 Risk panel | Must | E18-S3 |
| FR-31 Triggered-signals view | Must | E18-S4 |
| FR-32 Backtest equity curve + attribution | Should | E18-S5 |
| FR-33 Real-data end-to-end validation | Must | E19-S1 |
| FR-34 Local paper-trade arena | Should | E19-S2 |
| FR-35 Complete HammerGPT factor port | Should | E20-S1 |
| FR-36 Provider abstraction | Could | E20-S2 |
| FR-37 Stablecoin CLI guard | Should | E20-S3 |
| FR-38 Transaction-sequence validation | Could | E20-S4 |

---

## Notes on Wave Safety
- **Epic 18 is the lead**, rooted at E18-S1 (vendored uPlot + dashboard wiring). S2–S5 fan out from S1 and all touch `report/dashboard/` — they share one package, so run them sequentially or with explicit section ownership (not naive parallel) to avoid contention.
- **Epic 19** depends on the cortex (cycle 2, done) — E19-S1 (real-data run) gates E19-S2 (arena). E19-S2 adds a new `backtest/arena.py` leaf + a CLI subcommand.
- **Epic 20** stories own distinct files (`signals/factors.py`, `ingest/coingecko.py`, `cli.py`, `portfolio/ledger.py`) and are largely parallel-safe; E20-S1 and E20-S4 touch files the arena may also touch, so sequence if run concurrently with Epic 19.
- New modules stay **pure leaves** (`backtest/arena.py`) or apex (`cli.py`); the acyclic import graph is preserved. CI must keep failing if `pandas-ta` is imported.

## Related Documents
- Brief: [../_project-brief.md](../_project-brief.md) · PRD: [../_project-requirements.md](../_project-requirements.md)
- Architecture (carried forward; ADR-009 added): [../_project-architecture.md](../_project-architecture.md)
- Feature ideas: [_feature-ideas.md](_feature-ideas.md) · Evidence digest: [../.output/work/260606-2135/evolve-evidence.md](../.output/work/260606-2135/evolve-evidence.md)
- Cycle 2 archive: [_archive/cycle-2-260606-2135-decision-cortex/](_archive/cycle-2-260606-2135-decision-cortex/)
