# Project Brief: Domdhi.Crypto

| Attribute | Value |
|-----------|-------|
| **Author** | product-strategist (via `/onboard`) |
| **Date** | 2026-06-06 |
| **Status** | Reverse-Engineered (brownfield) |
| **Version** | 1.0 |

> **Context / Reverse-Engineering Mode.** This brief is extracted from a working codebase (commit `ad85772`), not authored ahead of it. The vision, users, scope, and constraints are read from `README.md`, `docs/_project-architecture.md`, and `docs/_project-context.md`. Items not stated outright in those sources but reasonably implied are marked **(inferred)**. There are no production users and no original PRD — this records what the tool already *is* and the strategic frame it already serves.

---

## Vision

Domdhi.Crypto is a self-hosted, local-first crypto portfolio and technical-analysis engine: it pulls live prices from CoinGecko, stores them in a local SQLite database, computes hand-rolled TA indicators, and renders an offline single-file HTML dashboard — so a technical holder gets portfolio tracking and trading signals **without ever handing their API key or holdings to a SaaS**.

## Problem Statement

### The Problem

A technically-comfortable individual crypto holder who wants portfolio tracking *and* technical-analysis signals has to choose between convenience and privacy. The convenient options — hosted portfolio trackers and dashboards-as-a-service — require an account, often request exchange/wallet connections or API keys, and run their analysis on someone else's servers with telemetry attached. The holder's exact positions and cost basis become someone else's data.

### Current State

Holders today reach for hosted trackers (CoinGecko/CoinMarketCap portfolios, CoinStats, Delta, and similar), exchange-native portfolio views, or hand-built spreadsheets. The pain points the tool exists to relieve:
- **Privacy leakage**: holdings, cost basis, and keys live in a third-party cloud, with telemetry the user can't audit.
- **Black-box indicators**: signals are computed by closed code the user can't inspect or verify against textbook references.
- **Online dependence**: a "dashboard-as-a-service" needs a network and a running service to view your own numbers.
- **Spreadsheets**: private and offline, but have no TA engine — the user does the math by hand. *(inferred — spreadsheets are the obvious fallback, not named in the sources.)*

### Desired State

The holder runs a CLI on their own machine, pulls data once, and gets a dark, offline HTML dashboard plus per-coin buy/hold/sell-ish signals — with the API key, holdings, price database, and rendered dashboard all git-ignored and never leaving the machine. The indicator math is hand-rolled in plain pandas/numpy, so it is auditable and verifiable against textbook references rather than trusted on faith.

---

## Target Users

### Primary Persona: The self-custody technical holder

- **Who**: A single technically-comfortable individual crypto holder who is comfortable on a command line, can edit a JSON config, and runs `pip install` without help. (The repo is a personal tooling project with one author and no other users.)
- **Goal**: Track portfolio value and unrealized P/L, and read technical signals (RSI, MACD, moving-average regime, etc.) per coin — on their own terms, offline, with no account.
- **Pain**: Unwilling to hand holdings, cost basis, or an API key to a hosted tracker; wants indicator math they can audit rather than a black box.
- **Frequency**: A daily ritual — `domdhi-crypto ingest && domdhi-crypto dashboard --open` — plus ad-hoc per-coin `ta` lookups. *(inferred cadence from the README's "daily ritual" framing.)*

> This is a **single-persona** product. There is deliberately no secondary persona — no admin, no multi-user, no "team" role. The tool is built for one user on one machine, and that constraint is load-bearing across the whole design.

---

## Key Features (High Level)

These features are **already built**; they constitute the current, shipped scope. Priorities below describe what is core to the product's identity (Must Have) versus refinements and explicitly-deferred ideas — not a forward build order.

| # | Feature | Priority | Description |
|---|---------|----------|-------------|
| 1 | Local-first privacy model | Must Have | API key, holdings/cost basis, price database, and rendered dashboard all live on the user's machine and are git-ignored by default; the repo ships only `*.example.json` templates. This is the whole point of the tool. |
| 2 | CLI with the core workflow | Must Have | A `domdhi-crypto` command with `init`, `ingest`, `ta`, `report`, `dashboard` subcommands that drive the end-to-end ritual from a single machine. |
| 3 | CoinGecko price ingestion | Must Have | Fetch live snapshot + daily history for the user's coins (demo/pro tiers), with polite pacing and 429 backoff, persisted idempotently so re-runs never duplicate and back-fill gaps. |
| 4 | Hand-rolled TA indicators + signals | Must Have | Auditable RSI, MACD, Bollinger+%B, ATR, SMAs, and annualized volatility in pure pandas/numpy (no `pandas-ta`), plus plain-language buy/hold/sell-ish signals (RSI thresholds, MACD histogram, SMA200 regime, golden/death cross, Bollinger stretch). |
| 5 | Offline single-file HTML dashboard | Must Have | One self-contained `dashboard.html` (inline SVG charts, dark theme): summary cards, allocation bars, holdings table with P/L and signal pills, per-coin price+RSI charts — opens from disk with no server, CDN, or JS framework. |
| 6 | Terminal reports | Should Have | `ta <symbol>` and `report` print indicator readouts and live portfolio value/P/L/signals directly to the terminal for a quick, no-browser check. |
| 7 | Relocatable data directory | Should Have | `$DOMDHI_CRYPTO_HOME` lets the user point all runtime files at a chosen folder (e.g. an Obsidian vault) instead of the current directory. |
| 8 | Stablecoin handling | Could Have | A `"stable": true` flag in `coins.local.json` counts a coin toward portfolio value but skips it for history ingestion and TA, avoiding meaningless signals on pegged assets. |
| 9 | Finer-grained OHLC / ATR pulls | Could Have | `ingest --days 30` trades history depth for daily-granularity OHLC candles so ATR is computed on daily rather than 4-day candles. |
| 10 | Cloud/SaaS hosting & multi-user | Won't Have | Explicitly rejected — see Out of Scope. A hosted, multi-user version would contradict the local-first vision. |

---

## Success Metrics

Framed modestly, as fits a personal tool with no commercial or growth goals. Success is "the ritual works and nothing leaks," not adoption.

| Metric | Target | How Measured |
|--------|--------|-------------|
| Daily ritual completes end-to-end | `ingest` → `dashboard --open` runs without error on a populated config | Run the ritual; exit code 0 and a rendered `dashboard.html` |
| Indicator correctness | Hand-rolled indicators match textbook references | The 27 unit tests pass (`tests/test_ta.py` cross-checks the math; `test_db.py`, `test_coingecko.py` cover storage + client) |
| Zero data leakage | No secrets, keys, or holdings ever committed | `crypto.db`, `coins.local.json`, `config.local.json`, `dashboard.html` are git-ignored; repo ships only `*.example.json` |
| Offline operability | Dashboard fully functional with no network | Open `dashboard.html` from disk while offline; all charts/data render *(inferred verification method — the offline property is stated; this is how you'd check it)* |
| CI stays green across runtimes | Lint + tests pass on Python 3.11 / 3.12 / 3.13 | GitHub Actions matrix: `ruff check` + `pytest` on every push/PR |

---

## Constraints

<!-- These bound the solution space and come from the project's reality; they are not premature tool picks. The stack choices themselves (SQLite, requests, hatchling, etc.) are recorded and reasoned in docs/_project-architecture.md, which is the correct home for picks. -->

- **Timeline**: None — personal project, built across two sessions, no deadline or release commitment.
- **Budget**: $0 running cost. The free CoinGecko Demo tier is sufficient; there is no server, hosting, or paid service in the loop.
- **Technical**:
  - Must run entirely on the user's machine — **no server, no cloud component, no network exposure** beyond outbound calls to CoinGecko.
  - Must work **offline** for all analysis and rendering; the network is touched only on `ingest`.
  - Secrets and holdings **must never leave the machine** and must stay out of version control.
  - Indicators must be **dependency-light and auditable** — pure pandas/numpy, no `pandas-ta` (it breaks on numpy 2.x / Python 3.13).
  - Runtime is **Python ≥ 3.11**; runtime dependencies are limited to `requests` / `pandas` / `numpy`.
  - Bounded by **CoinGecko Demo-tier rate limits** (≈30 calls/min, history capped at 365 days) and **daily granularity** for the core indicators.
  - Quality bar is **ruff + tests only** — no static type-checking is part of the gate (per ADR-006). *(This is a recorded decision, noted here as a constraint on the quality process, not a tool pick to revisit in this brief.)*
- **Regulatory**: None binding, but the product is explicitly **not financial advice** — signals are mechanical math readouts, and the README/disclaimer make this stance load-bearing.
- **Team**: A single author. Solutions must be maintainable by one person; complexity that assumes a team (review gates, service ops, on-call) is unwarranted.

---

## Out of Scope

Explicitly **not** part of this product — these boundaries are stated in the README and architecture and are deliberate, not gaps to be filled later:

- **Multi-user, accounts, or authentication** — single user, single machine; OS file permissions are the entire access model.
- **Cloud hosting / SaaS / a served web app** — no server to run or secure; the dashboard is a static file, not a service.
- **Real-time or intraday streaming** — daily granularity only; the network is hit only on `ingest`.
- **Trade execution / order placement** — read-and-analyze only; the tool never touches an exchange or moves funds.
- **Mobile apps** — desktop CLI + browser-openable HTML only.
- **Alternative exchanges or data sources** — **CoinGecko is the single data source**; no multi-source aggregation or exchange APIs.
- **Schema migration tooling** — `CREATE TABLE IF NOT EXISTS` only; an incompatible schema change means "delete `crypto.db` and re-ingest," acceptable because the DB is a regenerable cache, not a source of truth.

---

## Open Questions

- None blocking. This is a working, reverse-engineered tool; the brief documents existing reality rather than proposing new direction.
- *(For a future maintainer, not gating)* The architecture doc flags candidate maintenance surfaces — hand-rolled TA correctness, tight CoinGecko v3 coupling, hand-built SVG/HTML, no migrations, no static typing. None is currently reported as painful; they are watch-items if the tool grows beyond its single-user intent.

---

## Appendix

### Competitive Landscape

The tool defines itself *against* hosted crypto trackers rather than competing with them on features. The relevant alternatives and the gap each leaves open:

| Alternative | What it offers | Gap Domdhi.Crypto fills |
|-------------|----------------|--------------------------|
| Hosted trackers (CoinGecko/CMC portfolios, CoinStats, Delta) | Convenient, polished, multi-device | Require an account; holdings/keys live in their cloud with telemetry — the privacy line this tool refuses to cross |
| Exchange-native portfolio views | Live, accurate for one venue | Tied to an exchange account; no auditable cross-coin TA; data lives off-machine |
| Spreadsheets | Private, offline, fully owned | No TA engine — the user computes indicators by hand *(inferred fallback)* |
| TradingView / charting platforms | Rich, authoritative indicators | Online, account-gated, not a holdings-aware portfolio tracker |

The opening is the intersection nobody serves for this one user: **private + offline + holdings-aware + auditable TA**, owned end-to-end on the user's own machine. This is a deliberately non-commercial, single-user positioning — there is no market/growth angle, and none is intended.

### Related Documents

- Architecture (tech stack, 6 ADRs, data pipeline): [_project-architecture.md](_project-architecture.md)
- Project context (quick-reference): [_project-context.md](_project-context.md)
- Product README (stated vision): [../README.md](../README.md)
- PRD / requirements: [_project-requirements.md](_project-requirements.md) *(not yet present — project began code-first)*
