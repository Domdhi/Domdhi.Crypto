# Product Backlog: Domdhi.Crypto

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Version** | 1.0 |
| **Status** | Brownfield — Phases 0–4 shipped (Epic 11 complete, 4/4); backlog exhausted |
| **Author** | project-planner |
| **Tech Stack** | Python ≥3.11 (src-layout CLI) · requests / pandas / numpy · SQLite (stdlib) · hatchling · ruff · pytest |

---

## Executive Summary

Domdhi.Crypto is a self-hosted, local-first crypto portfolio and technical-analysis engine. It is a **brownfield** project: the code already exists at commit `ad85772`, works end-to-end, and is covered by **38 passing unit tests**. This backlog therefore documents reality, not fiction.

Phases 0–3 capture the **already-shipped** capability surface mapped back to the PRD's 16 functional requirements. Every story in those phases is marked **`Status: ✅ shipped`** — they are recorded for traceability (so every FR has a home and a verifiable contract), not for re-implementation. A `/do` wave that picks one up should treat it as a verification/no-op unless a regression is found.

Phase 4 (Epic 11, Test & Release Hardening) was the last genuinely open work and is now **complete (4/4, shipped)**: a tight set of small, real, incremental stories grounded in gaps found during validation — `paths.py` had no dedicated test (E11-S1), `cli.py` had no `--version` path or helper test (E11-S2/S3), and CI installed dev tools ad-hoc rather than from the declared `dev` group (E11-S4). All shipped in commits `d918d57` / `2fb9fe4` / `ecdb48d`. Post-MVP work now arrives via the `/listen` → `/triage` lifecycle (see the **Triage Intake** section below).

**Phase = capability milestone, not a time box.** Each phase ends with the system able to do something it could not before. Within a phase, no two stories own the same file — the wave executor dispatches them in parallel, so file-ownership overlap is treated as a planning bug. Where a Phase 4 story must touch a file that a shipped story "owns," the overlap is called out explicitly and the shipped story is inert (it will not be re-run), so there is no live conflict.

**ID scheme:** `E{epic}-S{story}` (e.g. `E1-S2`). Epic numbers are globally unique across the whole backlog; story numbers restart per epic.

---

## Technology Stack

| Layer | Choice |
|-------|--------|
| Language / runtime | Python `>=3.11`, tested on CPython 3.11 / 3.12 / 3.13 |
| Runtime deps | `requests>=2.31`, `pandas>=2.0`, `numpy>=1.24` (no `pandas-ta`, no web framework, no ORM) |
| Storage | SQLite (stdlib `sqlite3`), single `crypto.db` file |
| Presentation | Terminal `print` tables + single-file offline HTML with inline SVG |
| Build / packaging | hatchling, PEP 621 `pyproject.toml`, src-layout, console script `domdhi-crypto` |
| Lint / test | ruff (`E/F/W/I/UP/B`, line 110, py311) + pytest (27 tests, network mocked) |
| CI | GitHub Actions matrix 3.11/3.12/3.13 → `ruff check` + `pytest` (no mypy, no format-check) |

---

## Phase 0: Foundation & Configuration

**Goal:** Packaging, the path/config resolver, and idempotent SQLite schema init — the center of the board that every other module depends on.

**Status:** ✅ shipped (recorded for traceability).

---

### Epic 0: Packaging & Project Bootstrap

**Objective:** A pip-installable src-layout package exposing the `domdhi-crypto` console script, with the ruff + pytest quality gate and the 3.11/3.12/3.13 CI matrix.

* **Story E0-S1 (Config): src-layout package + console entry point**
  * **As a** self-custody technical holder,
  * **I want** to `pip install -e .` and get a `domdhi-crypto` command (and `python -m domdhi_crypto`),
  * **So that** I can run the whole tool from one entry point on my own machine.
  * **AC:**
    * Given the repo, When `pip install -e .` runs, Then a `domdhi-crypto` console script is installed and resolves to `domdhi_crypto.cli:main`.
    * Given the installed package, When `python -m domdhi_crypto <cmd>` runs, Then it behaves identically to the console script (`__main__.py` → `cli.main`).
    * Given `pyproject.toml`, When inspected, Then it declares PEP 621 metadata, hatchling build backend, the `src/domdhi_crypto` wheel target, and runtime deps limited to `requests`/`pandas`/`numpy`. *(FR-1, NFR-PO2)*
  * **Files:** `pyproject.toml`, `src/domdhi_crypto/__init__.py`, `src/domdhi_crypto/__main__.py`
  * **Estimate:** S · **Status:** ✅ shipped · **Dependencies:** None

* **Story E0-S2 (DevOps): CI matrix + ruff/pytest quality gate**
  * **As a** maintainer,
  * **I want** lint + tests to run on every push/PR across Python 3.11/3.12/3.13,
  * **So that** the no-`pandas-ta` portability promise stays provably green.
  * **AC:**
    * Given a push to `master` or a PR, When CI runs, Then a matrix over Python 3.11/3.12/3.13 installs the package and runs `ruff check .` then `pytest`. *(NFR-PO1, NFR-Q1, NFR-Q2)*
    * Given `ruff.toml`, When inspected, Then it pins line-length 110, target py311, rules `E/F/W/I/UP/B`.
    * Given the CI config, When inspected, Then there is no mypy step and no `ruff format --check` step (gate is ruff + pytest only). *(NFR-Q4, ADR-006)*
  * **Files:** `.github/workflows/ci.yml`, `ruff.toml`, `.pre-commit-config.yaml`
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E0-S1

---

### Epic 1: Paths & Config Resolution

**Objective:** A single leaf module that resolves the data directory and fixed filenames, plus fail-fast config loading with copy-the-example errors.

* **Story E1-S1 (Config): Relocatable data-directory resolver**
  * **As a** self-custody technical holder,
  * **I want** all runtime files resolved from `$DOMDHI_CRYPTO_HOME` (or the CWD),
  * **So that** I can point the tool at an Obsidian vault or any folder I choose.
  * **AC:**
    * Given `$DOMDHI_CRYPTO_HOME` is set, When any path helper resolves a file, Then it is under that folder. *(FR-15)*
    * Given `$DOMDHI_CRYPTO_HOME` is unset, When a path helper resolves a file, Then it falls back to `Path.cwd()`.
    * Given the codebase, When searched, Then file locations come only from `paths.*` constants/helpers — no other module hard-codes a runtime filename. *(NFR-M1)*
  * **Files:** `src/domdhi_crypto/paths.py`
  * **Estimate:** S · **Status:** ✅ shipped · **Dependencies:** None
  * **Note:** Phase 4 story **E11-S1** adds the missing dedicated test for this file (read-only over `paths.py` itself; it owns a *new* test file, no source overlap).

* **Story E1-S2 (Config): Fail-fast config/holdings loading with copy-the-example errors**
  * **As a** self-custody technical holder,
  * **I want** missing/placeholder config to fail with an exact fix-it message,
  * **So that** first-run setup mistakes are obvious instead of producing a traceback.
  * **AC:**
    * Given no `coins.local.json`, When a command needs holdings, Then `SystemExit` names `coins.example.json → coins.local.json` as the fix. *(FR-16)*
    * Given no `config.local.json`, an empty `api_key`, or a key containing `"PASTE"`, When credentials load, Then `SystemExit` tells the user to copy the example / set the key. *(FR-7)*
    * Given valid files, When a command runs, Then current file contents are read fresh each run (no caching). *(FR-16)*
  * **Files:** `src/domdhi_crypto/coingecko.py` (`load_config`), `config.example.json`, `coins.example.json`
  * **Estimate:** S · **Status:** ✅ shipped · **Dependencies:** E1-S1
  * **Note:** `load_coins` (the `coins.local.json` side of FR-16) lives in `cli.py` and is exercised under Epic 2; `coingecko.py` here owns only the `config.local.json` credential side.

---

### Epic 2: SQLite Schema & Idempotent Storage

**Objective:** The four-table schema created idempotently, idempotent upsert ingestion, and the gap-filled daily close series the indicators depend on.

* **Story E2-S1 (Database): Idempotent four-table schema init**
  * **As a** self-custody technical holder,
  * **I want** `domdhi-crypto init` to create the schema safely whether the DB is fresh or already exists,
  * **So that** I can re-run setup without fear of dropping data.
  * **AC:**
    * Given no DB file, When `init` runs, Then `crypto.db` is created with `coins`, `prices`, `ohlc`, `snapshots`. *(FR-8, test_db)*
    * Given an existing schema, When `init_db()` runs again, Then it succeeds without dropping/altering data (`CREATE TABLE IF NOT EXISTS`).
    * Given a test, When `connect()`/`init_db()` are called with an explicit path, Then they operate against that path (`:memory:`/temp).
  * **Files:** `src/domdhi_crypto/db.py` (schema + `connect`/`init_db`)
  * **Estimate:** S · **Status:** ✅ shipped · **Dependencies:** E1-S1

* **Story E2-S2 (Database): Idempotent upsert ingestion**
  * **As a** self-custody technical holder,
  * **I want** every write to be idempotent,
  * **So that** re-ingesting overlapping date ranges never duplicates or corrupts rows.
  * **AC:**
    * Given an existing `(coin_id, date)` price row, When the same key is upserted, Then the row count is unchanged and values are updated. *(FR-9, NFR-R1, test_db)*
    * Given `ingest` run twice over an overlapping range, When the second completes, Then no duplicate `prices`/`ohlc` rows exist.
    * Given an existing `(coin_id, fetched_at)` snapshot, When re-inserted, Then it is a no-op (`ON CONFLICT DO NOTHING`). *(ADR-005)*
  * **Files:** `src/domdhi_crypto/db.py` (`upsert_coin`/`upsert_prices`/`upsert_ohlc`/`insert_snapshot`)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E2-S1
  * **Note:** Same physical file as E2-S1/E2-S3 but distinct, non-overlapping function surfaces; safe because all three are shipped/inert, not live wave work.

* **Story E2-S3 (Database): Gap-filled daily close series**
  * **As a** self-custody technical holder,
  * **I want** the analysis series reindexed to a continuous daily range and forward-filled,
  * **So that** rolling-window indicators receive a calendar-correct, gap-free series.
  * **AC:**
    * Given stored prices with missing calendar days, When `load_close_series()` is called, Then the returned series has a continuous daily index with gaps forward-filled. *(FR-10, NFR-R4, test_db)*
    * Given the raw `prices` table, When the series is loaded, Then stored rows are not mutated (gap repair is read-time only).
    * Given a coin with no stored prices, When `load_close_series()` is called, Then it returns `None`.
  * **Files:** `src/domdhi_crypto/db.py` (`load_close_series`/`load_ohlc`/`latest_snapshot_price`)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E2-S1

---

## Phase 1: Data & Core Ingestion

**Goal:** Pull live snapshots and daily history from CoinGecko (demo/pro tiers) with polite pacing, 429 backoff, fail-fast credentials, and per-coin failure isolation.

**Status:** ✅ shipped.

---

### Epic 3: CoinGecko Client

**Objective:** The system's only outbound trust boundary — tiered host/header wiring, rate-limit backoff, and fail-fast credential loading.

* **Story E3-S1 (Backend): Tiered demo/pro client wiring**
  * **As a** self-custody technical holder,
  * **I want** the client to wire the correct host + auth header from my `tier`,
  * **So that** both free-demo and pro keys work without code changes.
  * **AC:**
    * Given `tier: "demo"`, When a `CoinGecko` client is constructed, Then `base` is the demo host and the session carries `x-cg-demo-api-key`. *(FR-5, test_coingecko)*
    * Given `tier: "pro"`, When constructed, Then `base` is the pro host with `x-cg-pro-api-key`.
    * Given `tier` absent, When constructed, Then it defaults to demo wiring; `requests` is imported lazily inside `__init__`. *(NFR-PR3)*
  * **Files:** `src/domdhi_crypto/coingecko.py` (`CoinGecko.__init__`, `markets`/`market_chart`/`ohlc`)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E1-S2

* **Story E3-S2 (Backend): Rate-limit backoff and polite pacing**
  * **As a** self-custody technical holder,
  * **I want** transient 429s retried with backoff and a fixed inter-call pause,
  * **So that** ingest stays within the free-tier rate limit and survives blips.
  * **AC:**
    * Given the API returns 429 then 200, When `_get` is called, Then it sleeps, retries, and returns the 200 payload. *(FR-6, NFR-R2, test_coingecko)*
    * Given 429 on every attempt, When `_get` exhausts 4 retries, Then it raises (no silent `None`).
    * Given a 2xx response, When `_get` returns, Then a `pause`-length sleep has occurred (verifiable with a mocked clock). *(NFR-PF2)*
  * **Files:** `src/domdhi_crypto/coingecko.py` (`_get`)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E3-S1
  * **Note:** Shares `coingecko.py` with E3-S1/E1-S2 but owns the `_get` retry surface only; all three are inert/shipped.

---

### Epic 4: Ingest Orchestration

**Objective:** The `ingest` command that drives the client → DB pipeline with per-coin failure isolation, stablecoin skipping, and id/symbol resolution.

* **Story E4-S1 (Backend): Subcommand-driven CLI workflow**
  * **As a** self-custody technical holder,
  * **I want** five argparse subcommands (`init`, `ingest`, `ta`, `report`, `dashboard`),
  * **So that** the whole ritual is driven from one command.
  * **AC:**
    * Given the package is installed, When `domdhi-crypto <subcommand>` runs, Then the matching `cmd_*` handler executes and exits `0` on success. *(FR-1)*
    * Given no/unknown subcommand, When the CLI parses args, Then argparse prints usage/help rather than a traceback (`required=True` on the subparser).
    * Given `ingest`, When invoked, Then it accepts `--days` (default 365); `ta` requires a `<symbol>`; `dashboard` accepts `--open`.
  * **Files:** `src/domdhi_crypto/cli.py` (`main`, argparse wiring)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E0-S1
  * **Note:** `cli.py` is also touched by Phase 4 stories **E11-S2** (`--version`) and **E11-S3** (helper test). Those add new, non-overlapping surface; this shipped story is inert. See per-story overlap notes.

* **Story E4-S2 (Backend): Coin resolution by id or symbol**
  * **As a** self-custody technical holder,
  * **I want** to target a coin by CoinGecko id or ticker, case-insensitively,
  * **So that** `ta BTC` and `ta bitcoin` select the same coin.
  * **AC:**
    * Given `coins.local.json` lists `{"id":"bitcoin","symbol":"BTC"}`, When `ta BTC` or `ta bitcoin` runs, Then the same coin is selected. *(FR-2)*
    * Given an unknown symbol/id, When `ta` runs against it, Then `SystemExit` names the unknown coin (no empty output).
    * Given `coins.local.json` is missing, When `load_coins` runs, Then `SystemExit` names `coins.example.json → coins.local.json`. *(FR-16, coins side)*
  * **Files:** `src/domdhi_crypto/cli.py` (`_resolve`, `load_coins`)
  * **Estimate:** S · **Status:** ✅ shipped · **Dependencies:** E4-S1

* **Story E4-S3 (Backend): Per-coin failure isolation + stablecoin skip during ingest**
  * **As a** self-custody technical holder,
  * **I want** one coin's fetch failure to not abort the rest, and stablecoins skipped for history,
  * **So that** a single bad coin doesn't lose the whole run and pegged assets don't show meaningless signals.
  * **AC:**
    * Given a multi-coin run where one coin's history fetch raises, When `ingest` runs, Then a `! …failed` warning prints and other coins still ingest and commit. *(FR-3, NFR-R3)*
    * Given an earlier coin committed before a later failure, When the run ends, Then the earlier coin's rows persist (per-coin commit).
    * Given a coin with `"stable": true`, When `ingest` runs, Then no `market_chart`/`ohlc` history is fetched for it, but its `amount × price` still counts toward portfolio value in `report`/`dashboard`. *(FR-4)*
  * **Files:** `src/domdhi_crypto/cli.py` (`cmd_ingest`, `_daily_rows`)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E4-S1, E3-S1, E2-S2

---

## Phase 2: Technical Analysis

**Goal:** Hand-rolled, auditable indicators and the signal rules that turn them into plain-language calls.

**Status:** ✅ shipped.

---

### Epic 5: Indicators & Signals

**Objective:** Pure pandas/numpy indicator math (NaN on partial windows) and the `analyze`/`_signals` layer.

* **Story E5-S1 (Backend): Hand-rolled auditable indicators**
  * **As a** self-custody technical holder,
  * **I want** RSI/MACD/Bollinger/ATR/SMA/volatility implemented in pure pandas/numpy,
  * **So that** the math is auditable and verifiable against textbook references, not a black box.
  * **AC:**
    * Given a known close series, When `rsi()` is computed, Then it matches an independent Wilder's-RSI reference within tolerance. *(FR-11, NFR-Q3, test_ta)*
    * Given a known series, When `macd()`/`bollinger()` are computed, Then line/signal/histogram and mid/upper/lower/%B match textbook references within tolerance.
    * Given a series shorter than an indicator's window, When computed, Then under-window positions are `NaN` (no fabricated values).
    * Given the import graph, When `ta.py` is imported, Then it imports only `numpy`/`pandas` and nothing internal; `pandas-ta` is absent. *(NFR-M1, NFR-PO2, ADR-001)*
  * **Files:** `src/domdhi_crypto/ta.py` (`rsi`/`macd`/`bollinger`/`atr`/`annualized_vol`/`_f`)
  * **Estimate:** L · **Status:** ✅ shipped · **Dependencies:** None

* **Story E5-S2 (Backend): Signal generation rules**
  * **As a** self-custody technical holder,
  * **I want** `analyze()`/`_signals()` to turn the latest indicators into plain-language calls,
  * **So that** I get RSI/MACD/regime/cross/Bollinger readouts per coin.
  * **AC:**
    * Given SMA50 crossing above SMA200, When `analyze()` runs, Then a "golden cross (50D > 200D)" signal is emitted; below → "death cross". *(FR-12, test_ta)*
    * Given price above SMA200, When `analyze()` runs, Then "above 200D SMA (bull regime)" is emitted; below → "bear regime".
    * Given fewer than 200 days, When `analyze()` runs, Then `sma200` is `None` and SMA200-dependent signals are omitted (not computed on partial data).
    * Given RSI of 75 / 25 / 50, When signals are built, Then text is "overbought" / "oversold" / "neutral" respectively.
  * **Files:** `src/domdhi_crypto/ta.py` (`analyze`, `_signals`)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E5-S1, E2-S3
  * **Note:** Shares `ta.py` with E5-S1 but owns the `analyze`/`_signals` surface only; both shipped/inert.

---

## Phase 3: Dashboard & Reporting

**Goal:** Render results two ways — a single self-contained offline HTML/SVG dashboard and terminal reports.

**Status:** ✅ shipped.

---

### Epic 6: Offline HTML Dashboard

**Objective:** One self-contained `dashboard.html` (cards, allocation, holdings table, per-coin charts + RSI strip) that works fully offline.

* **Story E6-S1 (Frontend): Single-file offline HTML/SVG dashboard**
  * **As a** self-custody technical holder,
  * **I want** one `dashboard.html` with all data baked in,
  * **So that** I can open it from disk with no network, server, CDN, or JS framework.
  * **AC:**
    * Given a populated `crypto.db` and `coins.local.json`, When `dashboard` runs, Then a single `dashboard.html` is written and its path returned. *(FR-13)*
    * Given the file, When opened from disk offline, Then all cards, allocation bars, holdings table, and every chart render (data baked in). *(NFR-PR3, NFR-PO3)*
    * Given the file's contents, When inspected, Then there is no `<script src=…>` CDN ref and no external stylesheet link (fully self-contained). *(ADR-004)*
    * Given `--open`, When `dashboard --open` runs, Then the file is built and launched via `webbrowser`.
    * Given missing `coins.local.json`, When `dashboard` runs, Then `SystemExit` names the copy-the-example fix.
  * **Files:** `src/domdhi_crypto/dashboard.py`
  * **Estimate:** L · **Status:** ✅ shipped · **Dependencies:** E2-S3, E5-S2, E1-S1

---

### Epic 7: Terminal Reports

**Objective:** `ta <symbol>` and `report` print indicator/portfolio readouts directly to the terminal.

* **Story E7-S1 (Backend): Per-coin TA terminal readout**
  * **As a** self-custody technical holder,
  * **I want** `ta <symbol>` to print a full indicator + signal table,
  * **So that** I get a quick no-browser check for one coin.
  * **AC:**
    * Given a populated DB, When `domdhi-crypto ta BTC` runs, Then a fixed-width indicator/signal table prints and the process exits `0`. *(FR-14)*
    * Given an empty/unpopulated DB, When `ta` runs, Then `SystemExit` tells the user to run `domdhi-crypto ingest` (no traceback). *(FR-10)*
    * Given fewer than 200 days, When `ta` runs, Then SMA200-dependent signals are omitted. *(FR-12)*
  * **Files:** `src/domdhi_crypto/cli.py` (`cmd_ta`, `fmt`)
  * **Estimate:** S · **Status:** ✅ shipped · **Dependencies:** E4-S2, E5-S2
  * **Note:** Same file as E4-S1/S2/S3 and `cmd_report`; owns `cmd_ta`/`fmt` only. Inert/shipped.

* **Story E7-S2 (Backend): Portfolio report terminal readout**
  * **As a** self-custody technical holder,
  * **I want** `report` to print live portfolio value, P/L, and per-coin signals,
  * **So that** I see the whole position at a glance without the browser.
  * **AC:**
    * Given a populated DB and holdings, When `report` runs, Then total value, P/L, and per-coin signals print. *(FR-14)*
    * Given a stablecoin holding, When `report` runs, Then its `amount × price` counts toward total value with a `stablecoin` signal tag. *(FR-4)*
    * Given an empty DB, When `report` runs, Then it degrades by printing `n/a` per coin rather than crashing.
  * **Files:** `src/domdhi_crypto/cli.py` (`cmd_report`)
  * **Estimate:** M · **Status:** ✅ shipped · **Dependencies:** E4-S2, E5-S2, E2-S3
  * **Note:** Owns `cmd_report` only within the shared `cli.py`. Inert/shipped.

---

## Phase 4: Polish & Gaps

**Goal:** Close the real, validated gaps. These are the **only genuinely open** stories — small, incremental, and each owning a distinct (mostly new) file so a `/do` wave can dispatch them in parallel with zero conflict.

**Status:** ⬜ todo — this is the build wave.

---

### Epic 11: Test & Release Hardening

**Objective:** Add the missing `paths.py` test, a `--version` path with a focused CLI helper test, and align CI's dev-tool install with the declared `dev` group. No runtime behavior of the shipped pipeline changes.

* **Story E11-S1 (Test): Add a dedicated `paths.py` unit test**
  * **As a** maintainer,
  * **I want** `paths.py` covered by its own test file,
  * **So that** the data-directory contract (`$DOMDHI_CRYPTO_HOME` vs CWD, fixed filenames) is pinned like the other core modules.
  * **AC:**
    * Given a new `tests/test_paths.py`, When `pytest` runs, Then it passes and exercises `paths` only (no network, no real filesystem writes outside `tmp_path`/monkeypatched env).
    * Given `monkeypatch.setenv("DOMDHI_CRYPTO_HOME", tmp)`, When `data_dir()` is called, Then it returns `Path(tmp)`; with the env unset, When called, Then it returns `Path.cwd()`. *(FR-15)*
    * Given each path helper, When called, Then `config_path`/`coins_path`/`db_path`/`dashboard_path` join the resolved dir with the correct fixed filename constant.
    * Given the suite, When run, Then total passing tests increase from 27 (new tests are additive, none removed).
  * **Files:** `tests/test_paths.py` *(new — no overlap with any existing file)*
  * **Estimate:** S · **Status:** ⬜ todo · **Dependencies:** E1-S1
  * **Overlap:** None. New file; reads `paths.py` as the unit under test but does not modify it.

* **Story E11-S2 (Backend): Add a `--version` / version-display path**
  * **As a** self-custody technical holder,
  * **I want** `domdhi-crypto --version` to print the installed package version,
  * **So that** I can confirm which build I'm running when reporting an issue.
  * **AC:**
    * Given the installed package, When `domdhi-crypto --version` runs, Then it prints the version from package metadata (e.g. `importlib.metadata.version("domdhi-crypto")`) and exits `0`.
    * Given the version source, When inspected, Then the displayed version equals `pyproject.toml`'s `[project].version` (single source of truth — not a hard-coded duplicate). *(FR-1)*
    * Given `--version` is added, When any existing subcommand runs, Then behavior is unchanged (argparse `required=True` subparser still applies to non-version invocations).
  * **Files:** `src/domdhi_crypto/cli.py` (`main`, add `--version` action via `argparse`)
  * **Estimate:** S · **Status:** ⬜ todo · **Dependencies:** E4-S1
  * **Overlap:** Touches `cli.py`, shared with shipped Epic 4/7 stories. Those are inert (no live wave work). **E11-S2 and E11-S3 both touch `cli.py` and therefore must NOT run in the same parallel wave** — sequence E11-S2 before E11-S3 (E11-S3 adds the test that covers E11-S2's helper). See dependency.

* **Story E11-S3 (Test): Focused helper test for `cli.py`**
  * **As a** maintainer,
  * **I want** a unit test for a pure `cli.py` helper (`_resolve` and/or the `--version` resolver),
  * **So that** the CLI's id/symbol resolution and version path are pinned without invoking the network.
  * **AC:**
    * Given a new `tests/test_cli.py`, When `pytest` runs, Then it passes with no network calls.
    * Given a coins list, When `_resolve(coins, "BTC")` and `_resolve(coins, "bitcoin")` are called, Then both return the same coin; `_resolve(coins, "nope")` returns `None`. *(FR-2)*
    * Given the version resolver added in E11-S2, When tested, Then it returns the same string as `importlib.metadata.version("domdhi-crypto")`. *(FR-1)*
  * **Files:** `tests/test_cli.py` *(new file)*
  * **Estimate:** S · **Status:** ⬜ todo · **Dependencies:** E11-S2, E4-S2
  * **Overlap:** New test file — no source overlap. Depends on E11-S2 because it tests the version resolver E11-S2 introduces; run after E11-S2.

* **Story E11-S4 (DevOps): Align CI dev-tool install with the declared `dev` group**
  * **As a** maintainer,
  * **I want** CI to install dev tools from the PEP 735 `dev` group instead of an ad-hoc `pip install pytest ruff`,
  * **So that** the build bar matches the project's single declared dependency source (no version drift between CI and local).
  * **AC:**
    * Given `.github/workflows/ci.yml`, When the install step runs, Then dev tools come from the declared `[dependency-groups] dev` (e.g. `pip install --group dev` / `uv sync`) rather than a hand-listed `pip install pytest ruff`.
    * Given the change, When CI runs on 3.11/3.12/3.13, Then `ruff check .` and `pytest` still run and the matrix stays green (no mypy step, no format-check step added). *(NFR-PO1, NFR-Q1, NFR-Q2, ADR-006)*
    * Given the diff, When reviewed, Then it is scoped to the install step only — no new gate, no new dependency added to the `dev` group.
  * **Files:** `.github/workflows/ci.yml` *(no overlap with any other Phase 4 story)*
  * **Estimate:** S · **Status:** ⬜ todo · **Dependencies:** E0-S2
  * **Overlap:** None within Phase 4. Touches the shipped Epic 0 CI file, which is inert.

---

## Story Index

| Story | Title | Phase | Epic | Estimate | Status | Dependencies |
|-------|-------|-------|------|----------|--------|-------------|
| E0-S1 | src-layout package + console entry point | 0 | Packaging & Bootstrap | S | ✅ shipped | None |
| E0-S2 | CI matrix + ruff/pytest quality gate | 0 | Packaging & Bootstrap | M | ✅ shipped | E0-S1 |
| E1-S1 | Relocatable data-directory resolver | 0 | Paths & Config | S | ✅ shipped | None |
| E1-S2 | Fail-fast config loading w/ copy-example errors | 0 | Paths & Config | S | ✅ shipped | E1-S1 |
| E2-S1 | Idempotent four-table schema init | 0 | SQLite Storage | S | ✅ shipped | E1-S1 |
| E2-S2 | Idempotent upsert ingestion | 0 | SQLite Storage | M | ✅ shipped | E2-S1 |
| E2-S3 | Gap-filled daily close series | 0 | SQLite Storage | M | ✅ shipped | E2-S1 |
| E3-S1 | Tiered demo/pro client wiring | 1 | CoinGecko Client | M | ✅ shipped | E1-S2 |
| E3-S2 | Rate-limit backoff and polite pacing | 1 | CoinGecko Client | M | ✅ shipped | E3-S1 |
| E4-S1 | Subcommand-driven CLI workflow | 1 | Ingest Orchestration | M | ✅ shipped | E0-S1 |
| E4-S2 | Coin resolution by id or symbol | 1 | Ingest Orchestration | S | ✅ shipped | E4-S1 |
| E4-S3 | Per-coin failure isolation + stablecoin skip | 1 | Ingest Orchestration | M | ✅ shipped | E4-S1, E3-S1, E2-S2 |
| E5-S1 | Hand-rolled auditable indicators | 2 | Indicators & Signals | L | ✅ shipped | None |
| E5-S2 | Signal generation rules | 2 | Indicators & Signals | M | ✅ shipped | E5-S1, E2-S3 |
| E6-S1 | Single-file offline HTML/SVG dashboard | 3 | HTML Dashboard | L | ✅ shipped | E2-S3, E5-S2, E1-S1 |
| E7-S1 | Per-coin TA terminal readout | 3 | Terminal Reports | S | ✅ shipped | E4-S2, E5-S2 |
| E7-S2 | Portfolio report terminal readout | 3 | Terminal Reports | M | ✅ shipped | E4-S2, E5-S2, E2-S3 |
| E11-S1 | Add a dedicated `paths.py` unit test | 4 | Test & Release Hardening | S | ⬜ todo | E1-S1 |
| E11-S2 | Add a `--version` / version-display path | 4 | Test & Release Hardening | S | ⬜ todo | E4-S1 |
| E11-S3 | Focused helper test for `cli.py` | 4 | Test & Release Hardening | S | ⬜ todo | E11-S2, E4-S2 |
| E11-S4 | Align CI dev-tool install with `dev` group | 4 | Test & Release Hardening | S | ⬜ todo | E0-S2 |

---

## FR & NFR Coverage Map

Every functional requirement maps to at least one story. No orphans.

| Requirement | Priority | Story / Stories |
|-------------|----------|-----------------|
| FR-1 Subcommand-driven workflow | Must | E4-S1 (+ E11-S2 `--version`) |
| FR-2 Coin resolution by id/symbol | Must | E4-S2 (test: E11-S3) |
| FR-3 Per-coin failure isolation | Must | E4-S3 |
| FR-4 Stablecoin handling | Could | E4-S3, E7-S2 |
| FR-5 Tiered demo/pro client wiring | Must | E3-S1 |
| FR-6 Rate-limit backoff / pacing | Must | E3-S2 |
| FR-7 Fail-fast on missing credentials | Must | E1-S2 |
| FR-8 Idempotent schema init | Must | E2-S1 |
| FR-9 Idempotent upsert ingestion | Must | E2-S2 |
| FR-10 Gap-filled close series | Must | E2-S3 (+ E7-S1 empty-DB exit) |
| FR-11 Hand-rolled indicators | Must | E5-S1 |
| FR-12 Signal generation rules | Must | E5-S2 (+ E7-S1) |
| FR-13 Offline HTML/SVG dashboard | Must | E6-S1 |
| FR-14 Terminal reports | Should | E7-S1, E7-S2 |
| FR-15 Relocatable data directory | Should | E1-S1 (test: E11-S1) |
| FR-16 Config loading w/ copy-example errors | Must | E1-S2 (config), E4-S2 (coins) |
| NFR-PR1/2/3 Privacy / data locality | Must | E1-S1, E3-S1, E6-S1 |
| NFR-S1/2/3 Security | Must | E1-S2, E3-S1, E6-S1 |
| NFR-R1/2/3/4 Reliability | Must | E2-S2, E3-S2, E4-S3, E2-S3 |
| NFR-PO1/2/3 Portability | Must | E0-S1, E0-S2, E6-S1 |
| NFR-PF1/2 Performance | Should | E6-S1, E3-S2 |
| NFR-Q1/2/3 Quality bar | Must | E0-S2, E5-S1; reinforced by E11-S1/S3/S4 |
| NFR-Q4 No static type-checking (won't) | Won't | E0-S2 (gate stays ruff+pytest; E11-S4 keeps it so) |
| NFR-D1/2 Data granularity | Must/Could | E3-S2, E4-S3 |
| NFR-M1/2 Maintainability | Must/Should | E1-S1, E5-S1, E0-S1 |

---

## Notes on File Ownership & Wave Safety

- **Within Phase 4** (the only live wave), file ownership is conflict-free **except** E11-S2 and E11-S3, which both relate to `cli.py`. E11-S3 only *adds* `tests/test_cli.py`, but it depends on E11-S2's resolver — so the dependency edge (E11-S3 → E11-S2) keeps them sequenced rather than parallel. E11-S1 (`tests/test_paths.py`) and E11-S4 (`ci.yml`) own unique files and can run fully in parallel with each other and with E11-S2.
- **Phases 0–3 are shipped/inert.** Several shipped stories share a physical file (`db.py`, `coingecko.py`, `ta.py`, `cli.py`) but each owns a distinct, non-overlapping function surface. This is acceptable because no shipped story will be re-dispatched as live work; they exist for FR traceability.
- **No circular dependencies.** The dependency graph is a DAG; it mirrors the codebase's strictly-acyclic import graph (`paths`/`ta` leaves → `coingecko`/`db` → `dashboard`/`cli` apex). *(NFR-M1)*

---

## Related Documents
- PRD: [../_project-requirements.md](../_project-requirements.md)
- Architecture: [../_project-architecture.md](../_project-architecture.md)
- Brief: [../_project-brief.md](../_project-brief.md)
- UX Spec: [../design/_project-design.md](../design/_project-design.md) *(not yet present)*

---

## Triage Intake

Stories promoted from `/listen` → `/triage` signal sweeps. Ordered by ICE (descending). These are post-MVP, push-from-reality items — distinct from the FR-traceable Phases 0–4 above.

* **Story T.1 (Docs): Fix stale "build leg fails" note in CLAUDE.md**
  * **As a** contributor, **I want** CLAUDE.md's Build & Test section to match the actual gate behavior, **So that** I'm not told the build is broken when it passes.
  * **AC:**
    * The "NOTE: ... build leg currently fails (findings C1–C3)" text is removed or rewritten to reflect that the specialized gate config (commit 40849e2) dropped the mypy + `ruff format --check` legs and the gate now reports green (build 0 errors, test 38/38).
    * The Build & Test commands listed still match `.claude/core/gate.js` reality (verify against a fresh `node .claude/core/gate.js test` run).
  * **Estimate:** S   ·   **Severity:** Medium
  * **ICE:** 3×5×5 = 75   ·   **MoSCoW:** Should
  * **Source:** [origin: telemetry] CLAUDE.md build-leg note contradicts latest green gate run  ·  triaged 2026-06-06
  * **Dependencies:** None
  * **Status:** ✅ done 2026-06-06 — CLAUDE.md Build & Test section rewritten to match the specialized gate config; verified against a fresh green `node .claude/core/gate.js test` (build 0 errors, 38/38). Also corrected stale "27 tests" → 38.

* **Story T.2 (Docs): Update `_backlog.md` status line — Phase 4 / Epic 11 complete**
  * **As a** maintainer, **I want** the backlog header to reflect that Epic 11 is 4/4 done, **So that** the backlog doesn't advertise open work that no longer exists.
  * **AC:**
    * The `Status` row no longer reads "Phase 4 open"; Phase 4 stories (E11-S1..S4) are marked shipped/complete consistent with their per-story status.
    * The Executive Summary's "Phase 4 is the only genuinely open work" framing is reconciled with completion (or moved to past tense).
  * **Estimate:** S   ·   **Severity:** Low
  * **ICE:** 2×5×5 = 50   ·   **MoSCoW:** Could
  * **Source:** [origin: backlog] `_backlog.md` status line stale after Epic 11 completion  ·  triaged 2026-06-06
  * **Dependencies:** None
  * **Status:** ✅ done 2026-06-06 — status row now reads "Phases 0–4 shipped (Epic 11 complete, 4/4)"; Executive Summary Phase 4 framing moved to past tense; stale "27 tests" → 38.
