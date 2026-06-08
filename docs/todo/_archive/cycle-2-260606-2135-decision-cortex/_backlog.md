# Product Backlog: Domdhi.Crypto — Cycle 2 (Decision Cortex)

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Version** | 2.0 |
| **Status** | Active — cycle 2 planning (fresh backlog; cycle 1 archived 100% complete) |
| **Author** | project-planner (via `/evolve` cycle 1→2) |
| **Tech Stack** | Python ≥3.11 · requests / pandas / numpy (no `pandas-ta`) · SQLite · MCP server · hatchling · ruff · pytest |

---

## Executive Summary

Cycle 1 (the local-first portfolio + TA engine, Epics 0–7 + 11) shipped **100% complete** and is archived at `docs/todo/_archive/cycle-1-260606-1214/`. Cycle 2 evolves the tool into a **decision cortex** — an auditable factor substrate, rigorous edge validation, and an MCP interface for an LLM agent to reason over and *explain* decisions, with execution delegated and gated.

The plan is seeded from production evidence (`docs/.output/work/260606-1214/evolve-evidence.md`) and the carried-forward `_feature-ideas.md` (13 ideas), grounded in prior-art recon (Ghostfolio, Freqtrade/Jesse, Moon Dev, nof1 Alpha Arena, HammerGPT). Architecture carries forward unchanged (no `--replan-arch`); new compute modules stay pure leaves.

**Spine:** Substrate (Epic 12) → Edge Validation (Epic 13) → Agent Interface (Epic 14), then Output (15) and Portfolio Context (16). Execution (17) is deferred.

**ID scheme:** `E{epic}-S{story}`, epic numbers continue from cycle 1 (next free = 12).

---

## Technology Stack

| Layer | Choice |
|-------|--------|
| Language / runtime | Python ≥3.11 (3.11/3.12/3.13) |
| Compute | pure pandas/numpy factor primitives — **no `pandas-ta`** (ADR-001) |
| Storage | SQLite; **+ schema migrations** once the thin ledger lands |
| Agent interface | MCP server (local, offline) |
| Borrowed (Apache-2.0) | HammerGPT factor strings + IC/ICIR + time-gated backtester *patterns* |
| Lint / test / CI | ruff + pytest, 3.11/3.12/3.13 matrix |

---

## Phase 5: Substrate & Edge Validation (the spine)

**Goal:** Turn raw indicators into a declarative factor library whose predictive edge can be measured and backtested without look-ahead bias. Everything downstream feeds on this.

**Status:** ✅ done — the build wave.

---

### Epic 12: Signal Substrate

**Objective:** Factors-as-data over a pure-numpy primitive registry (FR-17, FR-18). Extends `ta.py`; adds `factors.py`.

* **Story E12-S1 (Backend): Pure-numpy factor primitive registry**
  * **As a** quant-minded holder, **I want** a registry of TA + time-series + cross-section primitives in pure numpy/pandas, **So that** factors compute without `pandas-ta` and stay auditable.
  * **AC:**
    * Primitives (MAs, momentum, trend, vol, volume, `DELAY`/`TS_*`/`DECAYLINEAR`/`LOG_RETURN`/`NORMALIZE`/`ZSCORE`, math) each match a reference value within tolerance.
    * Registry exposes per-function metadata (signature, description, example, category).
    * Import graph: numpy/pandas only; `pandas-ta` absent. *(FR-17, NFR-C2-1, ADR-001)*
  * **Files:** `src/domdhi_crypto/factors.py` (registry), `src/domdhi_crypto/ta.py` (extend) · **Est:** L · **Status:** ✅ done · **Deps:** None

* **Story E12-S2 (Backend): Safe declarative factor expression evaluator**
  * **As a** holder, **I want** factors expressed as strings evaluated safely over the registry, **So that** adding a factor is data, not code.
  * **AC:**
    * A valid factor string evaluates to the correct series; partial windows → NaN.
    * Invalid/malicious expressions are rejected with no arbitrary code execution.
    * Evaluator operates on an OHLCV frame from `db.load_*`. *(FR-18)*
  * **Files:** `src/domdhi_crypto/factors.py` (evaluator) · **Est:** M · **Status:** ✅ done · **Deps:** E12-S1

* **Story E12-S3 (Backend): Built-in factor library (port HammerGPT set)**
  * **As a** holder, **I want** ≥40 built-in factors across all categories, **So that** I start with a real library, not a blank slate.
  * **AC:**
    * ≥40 factor strings + categories loaded as data, re-homed onto E12-S1 primitives (Apache-2.0 attribution recorded in `NOTICE`).
    * Each evaluates without error on a populated DB. *(FR-18)*
  * **Files:** `src/domdhi_crypto/factors.py` (builtin data), `NOTICE` · **Est:** M · **Status:** ✅ done · **Deps:** E12-S2

---

### Epic 13: Edge Validation

**Objective:** Measure whether factors predict, and backtest strategies honestly (FR-19, FR-20, FR-21). Adds `effectiveness.py`, `backtest/`.

* **Story E13-S1 (Backend): IC / ICIR factor effectiveness**
  * **As a** holder, **I want** each factor scored by IC/ICIR vs forward returns, **So that** I know which signals actually predict.
  * **AC:**
    * IC matches a hand-computed rank-correlation reference within tolerance.
    * A future-data factor scores IC ≈ 0 on honest windows (sanity guard).
    * CLI reports IC/ICIR per factor, ranked. *(FR-19, NFR-C2-2)*
  * **Files:** `src/domdhi_crypto/effectiveness.py`, `src/domdhi_crypto/cli.py` (new `factors` subcommand) · **Est:** M · **Status:** ✅ done · **Deps:** E12-S2

* **Story E13-S2 (Backend): Look-ahead-safe event backtester**
  * **As a** holder, **I want** a backtester that can never see future bars, **So that** reported edge is real, not leaked.
  * **AC:**
    * At event time T, no bar with ts > T is ever returned (tested look-ahead guard).
    * Returns trade records + stats (return, win-rate, max drawdown) net of modeled slippage/fees.
    * Deterministic across re-runs. *(FR-20, NFR-C2-2)*
  * **Files:** `src/domdhi_crypto/backtest/{engine,virtual_account,execution_simulator,data_provider}.py` · **Est:** L · **Status:** ✅ done · **Deps:** E12-S2

* **Story E13-S3 (Backend): By-factor attribution**
  * **As a** holder, **I want** outcomes decomposed by factor, **So that** wins/losses are explainable.
  * **AC:** A completed backtest yields per-factor contribution. *(FR-21)*
  * **Files:** `src/domdhi_crypto/backtest/attribution.py` · **Est:** M · **Status:** ✅ done · **Deps:** E13-S2

---

## Phase 6: Agent Decision Interface

**Goal:** Let an LLM agent consume the substrate + portfolio context and return explainable decisions.

**Status:** ✅ done.

---

### Epic 14: MCP Decision Interface

**Objective:** Expose signals/context to Claude and define the decision contract (FR-22, FR-23).

* **Story E14-S1 (Backend): MCP signal + context server**
  * **As an** agent operator, **I want** an MCP server exposing signals, the factor menu, and positions, **So that** Claude can reason over my portfolio locally.
  * **AC:**
    * MCP context tool returns schema-valid structured data (signals + positions + factor menu from E12-S1 metadata).
    * Runs locally/offline against `crypto.db`; no live-exchange calls. *(FR-22, NFR-C2-3)*
  * **Files:** `src/domdhi_crypto/mcp_server.py` · **Est:** L · **Status:** ✅ done · **Deps:** E12-S3, E13-S1

* **Story E14-S2 (Backend): Decision contract (output schema + trigger context)**
  * **As an** agent operator, **I want** decisions to carry trigger context and return a validated JSON schema with cited rationale, **So that** outputs are parseable and explainable.
  * **AC:** Decision response validates against the JSON schema (action buy/hold/sell/nothing + rationale + cited factors); triggers are event-driven. *(FR-23)*
  * **Files:** `src/domdhi_crypto/mcp_server.py`, `src/domdhi_crypto/decision.py` · **Est:** M · **Status:** ✅ done · **Deps:** E14-S1

---

## Phase 7: Output & Portfolio Context

**Goal:** Surface decisions on a schedule and add just-enough portfolio context to weight them.

**Status:** ✅ done.

---

### Epic 15: Alerts & Scheduled Digest

* **Story E15-S1 (Backend): Threshold rules + `digest` command**
  * **As a** holder, **I want** a `digest` command that summarizes triggered signals + agent rationale to a file, **So that** `/schedule` can drop a daily brief into my vault.
  * **AC:** Given threshold rules + a populated DB, `digest` writes a Markdown brief; no server/push service. *(FR-24, NFR-C2-3)*
  * **Files:** `src/domdhi_crypto/digest.py`, `src/domdhi_crypto/cli.py` · **Est:** M · **Status:** ✅ done · **Deps:** E13-S1

### Epic 16: Portfolio Context (thin)

* **Story E16-S1 (Database): Schema migrations scaffolding**
  * **As a** maintainer, **I want** a `schema_version` table + ordered migrations, **So that** the DB can become a partial source-of-truth without "delete and re-ingest."
  * **AC:** Migrations apply idempotently and version-track; existing data preserved. *(NFR-C2-5)*
  * **Files:** `src/domdhi_crypto/db.py` (migrations) · **Est:** M · **Status:** ✅ done · **Deps:** None

* **Story E16-S2 (Backend): NAV-over-time + thin ledger**
  * **As a** holder, **I want** NAV history from stored snapshots and optional derived cost basis, **So that** decisions are position-aware. (Not a tax/rebalancing tracker.)
  * **AC:** NAV dated series from snapshots; `transactions` table → derived realized/unrealized P/L. *(FR-25)*
  * **Files:** `src/domdhi_crypto/ledger.py`, `src/domdhi_crypto/db.py` · **Est:** L · **Status:** ✅ done · **Deps:** E16-S1

* **Story E16-S3 (Backend): Portfolio-level risk (`risk.py` leaf)**
  * **As a** holder, **I want** correlation/vol/beta/drawdown across holdings, **So that** I can see real diversification.
  * **AC:** Correlation matrix + portfolio vol + beta-to-BTC from ≥2 close series; under-window → NaN. *(FR-26)*
  * **Files:** `src/domdhi_crypto/risk.py` · **Est:** M · **Status:** ✅ done · **Deps:** None

---

## Deferred (Won't — this version)

### Epic 17: Gated Live Execution Adapter (FR-27)
Delegate paper-then-live orders to Freqtrade/CCXT behind a hard human gate (withdrawal-disabled, IP-allowlisted keys, hard caps, kill-switch). The distant "run" rung — captured, not scheduled. Revisit only after the "Alpha Arena for one" paper-trading loop proves edge.

---

## Story Index

| Story | Title | Phase | Epic | Estimate | Status | Dependencies |
|-------|-------|-------|------|----------|--------|-------------|
| E12-S1 | Pure-numpy factor primitive registry | 5 | Signal Substrate | L | ✅ done | None |
| E12-S2 | Safe declarative factor expression evaluator | 5 | Signal Substrate | M | ✅ done | E12-S1 |
| E12-S3 | Built-in factor library (port HammerGPT set) | 5 | Signal Substrate | M | ✅ done | E12-S2 |
| E13-S1 | IC / ICIR factor effectiveness | 5 | Edge Validation | M | ✅ done | E12-S2 |
| E13-S2 | Look-ahead-safe event backtester | 5 | Edge Validation | L | ✅ done | E12-S2 |
| E13-S3 | By-factor attribution | 5 | Edge Validation | M | ✅ done | E13-S2 |
| E14-S1 | MCP signal + context server | 6 | MCP Interface | L | ✅ done | E12-S3, E13-S1 |
| E14-S2 | Decision contract (schema + trigger context) | 6 | MCP Interface | M | ✅ done | E14-S1 |
| E15-S1 | Threshold rules + `digest` command | 7 | Alerts & Digest | M | ✅ done | E13-S1 |
| E16-S1 | Schema migrations scaffolding | 7 | Portfolio Context | M | ✅ done | None |
| E16-S2 | NAV-over-time + thin ledger | 7 | Portfolio Context | L | ✅ done | E16-S1 |
| E16-S3 | Portfolio-level risk (`risk.py`) | 7 | Portfolio Context | M | ✅ done | None |

---

## FR Coverage Map

| Requirement | Priority | Story |
|-------------|----------|-------|
| FR-17 Factor primitive registry | Must | E12-S1 |
| FR-18 Declarative factor expressions | Must | E12-S2, E12-S3 |
| FR-19 IC/ICIR effectiveness | Must | E13-S1 |
| FR-20 Look-ahead-safe backtester | Must | E13-S2 |
| FR-21 By-factor attribution | Should | E13-S3 |
| FR-22 MCP signal+context surface | Must | E14-S1 |
| FR-23 Decision contract | Should | E14-S2 |
| FR-24 Alerts & digest | Should | E15-S1 |
| FR-25 NAV + thin ledger | Could | E16-S2 (+ E16-S1 migrations) |
| FR-26 Portfolio-level risk | Should | E16-S3 |
| FR-27 Gated execution adapter | Won't (this version) | Epic 17 (deferred) |

---

## Notes on Wave Safety
- **Phase 5 spine is sequential within Epic 12** (S1→S2→S3) but Epic 13 stories fan out from E12-S2. E16-S1 and E16-S3 own unique files and can run in parallel with Phase 5.
- New compute modules are **pure leaves** (`factors.py`, `risk.py`, `effectiveness.py`) or apex (`mcp_server.py`, `cli.py`); the acyclic import graph (NFR-M1) is preserved.
- **License + `pandas-ta` guard** are cross-cutting: decide the project license before E12-S3 (lifting Apache-2.0 factor strings); CI must keep failing if `pandas-ta` is imported.

## Related Documents
- Brief: [../_project-brief.md](../_project-brief.md) · PRD: [../_project-requirements.md](../_project-requirements.md)
- Architecture (carried forward): [../_project-architecture.md](../_project-architecture.md)
- Feature ideas: [_feature-ideas.md](_feature-ideas.md) · Evidence digest: [../.output/work/260606-1214/evolve-evidence.md](../.output/work/260606-1214/evolve-evidence.md)
- Cycle 1 archive: [_archive/cycle-1-260606-1214/](_archive/cycle-1-260606-1214/)
