# Product Requirements Document: Domdhi.Crypto

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Version** | 1.0 |
| **Status** | Reverse-Engineered (brownfield) |
| **Author** | product-strategist (via `/onboard`) |
| **Date** | 2026-06-06 |
| **Tech Stack** | Python ≥3.11 (src-layout CLI) · requests / pandas / numpy · SQLite (stdlib) · hatchling · ruff · pytest |

> **Context / Reverse-Engineering Mode.** This PRD is extracted from a working codebase at commit `ad85772`, not authored ahead of it. Every functional requirement below describes behavior that **already ships** in `src/domdhi_crypto/`, and its acceptance criteria are grounded in observed code and the 27 existing unit tests (`tests/test_ta.py`, `tests/test_db.py`, `tests/test_coingecko.py`). MoSCoW priorities are read *backward* from what was actually built: shipped, load-bearing behavior is **Must Have**; genuine refinements are **Should/Could Have**; explicitly-rejected directions from the brief are **Won't Have**. Items the sources imply but do not state outright are marked **(inferred)**. Sources of truth: [`_project-brief.md`](_project-brief.md), [`_project-architecture.md`](_project-architecture.md), [`_project-context.md`](_project-context.md), [`../README.md`](../README.md), [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

---

## Executive Summary

Domdhi.Crypto is a self-hosted, local-first crypto portfolio and technical-analysis engine. It pulls live prices and daily history from the CoinGecko REST API, stores them in a local SQLite database, computes a set of hand-rolled technical indicators (RSI, MACD, Bollinger Bands, ATR, SMAs, annualized volatility) over the price history, and renders the results two ways — as terminal reports and as a single self-contained offline HTML dashboard with inline-SVG charts. The user drives the whole thing from one `domdhi-crypto` command on their own machine.

The product exists to resolve a forced trade-off between **convenience and privacy**. Hosted portfolio trackers are polished and multi-device, but they require an account, often want exchange or wallet connections, and run their indicator math on someone else's servers with telemetry the user cannot audit. Domdhi.Crypto refuses that trade: the API key, the holdings and cost basis, the price database, and the rendered dashboard all stay on the user's machine and are git-ignored by default. The indicator math is hand-rolled in plain pandas/numpy so it is auditable and verifiable against textbook references rather than trusted on faith.

This is a deliberately non-commercial, **single-user** product — one author, one machine, no accounts, no multi-tenancy, no server. That constraint is load-bearing across the entire design and shapes every requirement in this document. The product is explicitly **not financial advice**: signals are mechanical readouts of math, not recommendations.

---

## User Personas

### Persona 1: The self-custody technical holder (primary — and only)

- **Background**: A single technically-comfortable individual crypto holder. Comfortable on a command line, can edit a JSON config by hand, and runs `pip install` without help. The repository is a personal tooling project with one author and no other users.
- **Goals**: Track portfolio value and unrealized P/L, and read technical signals (RSI, MACD, moving-average regime, golden/death cross, etc.) per coin — on their own terms, offline, with no account.
- **Frustrations**: Unwilling to hand holdings, cost basis, or an API key to a hosted tracker; distrusts black-box indicators they cannot inspect; resents needing a network and a running service just to view their own numbers.
- **Tech Comfort**: **High** (CLI-fluent, edits JSON, installs Python packages).

> **There is deliberately no second persona.** No admin, no multi-user role, no "team" member, no end-customer. The tool is built for one user on one machine; OS file permissions are the entire access model. Inventing a secondary persona would contradict the product's core constraint.

---

## Functional Requirements

> Modules below mirror `src/domdhi_crypto/`. The import graph is strictly acyclic (`paths`/`ta` are leaves; `cli` is the apex). FR IDs are stable references for the backlog and architecture docs.

### Module 1: CLI Orchestrator (`cli.py`, `__main__.py`)

#### FR-1: Subcommand-driven workflow
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: An `argparse`-based `domdhi-crypto` command exposes five subcommands — `init`, `ingest [--days N]`, `ta <symbol>`, `report`, `dashboard [--open]` — that drive the end-to-end ritual. The same entry point is reachable as `python -m domdhi_crypto <command>`.
- **Acceptance Criteria**:
  - Given the package is installed, When the user runs `domdhi-crypto <subcommand>`, Then the matching `cmd_*` handler executes and the process exits `0` on success.
  - Given the package is installed, When the user runs `python -m domdhi_crypto <subcommand>`, Then it behaves identically to the console script (both resolve to `cli.main`).
  - Given no subcommand (or an unknown one) is supplied, When the CLI parses arguments, Then argparse prints usage/help rather than crashing with a traceback.
- **Notes**: `ingest` accepts `--days` (default 365); `ta` requires a `<symbol>` positional; `dashboard` accepts `--open`.

#### FR-2: Coin resolution by id or symbol
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: Commands that target one coin (`ta`) resolve the user's argument against `coins.local.json` by either CoinGecko id (e.g. `bitcoin`) or ticker symbol (e.g. `BTC`), case-insensitively.
- **Acceptance Criteria**:
  - Given `coins.local.json` lists `{"id":"bitcoin","symbol":"BTC"}`, When the user runs `domdhi-crypto ta BTC` or `domdhi-crypto ta bitcoin`, Then the same coin is selected.
  - Given a symbol/id not present in `coins.local.json`, When the user runs `ta` against it, Then the CLI exits with a `SystemExit` message naming the unknown coin rather than silently producing empty output.

#### FR-3: Per-coin failure isolation during ingest
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: During `ingest`, a fetch/store failure on one coin is caught, printed as a warning, and skipped so the run continues for the remaining coins. Each coin commits independently.
- **Acceptance Criteria**:
  - Given a multi-coin `coins.local.json` where one coin's history fetch raises, When `ingest` runs, Then a `! …failed` warning is printed for that coin and the other coins are still ingested and committed.
  - Given a coin's ingest committed before a later coin failed, When the run ends, Then the earlier coin's rows remain persisted (per-coin commit).

#### FR-4: Stablecoin handling
- **Priority**: Could Have
- **Persona**: Self-custody technical holder
- **Description**: A coin flagged `"stable": true` in `coins.local.json` counts toward portfolio value but is skipped for history ingestion and TA, so the user is not shown meaningless signals on a pegged asset.
- **Acceptance Criteria**:
  - Given a coin with `"stable": true`, When `ingest` runs, Then no `market_chart`/`ohlc` history is fetched or stored for it.
  - Given a stablecoin holding, When `report`/`dashboard` compute portfolio value, Then the stablecoin's `amount × price` is still included in total value.

### Module 2: Data Ingestion — CoinGecko client (`coingecko.py`)

#### FR-5: Tiered CoinGecko client wiring (demo / pro)
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: The client reads `api_key` and `tier` from `config.local.json` and wires the correct base host and auth-header name: `tier: "demo"` → `api.coingecko.com` with `x-cg-demo-api-key`; `tier: "pro"` → `pro-api.coingecko.com` with `x-cg-pro-api-key`.
- **Acceptance Criteria**:
  - Given `tier: "demo"`, When a `CoinGecko` client is constructed, Then `base` is the demo host and the session carries an `x-cg-demo-api-key` header. *(test_coingecko)*
  - Given `tier: "pro"`, When a client is constructed, Then `base` is the pro host and the session carries an `x-cg-pro-api-key` header. *(test_coingecko)*
  - Given `tier` is absent, When a client is constructed, Then it defaults to the demo wiring.
- **Notes**: `requests` is imported lazily inside `CoinGecko.__init__`, so non-network commands do not pay for it.

#### FR-6: Rate-limit backoff and polite pacing
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: On HTTP 429 the client backs off `5 · 2^attempt` seconds and retries up to 4 attempts before giving up; a fixed inter-call pause (default 2.0s) follows each successful call; other non-2xx responses raise via `raise_for_status`.
- **Acceptance Criteria**:
  - Given the API returns 429 then 200, When `_get` is called, Then it sleeps, retries, and returns the 200 payload. *(test_coingecko)*
  - Given the API returns 429 on every attempt, When `_get` exhausts its 4 retries, Then it raises (does not silently return `None`/empty). *(test_coingecko)*
  - Given a successful (2xx) response, When `_get` returns, Then a `pause`-length sleep has occurred before returning (verifiable with a mocked clock).
- **Notes**: All tests mock the network — no test ever hits CoinGecko, and this property is a contributor constraint.

#### FR-7: Fail-fast on missing/placeholder credentials
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: A missing `config.local.json`, an empty `api_key`, or a placeholder key containing `"PASTE"` raises `SystemExit` with an actionable fix-it message rather than making a doomed request.
- **Acceptance Criteria**:
  - Given no `config.local.json` exists, When credentials load, Then `SystemExit` is raised telling the user to copy `config.example.json → config.local.json`.
  - Given `api_key` is empty or contains `"PASTE"`, When credentials load, Then `SystemExit` is raised telling the user to set their key.

### Module 3: Storage — SQLite layer (`db.py`)

#### FR-8: Schema initialization (idempotent)
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: `init` / `init_db()` creates the four-table schema (`coins`, `prices`, `ohlc`, `snapshots`) using `CREATE TABLE IF NOT EXISTS`, so it is safe to run against a fresh or already-initialized database.
- **Acceptance Criteria**:
  - Given no database file exists, When `domdhi-crypto init` runs, Then `crypto.db` is created with all four tables. *(test_db)*
  - Given the schema already exists, When `init_db()` runs again, Then it succeeds without error and does not drop or alter existing data.
- **Notes**: `connect()`/`init_db()` accept an explicit path, which is what lets the tests run against `:memory:`/temp files.

#### FR-9: Idempotent upsert ingestion
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: All writes are idempotent. `coins`/`prices`/`ohlc` use `INSERT … ON CONFLICT(pk) DO UPDATE` (latest fetch wins per key); `snapshots` use `ON CONFLICT DO NOTHING` (first write of a given timestamp wins). Re-ingesting overlapping ranges never duplicates or corrupts rows.
- **Acceptance Criteria**:
  - Given a price row for `(coin_id, date)` already exists, When the same key is upserted with new values, Then the row count is unchanged and the values are updated. *(test_db)*
  - Given `ingest` is run twice over an overlapping date range, When the second run completes, Then no duplicate `prices`/`ohlc` rows exist. *(test_db)*
  - Given a snapshot for `(coin_id, fetched_at)` already exists, When the same timestamp is inserted again, Then the insert is a no-op (no error, no duplicate). *(test_db)*

#### FR-10: Gap-filled daily close series for analysis
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: `load_close_series()` reads stored `prices`, reindexes to a **continuous daily** date range, and forward-fills `close`, so rolling-window indicators receive a calendar-correct, gap-free series. Stored rows are never mutated — gap repair is a read-time concern.
- **Acceptance Criteria**:
  - Given stored prices with one or more missing calendar days, When `load_close_series()` is called, Then the returned series has a continuous daily index with the gaps forward-filled. *(test_db)*
  - Given the raw `prices` table, When the series is loaded, Then the stored rows are not altered (the table still reflects exactly what CoinGecko returned).
  - Given a coin with no stored prices, When `load_close_series()` is called, Then it returns `None` (callers then `SystemExit` with "Run: domdhi-crypto ingest" or skip the coin).

### Module 4: Technical Analysis — hand-rolled indicators (`ta.py`)

#### FR-11: Hand-rolled, auditable indicators (no `pandas-ta`)
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: RSI (Wilder, EWM), MACD (12/26/9), Bollinger Bands (20, 2σ) + %B, ATR (14), SMAs, and annualized volatility (×√365) are implemented in pure pandas/numpy. Each takes a Series (or OHLC DataFrame for ATR) and returns a Series; partial windows surface as **NaN**, never as fabricated numbers.
- **Acceptance Criteria**:
  - Given a known close series, When `rsi()` is computed, Then it matches an independently-coded Wilder's-RSI reference within tolerance. *(test_ta)*
  - Given a known series, When `macd()`/`bollinger()` are computed, Then the line/signal/histogram and mid/upper/lower/%B match textbook references within tolerance. *(test_ta)*
  - Given a series shorter than an indicator's window, When that indicator is computed, Then the under-window positions are `NaN` (no fabricated values). *(test_ta)*
  - Given the project's dependency set, When `ta.py` is imported, Then it imports only `numpy`/`pandas` and nothing from the project (leaf module) — and `pandas-ta` is absent.

#### FR-12: Signal generation rules
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: `analyze()` assembles the latest indicator values and `_signals()` turns them into plain-language calls: RSI ≥70 overbought / ≤30 oversold / else neutral; MACD histogram sign (bullish > 0 / bearish < 0); price-vs-SMA200 bull/bear regime; SMA50-vs-SMA200 golden/death cross; %B > 1 / < 0 Bollinger stretch.
- **Acceptance Criteria**:
  - Given a series whose SMA50 crosses above SMA200, When `analyze()` runs, Then a "golden cross (50D > 200D)" signal is emitted; below → "death cross". *(test_ta)*
  - Given the latest price above its SMA200, When `analyze()` runs, Then an "above 200D SMA (bull regime)" signal is emitted; below → "bear regime". *(test_ta)*
  - Given fewer than 200 days of data, When `analyze()` runs, Then `sma200` is `None` and the SMA200-dependent signals (regime, cross) are omitted rather than computed on partial data. *(test_ta)*
  - Given an RSI of 75 / 25 / 50, When signals are built, Then the emitted text is "overbought" / "oversold" / "neutral" respectively.

### Module 5: Dashboard — offline HTML/SVG renderer (`dashboard.py`)

#### FR-13: Single-file, self-contained offline HTML dashboard
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: `dashboard` builds one `dashboard.html` containing summary cards (portfolio value, unrealized P/L, cost basis, position count), allocation bars, a holdings table (P/L + a 90-day sparkline + a signal pill), and per-coin ~180-day price charts (price + SMA20/50/200) with an RSI(14) strip. Charts are inline SVG; styling is an inline `<style>` block (dark theme). No JS framework, no CDN, no server.
- **Acceptance Criteria**:
  - Given a populated `crypto.db` and `coins.local.json`, When `dashboard` runs, Then a single `dashboard.html` file is written and its path returned.
  - Given the generated `dashboard.html`, When it is opened from disk with **no network connection**, Then all cards, allocation bars, the holdings table, and every chart render fully (all data is baked in at generation time).
  - Given the file's contents, When inspected, Then it contains no `<script src=…>` CDN reference and no external stylesheet link — it is fully self-contained.
  - Given `--open`, When `dashboard --open` runs, Then the file is built and launched in the default browser via `webbrowser`.

#### FR-14: Terminal reports
- **Priority**: Should Have
- **Persona**: Self-custody technical holder
- **Description**: `ta <symbol>` prints a full indicator + signal readout for one coin, and `report` prints live portfolio value, unrealized P/L, and per-coin signals — both directly to the terminal for a quick, no-browser check.
- **Acceptance Criteria**:
  - Given a populated DB, When `domdhi-crypto ta BTC` runs, Then a fixed-width indicator/signal table for that coin is printed and the process exits `0`.
  - Given a populated DB and holdings, When `domdhi-crypto report` runs, Then total value, P/L, and per-coin signals are printed.
  - Given an empty/unpopulated DB, When `ta`/`report` run, Then the command exits with a `SystemExit` telling the user to run `domdhi-crypto ingest` (no traceback).

### Module 6: Config & Paths (`paths.py`)

#### FR-15: Relocatable data directory
- **Priority**: Should Have
- **Persona**: Self-custody technical holder
- **Description**: `paths.py` is the single place that resolves the data directory — `$DOMDHI_CRYPTO_HOME` if set, otherwise the current working directory — and exposes the fixed filenames (`config.local.json`, `coins.local.json`, `crypto.db`, `dashboard.html`, plus `*.example.json`). No other module hard-codes a path.
- **Acceptance Criteria**:
  - Given `$DOMDHI_CRYPTO_HOME` is set to a folder, When any command resolves a runtime file, Then it is read/written under that folder (e.g. an Obsidian vault).
  - Given `$DOMDHI_CRYPTO_HOME` is unset, When any command resolves a runtime file, Then it falls back to the current working directory.
  - Given the codebase, When searched, Then file locations are obtained only via `paths.*` (no module hard-codes a runtime filename or directory).

#### FR-16: Config-file loading with copy-the-example errors
- **Priority**: Must Have
- **Persona**: Self-custody technical holder
- **Description**: Holdings/config live in `coins.local.json` and `config.local.json`, read fresh on each command. A missing file fails fast with a `SystemExit` that tells the user exactly which example to copy.
- **Acceptance Criteria**:
  - Given no `coins.local.json`, When `dashboard`/`report`/`ingest` need holdings, Then `SystemExit` is raised telling the user to copy `coins.example.json → coins.local.json`.
  - Given valid `coins.local.json`/`config.local.json`, When a command runs, Then the current file contents are used (edits between runs take effect on the next command, no caching).

---

## Non-Functional Requirements

### Privacy / Data Locality

| ID | Requirement | Target (measurable) | Priority |
|----|-------------|---------------------|----------|
| NFR-PR1 | Secrets and holdings never leave the machine or enter version control | `git ls-files` returns **zero** matches for `crypto.db`, `coins.local.json`, `config.local.json`, `dashboard.html`; only `*.example.json` templates are tracked | Must Have |
| NFR-PR2 | The repo ships no real secret or holdings data | No committed file contains a real API key or holdings; placeholders contain `"PASTE…"` | Must Have |
| NFR-PR3 | No outbound network calls except CoinGecko on `ingest` | `ta`, `report`, `dashboard`, `init` make **zero** network calls (verifiable: they run fully offline) | Must Have |

### Security

| ID | Requirement | Standard / Target | Priority |
|----|-------------|-------------------|----------|
| NFR-S1 | Only authentication is a single CoinGecko API key in a git-ignored file | Key read solely from `config.local.json`; never logged to stdout | Must Have |
| NFR-S2 | Access control is OS file permissions only | No app-level auth/roles exist; whoever can run the binary is the user | Must Have |
| NFR-S3 | No inbound network surface | The tool opens **no** listening port/socket; outbound HTTPS to CoinGecko only | Must Have |

### Reliability

| ID | Requirement | Target (measurable) | Priority |
|----|-------------|---------------------|----------|
| NFR-R1 | Ingestion is idempotent | Re-running `ingest` over an overlapping range adds **0** duplicate `prices`/`ohlc` rows | Must Have |
| NFR-R2 | Transient CoinGecko 429s are retried before failure | Up to **4** attempts with `5·2^attempt`s backoff per request | Must Have |
| NFR-R3 | Ingest degrades gracefully on per-coin failure | A single coin's failure aborts **0** other coins; earlier per-coin commits survive | Must Have |
| NFR-R4 | Analysis tolerates sparse history | `load_close_series` yields a gap-free daily index for any input with missing days | Must Have |

### Portability

| ID | Requirement | Target (measurable) | Priority |
|----|-------------|---------------------|----------|
| NFR-PO1 | Runs on supported Python runtimes | Python **≥3.11**; CI matrix green on **3.11 / 3.12 / 3.13** | Must Have |
| NFR-PO2 | Runtime dependency surface is minimal | Runtime deps limited to **`requests`, `pandas`, `numpy`** (no `pandas-ta`, no web framework, no ORM) | Must Have |
| NFR-PO3 | Dashboard is a portable artifact | `dashboard.html` opens in any modern browser (or Obsidian) from disk with **0** external assets | Must Have |

### Performance

| ID | Requirement | Target (measurable) | Priority |
|----|-------------|---------------------|----------|
| NFR-PF1 | Dashboard generation + offline open is fast on a single-user dataset | **Sub-second** local compute to build `dashboard.html` for a handful of coins × ~365 daily rows *(inferred target — no stated SLA; the only real bound is CoinGecko's rate limit, not local compute)* | Should Have |
| NFR-PF2 | Ingest respects upstream rate limits over raw speed | Fixed **2.0s** inter-call pause; ingest time scales linearly with coin count (acceptable for a personal portfolio) | Should Have |

### Quality Bar

| ID | Requirement | Target (measurable) | Priority |
|----|-------------|---------------------|----------|
| NFR-Q1 | Lint is clean | `ruff check .` reports **0** violations (config: line-length 110, target py311, rules `E/F/W/I/UP/B`) | Must Have |
| NFR-Q2 | Test suite is green | **27** unit tests pass via `pytest` with the network mocked (12 `ta`, 9 `db`, 6 `coingecko`) | Must Have |
| NFR-Q3 | Indicator correctness is pinned to references | Every TA indicator has a test cross-checking it against an independent textbook reference within tolerance | Must Have |
| NFR-Q4 | **No static type-checking is part of the gate** | mypy is **not** a dependency and there is **no** `[tool.mypy]` config — the gate is **ruff + pytest only** (accepted boundary per ADR-006; tests, not the type system, are the safety net) | Won't Have (this release) |

### Data Granularity

| ID | Requirement | Target (measurable) | Priority |
|----|-------------|---------------------|----------|
| NFR-D1 | Core indicators run on daily granularity | RSI/MACD/SMA/Bollinger computed from `/market_chart` daily points; bounded by CoinGecko Demo tier (≈30 calls/min, history capped at **365 days**) | Must Have |
| NFR-D2 | Finer OHLC/ATR is opt-in | `ingest --days 30` yields daily-granularity OHLC candles for ATR; a 365-day pull yields **4-day** candles (a known CoinGecko granularity limit) | Could Have |

### Maintainability

| ID | Requirement | Target (measurable) | Priority |
|----|-------------|---------------------|----------|
| NFR-M1 | Imports stay strictly acyclic | `paths`/`ta` remain leaves, `cli` the apex; **0** import cycles | Must Have |
| NFR-M2 | Single-author maintainable | Modules stay small (~40–320 lines); no team-scale operational complexity introduced | Should Have |

---

## User Flows

### Flow 1: First-run setup (happy path + errors)
1. User clones the repo and runs `pip install -e .` (or `uv pip install -e .`).
2. User copies `config.example.json → config.local.json` and pastes their CoinGecko API key (and sets `tier` if pro).
3. User copies `coins.example.json → coins.local.json` and fills in real holdings (`id`, `symbol`, `amount`, `avg_entry`, optional `"stable": true`).
4. User runs `domdhi-crypto init` → `crypto.db` and its schema are created.
   - If `config.local.json` is missing or the key still contains `"PASTE"`: the CLI exits with a copy-the-example / set-your-key message (FR-7).
   - If `coins.local.json` is missing when a command needs holdings: exit with a copy-the-example message (FR-16).

### Flow 2: Daily ritual (happy path + degradation)
1. User runs `domdhi-crypto ingest` — for each non-stable coin, fetch the live snapshot + ~365 days of history, upsert idempotently into `crypto.db`.
   - If a 429 is returned: back off (`5·2^attempt`s) and retry up to 4 times (FR-6).
   - If one coin's fetch fails outright: print `! …failed` for that coin and continue with the rest (FR-3).
2. User runs `domdhi-crypto dashboard --open` — build `dashboard.html` from the local DB and launch it in the browser.
   - If the DB has no data yet: exit with "Run: domdhi-crypto ingest" (FR-14/FR-10).
   - Coins with no data are skipped, so a partially-populated DB still renders a useful dashboard.
3. User reads portfolio value, P/L, allocation, and per-coin signals — fully offline.

### Flow 3: Ad-hoc analysis
1. User runs `domdhi-crypto ta BTC` (id or symbol) → a full indicator + signal readout prints to the terminal (FR-2, FR-14).
2. User runs `domdhi-crypto report` → live portfolio value, P/L, and per-coin signals print to the terminal.
   - If the requested coin is unknown: exit with a `SystemExit` naming it (FR-2).
   - If fewer than 200 days of history exist: SMA200-dependent signals are omitted rather than computed on partial data (FR-12).

### Flow 4: Relocating the data directory
1. User sets `$DOMDHI_CRYPTO_HOME=/path/to/vault` (e.g. an Obsidian vault).
2. User runs any subcommand → all runtime files (`config.local.json`, `coins.local.json`, `crypto.db`, `dashboard.html`) are read/written under that folder (FR-15).
   - If `$DOMDHI_CRYPTO_HOME` is unset: the current working directory is used.

---

## Data Model (Conceptual)

The DB holds only **market data**; the user's **position** (amounts, cost basis, stablecoin flags) lives in `coins.local.json`, not the database. `coins.id` is the CoinGecko coin id and the join key across all tables; SQLite foreign keys are not declared — referential integrity is maintained by the ingest code.

### Entities
| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Coin | A tracked CoinGecko asset | `id` (PK, CoinGecko id), `symbol`, `name` |
| Price | A daily market data point for a coin | `(coin_id, date)` (PK), `close`, `volume`, `market_cap` |
| OHLC candle | A candle for a coin | `(coin_id, ts)` (PK, epoch-ms open), `open`, `high`, `low`, `close` |
| Snapshot | A point-in-time live quote (append-only) | `(coin_id, fetched_at)` (PK), live price, 24h/7d/30d % change |
| Holding *(config, not DB)* | The user's position in a coin | `id`, `symbol`, `amount`, `avg_entry`, optional `stable` |

### Relationships
- A Coin has many Prices, many OHLC candles, and many Snapshots (each keyed by `coin_id`).
- A Holding (in `coins.local.json`) corresponds to at most one Coin (by `id`); portfolio value/P/L join Holdings to the latest Snapshot price.
- Snapshots are append-only: each `ingest` adds one row per coin, building a history of check-ins (latest is read for live price/P/L).

---

## API Surface

**The project exposes no API of its own** — no HTTP server, no RPC, no public library surface beyond the console entry point. The relevant surfaces are the CoinGecko REST API it *consumes* and the CLI it *presents*.

### Consumed external API — CoinGecko v3
| Group | Purpose | Key Operations |
|-------|---------|----------------|
| `/coins/markets` | Live price, market cap, 24h/7d/30d change | one call covers all coins (`ids` joined) |
| `/coins/{id}/market_chart` | Historical daily price/volume/market-cap series | `days ≥ 90` yields daily points |
| `/coins/{id}/ohlc` | OHLC candles | granularity varies by `days`; `days` capped at 365 on ingest |

### Presented CLI surface
| Group | Purpose | Key Operations |
|-------|---------|----------------|
| `init` | Create the DB + schema | no network |
| `ingest [--days]` | Fetch + upsert snapshot and history | network; idempotent |
| `ta <symbol>` / `report` | Print indicators / portfolio readout | reads DB; no network |
| `dashboard [--open]` | Build (and optionally open) `dashboard.html` | reads DB; no network |

---

## Security Requirements

- **Authentication**: To CoinGecko — a single API key sent as an HTTP header, read only from git-ignored `config.local.json`; `tier` selects the demo/pro header name. To the tool itself — **none** (local single-user CLI; no login, session, or token).
- **Authorization**: Not applicable. No roles, no multi-tenancy, no per-resource permissions. OS file permissions on the data directory are the entire access-control model.
- **Data Protection**: The API key, holdings, cost basis, price database, and rendered dashboard all stay on the user's machine and are git-ignored (project `.gitignore` block plus defense-in-depth `*.local.*` pattern). No telemetry; no third-party data egress. The key is never printed to stdout.
- **Audit**: None — diagnostics are human-readable `print()` to stdout (progress lines, row counts, rate-limit notices, per-coin warnings). There is no log file, structured logging, metrics, or tracing, and none is warranted for this single-user model.
- **Compliance**: None binding. The product is explicitly **not financial advice** — signals are mechanical math readouts; the README disclaimer makes this stance load-bearing.

---

## Assumptions & Dependencies

### Assumptions
- A single technically-comfortable user runs the tool on their own machine; there is exactly one writer and no concurrency.
- `crypto.db` is a **regenerable cache**, not a system of record — "delete and re-ingest" is an acceptable recovery and migration story (no migration framework exists by design).
- The free CoinGecko Demo tier (≈30 calls/min, 365-day history cap) is sufficient for a personal portfolio; the 2.0s pace and 429 backoff keep within it.
- The user keeps their holdings current in `coins.local.json`; the tool reflects whatever is there at command time. *(inferred)*
- Daily granularity is acceptable for the user's analysis; intraday/real-time is out of scope.

### Dependencies
- **CoinGecko v3 REST API** — the single, hard external dependency. Endpoint, field-name, or granularity changes would break ingest (contained to `coingecko.py`).
- **Python ≥3.11** runtime; runtime libraries `requests` / `pandas` / `numpy`; stdlib `sqlite3`.
- **Dev/CI tooling** — hatchling (build), ruff (lint), pytest (tests), pre-commit (hooks), GitHub Actions (3.11/3.12/3.13 matrix).

---

## Success Criteria

| Criteria | Target | Measurement |
|----------|--------|-------------|
| Daily ritual completes end-to-end | `ingest` → `dashboard --open` runs without error on a populated config | Exit code `0` and a rendered `dashboard.html` |
| Indicator correctness | Hand-rolled indicators match textbook references | The 27 unit tests pass (`test_ta` cross-checks the math; `test_db`/`test_coingecko` cover storage + client) |
| Zero data leakage | No secrets, keys, or holdings ever committed | `git ls-files` returns 0 matches for `crypto.db`, `coins.local.json`, `config.local.json`, `dashboard.html` |
| Offline operability | Dashboard fully functional with no network | Open `dashboard.html` from disk while offline; every card/chart renders *(inferred verification method)* |
| Re-ingest safety | Re-running `ingest` never duplicates rows | Row counts stable across repeated overlapping ingests (`test_db`) |
| CI stays green across runtimes | Lint + tests pass on Python 3.11 / 3.12 / 3.13 | GitHub Actions matrix: `ruff check` + `pytest` on every push/PR |

---

## Glossary

| Term | Definition |
|------|-----------|
| Local-first | All data and computation live on the user's machine; the network is touched only on `ingest`. |
| Idempotent upsert | A write that, repeated with the same key, leaves the store in the same state (no duplicates). |
| Gap-fill / forward-fill | Reindexing a price series to a continuous daily range and carrying the last known close forward over missing days (read-time only). |
| RSI (Wilder) | Relative Strength Index using Wilder's EWM smoothing; ≥70 overbought, ≤30 oversold. |
| MACD | Moving Average Convergence Divergence (12/26/9); histogram sign drives the bullish/bearish signal. |
| Golden / death cross | SMA50 crossing above (golden) or below (death) SMA200 — a regime-shift signal. |
| %B (Bollinger) | Position of price within its Bollinger band; >1 stretched above the upper band, <0 below the lower. |
| Tier (demo/pro) | CoinGecko plan selector controlling the API host and auth-header name. |
| Data directory | `$DOMDHI_CRYPTO_HOME` or the current working directory — the single home for all runtime files. |
| Snapshot | An append-only point-in-time live quote row; the latest is read for live price and P/L. |

---

## Related Documents
- Project Brief: [_project-brief.md](_project-brief.md)
- Architecture (tech stack, 6 ADRs, data pipeline): [_project-architecture.md](_project-architecture.md)
- Project Context (quick-reference): [_project-context.md](_project-context.md)
- Product README (stated vision): [../README.md](../README.md)
- Contributing (design constraints): [../CONTRIBUTING.md](../CONTRIBUTING.md)
- UX Spec: [design/_project-design.md](design/_project-design.md) *(not yet present)*
- Epics / backlog: [todo/_backlog.md](todo/_backlog.md)
