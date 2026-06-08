# Project Brief: Domdhi.Crypto — Cycle 3 (See It & Prove It)

| Attribute | Value |
|-----------|-------|
| **Author** | product-strategist (via `/evolve` cycle 2→3) |
| **Date** | 2026-06-06 |
| **Status** | Active — cycle 3 planning |
| **Version** | 3.0 |

> **Evolved, not restarted.** This brief regenerates the cycle-2 vision from evidence (see `docs/.output/work/260606-2135/evolve-evidence.md`). Cycle 2 built the complete agent-native *decision cortex* (substrate → edge validation → agent interface → digest → thin portfolio context), all green at 308 tests — but it is **headless and unproven on real data**. Cycle 3 makes that cortex **visible** (a real dashboard) and **provable** (run it on reality; paper-trade vs buy-and-hold). The cycle-2 brief is preserved at `docs/todo/_archive/cycle-2-260606-2135-decision-cortex/_project-brief.md`.

---

## Vision

Cycle 2 made the cortex *think*. Cycle 3 makes it *show its work and earn trust*. Take the auditable signal/edge/decision/portfolio engine already built and (a) **surface** it to the human in a single offline dashboard, and (b) **prove** it has edge by running the full pipeline on real market data and paper-trading the cortex's decisions against a buy-and-hold baseline in a local arena. This advances the product from *crawl* (decision-support, computed but invisible) to *walk* (decisions made visible, measured, and attributed) — without crossing the deferred *run* (live execution) gate.

## Problem Statement

### The Problem

A decision engine nobody can see and nobody has run on real data is a hypothesis, not a tool. Cycle 2 delivered sophisticated computation — factor IC/ICIR, look-ahead-safe backtests, portfolio risk, average-cost P/L — but every output is reachable only via CLI text, a Markdown file, or an MCP payload meant for an agent. The human operator has no visual surface, and **not one number has been produced from real CoinGecko history**: all 308 tests mock the network. The standing risk (nof1 Alpha Arena: 4/6 frontier LLMs lost money) is precisely what this project exists to guard against — but you cannot *guard against* what you cannot *measure and watch*.

### Current State

- The cortex spine is built and unit-tested: `factors.py`, `effectiveness.py`, `backtest/`, `context.py`/`decision.py`/`mcp_server.py`, `digest.py`, `ledger.py`, `risk.py`.
- The only visual UI, `dashboard.py`, imports just `db, ta, paths` — it renders **Cycle-1** visuals (price polylines, sparklines, RSI). None of the cycle-2 layer is visible.
- The pipeline has never been run end-to-end on real holdings; there is no evidence the agent's decisions beat (or lose to) buy-and-hold.

### Desired State

The holder runs `ingest` on their real coins, then opens one offline `dashboard.html` that shows their NAV curve and P/L, a portfolio-risk panel, which factor signals are currently triggered, and a backtest equity curve — all interactive, all offline. Separately, they run a local **arena**: the cortex paper-trades over real history while a buy-and-hold baseline runs alongside, and the result is scored and attributed by factor — answering "does this thing actually have edge?" before a cent is ever risked. Everything stays inspectable, private, and on-machine.

---

## Target Users

### Primary Persona: The self-custody technical holder, now an *agent operator* (carried forward)

- **Who**: The same single technically-comfortable holder — CLI-comfortable, edits JSON, runs `pip install` — who in cycle 2 gained an AI decision aid and now wants to *see* and *trust* it.
- **Goal**: Look at one screen and understand their position, risk, and live signals; and verify the cortex has measurable edge before relying on it.
- **Pain**: A powerful engine they can't watch and haven't validated. "Is it working? Is it any good?" is currently unanswerable.
- **Frequency**: A daily glance at the dashboard + periodic arena evaluation runs.

> Still a **single-persona, single-machine** product. Local-first/offline/privacy remains load-bearing — it is the difference from every hosted competitor.

---

## Key Features (High Level)

Build order: surface first (everything to show already exists), then prove, then harden. MoSCoW priorities.

| # | Feature | Priority | Description |
|---|---------|----------|-------------|
| 1 | Decision Dashboard (NAV + P/L) | Must | Surface `ledger.py` — NAV-over-time curve and realized/unrealized P/L — in the offline HTML via vendored uPlot (ADR-009). |
| 2 | Risk panel | Must | Correlation matrix, portfolio vol, beta-to-BTC, max-drawdown from `risk.py`, rendered in the dashboard. |
| 3 | Triggered-signals view | Must | Which `factors.py`/`digest.py` signals are currently firing, shown in the dashboard (the agent's "why now" made visible to the human). |
| 4 | Backtest equity curve | Should | Render a `backtest/` run's equity curve + by-factor attribution as interactive charts. |
| 5 | Run-on-real-data validation | Must | Execute the full `ingest → ta → factors → backtest → digest` loop on real coins; confirm every module produces sane output on live history. |
| 6 | "Alpha Arena for one" | Should | Local offline arena: paper-trade the cortex's decisions vs buy-and-hold + a simple rule baseline over real history, scored by the look-ahead-safe backtester + attribution. The "walk" rung. |
| 7 | HammerGPT 64-factor port (complete) | Should | Finish lifting the Apache-2.0 factor *strings* onto our hand-rolled primitives (cycle 2 shipped a subset). |
| 8 | Provider abstraction | Could | Make `coingecko.py` a pluggable `prices` provider to de-risk single-vendor coupling (Architecture Risk #2). |
| 9 | Stablecoin CLI guard | Should | `cmd_factors`/`cmd_backtest` should give a clear message for stablecoins instead of a misleading "Run: ingest" dead-end (Epic-13 retro). |
| 10 | Transaction-sequence validation | Could | Optional validation path for the thin ledger to reject incoherent transaction sequences (Epic-16 deferred follow-up). |
| 11 | Gated live execution adapter | Won't (this version) | The distant "run" rung — delegate live orders behind a hard human gate. Unchanged from cycle 2. |

---

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Cortex is visible | One offline `dashboard.html` renders NAV, P/L, risk, and triggered signals from the cycle-2 modules | Open the file; panels populate from `ledger`/`risk`/`factors` |
| Charts are interactive + offline | uPlot charts zoom/tooltip with no network, no build step | Load with network disabled; ADR-009 honored (no framework/server) |
| Proven on reality | The full pipeline runs on real CoinGecko history without error | A documented end-to-end run on real coins; outputs sane |
| Edge is measurable | The arena produces a cortex-vs-buy-and-hold result, attributed by factor | Arena run reports both equity curves + per-factor contribution |
| No-leak discipline holds | Arena/backtest never reads future bars | Existing look-ahead guards still pass on real data |
| Core stays minimal | 3-dep runtime core unchanged; uPlot vendored, not pip-installed | `pyproject.toml` core deps unchanged; CI green 3.11/3.12/3.13 |

---

## Constraints

- **Timeline / Budget**: Personal project, no deadline, $0 running cost (free CoinGecko tier; no server).
- **Technical**:
  - Local-first, offline, no server/cloud beyond outbound CoinGecko.
  - **Dashboard: single offline HTML file, vendored uPlot, no frontend framework, no server, no build step (ADR-009).** uPlot is a string the generator inlines — *not* a Python dependency; the 3-dep core (ADR-007) is untouched.
  - Indicators/factors stay **pure pandas/numpy** — **no `pandas-ta`** (ADR-001).
  - The DB remains a **partial source-of-truth** (ADR-008); schema change goes through `db.migrate()` (add-only).
  - Runtime Python ≥ 3.11; quality bar stays ruff + pytest (ADR-006).
- **Safety/Regulatory**: Not financial advice. The arena is *paper-trading only*; live execution stays the last, gated, opt-in rung (out of scope this cycle).
- **Team**: Single author; complexity must stay maintainable by one person.

---

## Out of Scope (this cycle)

- **Live trading / order placement** — Epic 17 gated adapter remains Won't (this version).
- **A served/dynamic web app, React/Astro, or any Node toolchain** — explicitly rejected in ADR-009.
- **Reinventing portfolio tracking** (Ghostfolio's domain) — the ledger and dashboard stay decision-serving, not a full tax/rebalancing tool.
- **Multi-user / accounts / SaaS / mobile** — unchanged; single user, single machine.
- **`pandas-ta` or any heavy TA dependency** (ADR-001).

---

## Open Questions

- **uPlot version pin**: which uPlot release to vendor, and where to record its provenance/license attribution next to the blob (ADR-009 maintenance note).
- **Arena baseline set**: buy-and-hold is a must; is a single rule strategy (e.g. SMA-cross) enough as the second baseline for cycle 3, or also an equal-weight rebalance?
- **Real-data run cadence**: the validation run (feature #5) needs a small real coin set — reuse `coins.local.json` as-is, or a dedicated arena config?

---

## Appendix

### Competitive Landscape (carried forward from cycle 2)

| Alternative | What it owns | Gap Domdhi.Crypto fills |
|-------------|--------------|--------------------------|
| Ghostfolio | Self-hosted portfolio tracking | No TA/backtest/alerts; heavyweight web stack |
| Freqtrade / Jesse / Hummingbot | Execution + backtesting (quant) | "AI" is ML/coding-assistant, not a reasoning decision-maker |
| Moon Dev agents | Proves AI-trading concept | Example-grade, scattered, ephemeral, live-exchange-first |
| HammerGPT / nof1 Alpha Arena | Engineered/benchmarked LLM trading | Docker + live keys + `pandas-ta`; hosted/real-money — not a safe local bench |

The opening remains **a safe, local, offline, auditable decision + edge-validation layer** — and cycle 3 closes the last gap the demos skip: making it *watchable* and *provably better than buy-and-hold* before any real risk.

### Related Documents
- Evidence digest (re-plan seed): [.output/work/260606-2135/evolve-evidence.md](.output/work/260606-2135/evolve-evidence.md)
- Cycle 2 archive: [todo/_archive/cycle-2-260606-2135-decision-cortex/](todo/_archive/cycle-2-260606-2135-decision-cortex/)
- Feature ideas (carry-forward): [todo/_feature-ideas.md](todo/_feature-ideas.md)
- Architecture (carried forward; ADR-009 added this cycle): [_project-architecture.md](_project-architecture.md)
- PRD: [_project-requirements.md](_project-requirements.md)
