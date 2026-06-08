# Product Requirements Document: Domdhi.Crypto — Cycle 2 (Decision Cortex)

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Version** | 2.0 |
| **Status** | Active — cycle 2 planning |
| **Author** | product-strategist (via `/evolve` cycle 1→2) |
| **Date** | 2026-06-06 |
| **Tech Stack** | Python ≥3.11 (src-layout CLI + MCP server) · requests / pandas / numpy (no `pandas-ta`) · SQLite (stdlib) · hatchling · ruff · pytest |

> **Delta PRD, evidence-seeded.** This regenerates the requirements for cycle 2 from `docs/.output/work/260606-1214/evolve-evidence.md` + `docs/todo/_feature-ideas.md`. It assumes cycle 1's 16 shipped FRs as the **foundation** (preserved in the archive) and specifies only the *new* cycle-2 surface. Cycle 1 PRD: `docs/todo/_archive/cycle-1-260606-1214/_project-requirements.md`. New FR IDs continue at FR-17.

---

## Executive Summary

Cycle 1 shipped the local-first portfolio + TA engine (CoinGecko → SQLite → hand-rolled TA → offline HTML). Cycle 2 evolves it into a **decision cortex**: a richer auditable factor substrate, rigorous edge validation (IC/ICIR + look-ahead-safe backtesting), and an MCP interface that lets an LLM agent reason over signals + portfolio context and return *explainable* decisions — with execution delegated and gated. The DNA (local-first, offline, pure-numpy, single-user, not-financial-advice) carries forward unchanged; the one deliberate shift is that the DB becomes a partial source-of-truth (requiring migrations) once a thin ledger lands.

---

## User Personas

Unchanged from cycle 1 — the single self-custody technical holder, now operating an AI decision aid. No second persona. See the cycle-1 PRD (archived) for the full profile.

---

## Functional Requirements

> New modules extend `src/domdhi_crypto/`, preserving the strictly-acyclic import graph (`ta`, `risk` are leaves; `cli`/MCP server are apex).

### Module A: Signal Substrate (`factors.py` + extended `ta.py`)

#### FR-17: Pure-numpy factor primitive registry
- **Priority**: Must Have
- **Description**: A `FUNCTION_REGISTRY` of factor primitives implemented in pure pandas/numpy (no `pandas-ta`), each with metadata (signature, description, example, category). Covers moving averages, momentum, trend, volatility, volume, time-series operators (`DELAY`, `TS_SUM/MEAN/STD/MAX/MIN/RANK/CORR/ARGMAX`, `DECAYLINEAR`, `LOG_RETURN`), cross-section (`RANK`, `ZSCORE`, `NORMALIZE`), and math.
- **Acceptance Criteria**:
  - Given a registered primitive, When called on a known series, Then its output matches a textbook/reference value within tolerance.
  - Given the registry, When queried, Then it returns each function's metadata (for both humans and the agent's factor menu).
  - Given the import graph, When the module is imported, Then it pulls only numpy/pandas — **`pandas-ta` is absent** (ADR-001 preserved).

#### FR-18: Declarative factor expressions
- **Priority**: Must Have
- **Description**: A factor is a declarative string (e.g. `"(close-EMA(close,200))/close"`) evaluated safely over the registry against an OHLCV frame. Built-in factors are stored as data (strings + category), seeded from the (Apache-2.0) HammerGPT factor set, re-homed onto FR-17 primitives.
- **Acceptance Criteria**:
  - Given a valid factor string, When evaluated, Then it returns the correct series; partial windows surface as NaN (never fabricated).
  - Given a malicious/invalid expression, When evaluated, Then it is rejected safely (no arbitrary code execution).
  - Given the built-in set, When loaded, Then ≥40 factors across all categories are available as data without new Python code per factor.

### Module B: Edge Validation (`effectiveness.py`, `backtest/`)

#### FR-19: IC / ICIR factor effectiveness
- **Priority**: Must Have
- **Description**: Compute each factor's Information Coefficient (rank correlation of factor value vs *forward* return) and ICIR (trailing mean(IC)/std(IC)) over a sliding window, in pure numpy.
- **Acceptance Criteria**:
  - Given a factor and price history, When IC is computed, Then it matches a hand-computed rank-correlation reference within tolerance.
  - Given a factor built from *future* data, When scored, Then IC ≈ 0 over honest (non-leaking) windows (sanity guard).
  - Given the CLI, When `factors` (or equivalent) runs, Then IC/ICIR per factor is reported, ranked.

#### FR-20: Look-ahead-safe event backtester
- **Priority**: Must Have
- **Description**: Event-driven backtest with a virtual account, an execution simulator (slippage + fees), and a **time-gated** historical data provider that exposes only bars at or before the current event timestamp.
- **Acceptance Criteria**:
  - Given a backtest at event time T, When a strategy requests data, Then no bar with timestamp > T is ever returned (look-ahead guard; tested).
  - Given a strategy + history, When the backtest runs, Then it returns trade records + stats (return, win-rate, max drawdown) net of modeled slippage/fees.
  - Given an empty/again-run config, Then results are deterministic and reproducible.

#### FR-21: By-factor attribution
- **Priority**: Should Have
- **Description**: Decompose a backtest/decision outcome by contributing factor, so wins/losses are explainable.
- **Acceptance Criteria**: Given a completed backtest, When attribution runs, Then per-factor contribution is reported.

### Module C: Agent Decision Interface (MCP server)

#### FR-22: MCP signal + context tool surface
- **Priority**: Must Have
- **Description**: An MCP server exposes tools returning structured signal values, factor menu (from FR-17 metadata), and portfolio/position context for the agent to consume.
- **Acceptance Criteria**:
  - Given an MCP client (Claude), When it calls the context tool, Then it receives schema-valid structured data (signals + positions + factor menu).
  - Given the server, When run, Then it operates locally/offline against `crypto.db` with no live-exchange calls.

#### FR-23: Decision contract
- **Priority**: Should Have
- **Description**: A decision request carries `{trigger_context}` (why-now + signal values + position) and demands `{output_format}` — a JSON decision schema (action: buy/hold/sell/nothing + rationale + cited factors). Triggers are event-driven (signal/scheduled), not continuous poll.
- **Acceptance Criteria**: Given a decision request, When the agent responds, Then output validates against the JSON schema and includes a cited rationale.

### Module D: Output Channel (`digest.py`)

#### FR-24: Alerts & scheduled digest
- **Priority**: Should Have
- **Description**: Threshold rules over signals/IC; a `digest` command emits a summary (with rationale) to a file, pairable with `/schedule`. No server, no push service.
- **Acceptance Criteria**: Given threshold rules and a populated DB, When `digest` runs, Then a Markdown brief is written summarizing triggered signals + agent rationale.

### Module E: Portfolio Context (thin — `ledger.py`, `risk.py`)

#### FR-25: NAV-over-time + thin ledger
- **Priority**: Could Have
- **Description**: Derive portfolio NAV time-series from stored snapshots; optional `transactions` table for derived cost basis + realized/unrealized P/L. **Not** a full tax-lot/rebalancing tracker.
- **Acceptance Criteria**: Given snapshots, When NAV history is requested, Then a dated value series is returned; given transactions, When cost basis is derived, Then realized/unrealized P/L is computed.

#### FR-26: Portfolio-level risk
- **Priority**: Should Have
- **Description**: Correlation matrix across holdings, portfolio volatility, beta-to-BTC, max drawdown — pure numpy/pandas in a new leaf `risk.py`.
- **Acceptance Criteria**: Given ≥2 coins' close series, When risk is computed, Then a correlation matrix + portfolio vol + beta are returned; under-window inputs surface NaN.

#### FR-27: Gated live execution adapter
- **Priority**: Won't Have (this version)
- **Description**: Delegate paper-then-live orders to Freqtrade/CCXT behind a hard human-in-the-loop gate (withdrawal-disabled, IP-allowlisted keys, hard caps, kill-switch). Deferred — captured for the future "run" rung.

---

## Non-Functional Requirements

- **NFR-C2-1 (Auditability)**: All factor/indicator/IC math is pure, inspectable pandas/numpy. **No `pandas-ta`** or other heavy TA dependency (ADR-001 preserved).
- **NFR-C2-2 (Look-ahead safety)**: No backtest/effectiveness computation may read data beyond the evaluation timestamp. Enforced and tested.
- **NFR-C2-3 (Local-first / offline)**: All analysis, scoring, backtesting, and the MCP server run offline against local state. Network is hit only on `ingest` (and, only at the gated execution rung, a delegated order call).
- **NFR-C2-4 (Privacy)**: Keys/holdings never leave the machine; all runtime files git-ignored. Live exchange keys (future) are gated, scoped, capped.
- **NFR-C2-5 (Data integrity / migrations)**: Once a ledger makes the DB a partial source-of-truth, schema evolution uses ordered migrations + a `schema_version` marker (no more "delete and re-ingest").
- **NFR-C2-6 (Quality bar)**: ruff + pytest on 3.11/3.12/3.13 stays green; no static type-checking added (ADR-006).
- **NFR-C2-7 (Not financial advice)**: Decisions/signals are mechanical readouts + agent reasoning, surfaced as *support*; autonomous live trading is gated and opt-in.

---

## Out of Scope (this cycle)
Autonomous live trading by default (FR-27 deferred); reinventing tracking (Ghostfolio) or execution engines (Freqtrade); multi-user/SaaS/mobile; `pandas-ta`.

## Related Documents
- Brief: [_project-brief.md](_project-brief.md) · Architecture (carried forward): [_project-architecture.md](_project-architecture.md)
- Evidence digest: [.output/work/260606-1214/evolve-evidence.md](.output/work/260606-1214/evolve-evidence.md)
- Feature ideas: [todo/_feature-ideas.md](todo/_feature-ideas.md) · Backlog: [todo/_backlog.md](todo/_backlog.md)
