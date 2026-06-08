# Project Brief: Domdhi.Crypto — Cycle 2 (Decision Cortex)

| Attribute | Value |
|-----------|-------|
| **Author** | product-strategist (via `/evolve` cycle 1→2) |
| **Date** | 2026-06-06 |
| **Status** | Active — cycle 2 planning |
| **Version** | 2.0 |

> **Evolved, not restarted.** This brief regenerates the cycle-1 vision from production evidence (see `docs/.output/work/260606-1214/evolve-evidence.md` and the cycle-1 archive). Cycle 1 shipped a complete local-first portfolio + TA engine; cycle 2 builds *up* from that substrate toward an agent-native decision layer. The cycle-1 brief is preserved at `docs/todo/_archive/cycle-1-260606-1214/_project-brief.md`.

---

## Vision

Evolve Domdhi.Crypto from a portfolio + TA tool into a **local-first, agent-native crypto *decision cortex*** — the auditable substrate that turns market data into structured, *edge-validated*, *explainable* signals an LLM agent (Claude, via MCP) consumes to make and justify trading decisions, then **delegates execution** to existing engines. Not a tracker, not an order bot: the uncrowded decision/attribution layer between them, owned end-to-end on the user's own machine.

## Problem Statement

### The Problem

The wave of "AI trades crypto" projects is loud but shallow, and the honest evidence is damning: in nof1's Alpha Arena (Dec 2025), **four of six frontier LLMs lost real money** trading autonomously. The missing piece is not a smarter trader — it's the **infrastructure that makes an agent's decisions measurable, attributable, and edge-validated *before* a cent is risked.** Today a technical holder who wants an AI to *help* them decide must choose between black-box hosted bots, sprawling example repos that hit live exchanges immediately, or heavyweight quant frameworks with no LLM-reasoning layer.

### Current State

- **Ghostfolio** owns self-hosted portfolio *tracking* (heavyweight Angular/NestJS/Postgres) — but does no TA, backtesting, or alerts.
- **Freqtrade / Jesse / Hummingbot** own *execution and backtesting* (mature quant engines) — but their "AI" is classic ML or a coding assistant, not a reasoning decision-maker.
- **Moon Dev**-style projects prove the AI-agent-trading *concept* but ship example-grade, scattered, ephemeral code (the flagship agents repo has already vanished).
- **HammerGPT/Hyper-Alpha-Arena** is the closest engineered analog (Apache-2.0) but is Docker + live-exchange + `pandas-ta` heavy.

Nobody offers a **safe, local, auditable decision-and-evaluation layer** for one user.

### Desired State

The holder runs a CLI/MCP server on their own machine. It exposes a rich library of auditable factors, scores which ones actually predict forward returns (IC/ICIR), backtests strategies without look-ahead bias, and presents Claude with structured signal + portfolio context. Claude returns a *buy / hold / sell / nothing* decision **with a cited rationale**, which the human reviews. Over time the agent paper-trades against buy-and-hold in a local arena to *prove* edge — and only at a distant, human-gated rung does any live order get placed (delegated to Freqtrade/CCXT). Everything stays offline, inspectable, and private until that final gate.

---

## Target Users

### Primary Persona: The self-custody technical holder (carried forward), now an *agent operator*

- **Who**: The same single technically-comfortable holder from cycle 1 — comfortable on a CLI, edits JSON, runs `pip install` — now wanting an AI *decision aid*, not just a dashboard.
- **Goal**: Get explainable, edge-validated trade *suggestions* over their own holdings, on their own machine, and a way to *verify* the agent has edge before trusting it with anything real.
- **Pain**: Distrusts black-box bots and the "LLM lost 63%" failure mode; wants to *see why* a signal fired and *measure* whether the strategy works before risking money.
- **Frequency**: A daily decision-support ritual + an ongoing paper-trading evaluation loop.

> Still a **single-persona, single-machine** product. The local-first/offline/privacy constraint remains load-bearing — it is the difference from every hosted competitor.

---

## Key Features (High Level)

Forward build order this cycle. Priorities use MoSCoW; the spine is Substrate → Edge Validation → Agent Interface.

| # | Feature | Priority | Description |
|---|---------|----------|-------------|
| 1 | Expression-factor registry (Signal Substrate) | Must | Factors as declarative strings over a registry of **pure-numpy** primitives (extends `ta.py`; no `pandas-ta`). Adding a factor = adding a string. Registry metadata doubles as the agent's documented factor menu. |
| 2 | Factor operator vocabulary | Must | Time-series + cross-section operators (`DELAY`, `TS_*`, `DECAYLINEAR`, `LOG_RETURN`, `NORMALIZE`, `ZSCORE`) as pure functions — the HammerGPT vocabulary minus the rejected dependency. |
| 3 | IC/ICIR factor effectiveness | Must | Rank-correlation of factor vs *forward* return; ICIR = trailing mean(IC)/std(IC). Answers "does this signal predict anything?" before any trade sim. |
| 4 | Look-ahead-safe backtester | Must | Event-driven sim: virtual account + execution simulator (slippage/fees) + a **time-gated** data provider exposing only bars ≤ event time. |
| 5 | MCP decision interface | Must | Expose signals + portfolio context as a structured MCP tool surface for Claude; enforce a `{output_format}`/`{trigger_context}` decision contract. |
| 6 | By-factor attribution | Should | "Why did the decision win/lose, by factor" — the explainability payoff. |
| 7 | Portfolio-level risk | Should | Correlation matrix, portfolio volatility, beta-to-BTC, max drawdown (new pure-leaf `risk.py`). |
| 8 | Alerts & scheduled digest | Should | Threshold rules + a daily brief (with rationale) dropped into a vault via `/schedule`. No server. |
| 9 | "Alpha Arena for one" (capstone) | Could | Local offline arena: agent paper-trades vs buy-and-hold + rule strategies, scored + attributed. The "walk" rung as the product. |
| 10 | Thin transaction/position layer | Could | NAV-over-time from stored snapshots + optional ledger for derived cost basis. NOT a full tax/rebalancing tracker. Requires schema migrations. |
| 11 | Gated live execution adapter | Won't (this version) | Delegate paper-then-live orders to Freqtrade/CCXT behind a hard human gate. The distant "run" rung. |

---

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Factor substrate works | A declared factor string evaluates to a correct series; registry serves its menu | Unit tests on the expression engine + primitives (pure-numpy, no `pandas-ta`) |
| Edge is measurable | IC/ICIR computed for every factor over stored history | `ta`/new `factors` command prints IC/ICIR; values match a hand-computed reference |
| Backtests don't lie | No look-ahead leakage | A factor using only future data scores ~0 IC; backtester refuses to read bars > event time (tested) |
| Agent gets clean context | MCP server returns structured signal+position context; decisions parse as valid JSON | MCP tool call returns schema-valid output Claude can consume |
| Privacy/offline DNA preserved | No keys/holdings leave the machine; analysis works offline | Existing git-ignore + offline checks still hold; no live-exchange calls outside the gated adapter |
| Quality bar holds | Lint + tests green on 3.11/3.12/3.13 | CI matrix; no `pandas-ta` reintroduced |

---

## Constraints

- **Timeline / Budget**: Personal project, no deadline, $0 running cost (free CoinGecko tier; no server).
- **Technical**:
  - Local-first, offline, no server/cloud beyond outbound CoinGecko (and, only at the final gated rung, a delegated execution call).
  - Indicators/factors stay **pure pandas/numpy** — **no `pandas-ta`** (ADR-001). Borrow HammerGPT *patterns and factor strings*, not its engine.
  - Secrets/holdings never leave the machine; live exchange keys (if ever) are withdrawal-disabled, IP-allowlisted, hard-capped, behind a human gate.
  - The DB becomes a **partial source-of-truth** once a ledger lands → introduces the need for **schema migrations** (a deliberate change from cycle 1's "regenerable cache").
  - Runtime Python ≥ 3.11; quality bar stays ruff + pytest (ADR-006).
- **Safety/Regulatory**: Not financial advice. Autonomous live trading is empirically a money-loser → the product is decision-*support* and *evaluation* first; live execution is the last, gated, opt-in rung.
- **Team**: Single author; complexity must stay maintainable by one person.

---

## Out of Scope (this cycle)

- **Autonomous live trading as a default** — gated, opt-in, and deferred to a future version (feature #11).
- **Reinventing portfolio tracking** (Ghostfolio's domain) — the ledger stays thin, decision-serving only.
- **Reinventing an execution/order engine** (Freqtrade's domain) — delegate, don't rebuild.
- **Multi-user / accounts / SaaS / hosted web app / mobile** — unchanged from cycle 1; single user, single machine.
- **`pandas-ta` or any heavy TA dependency** — explicitly rejected (ADR-001).

---

## Open Questions

- **License**: choose the project's license before lifting Apache-2.0 code (HammerGPT). Keep permissive to allow reuse; avoid pasting GPL/AGPL (Freqtrade/Ghostfolio). *(Should be decided early in cycle 2.)*
- **Provider abstraction timing**: do the `coingecko.py` → pluggable-provider refactor (Architecture Risk #2) before or after the substrate deepens the dependency?
- **Migration tooling**: lightweight `schema_version` table + ordered migrations vs. a library — decide when the thin ledger lands.

---

## Appendix

### Competitive Landscape (cycle 2)

| Alternative | What it owns | Gap Domdhi.Crypto fills |
|-------------|--------------|--------------------------|
| Ghostfolio | Self-hosted portfolio tracking | No TA/backtest/alerts; heavyweight web stack |
| Freqtrade / Jesse / Hummingbot | Execution + backtesting (quant) | "AI" is ML/coding-assistant, not a reasoning decision-maker |
| Moon Dev agents | Proves AI-trading concept | Example-grade, scattered, ephemeral, live-exchange-first |
| HammerGPT / nof1 Alpha Arena | Engineered/benchmarked LLM trading | Docker + live keys + `pandas-ta`; hosted/real-money — not a safe local bench |

The opening: **a safe, local, offline, auditable decision + edge-validation layer** — the durable version of what the demos skip, feeding a Claude/MCP agent, with edge proven before a cent is risked.

### Related Documents
- Evidence digest (re-plan seed): [.output/work/260606-1214/evolve-evidence.md](.output/work/260606-1214/evolve-evidence.md)
- Cycle 1 archive: [todo/_archive/cycle-1-260606-1214/](todo/_archive/cycle-1-260606-1214/)
- Feature ideas (carry-forward): [todo/_feature-ideas.md](todo/_feature-ideas.md)
- Architecture (carried forward unchanged): [_project-architecture.md](_project-architecture.md)
- PRD: [_project-requirements.md](_project-requirements.md)
