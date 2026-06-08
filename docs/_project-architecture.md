# Architecture: Domdhi.Crypto

| Attribute | Value |
|-----------|-------|
| **Version** | 1.0 |
| **Status** | Reverse-Engineered (brownfield) |
| **Author** | architect (via `/onboard`) |
| **Date** | 2026-06-05 |
| **Source** | Reverse-engineered from the codebase at commit `ad85772`; no prior PRD exists |

> **Reverse-Engineering Mode.** This document records what the codebase **actually is** as of June 2026 — not a target design. Every claim traces to a file in `src/domdhi_crypto/` or a config at the repo root. ADRs are marked `Status: Inferred` because they reconstruct decisions from the code rather than from an original design record. Anything labelled *(inferred)* is a reasonable reading of intent that the code implies but does not state outright.

---

## System Overview

Domdhi.Crypto (package `domdhi-crypto`) is a **self-hosted, local-first crypto portfolio and technical-analysis engine**. It pulls daily price history and live market snapshots from the CoinGecko REST API, stores them in a local SQLite database, computes a set of hand-rolled technical indicators (RSI, MACD, Bollinger Bands, ATR, annualized volatility, moving-average regime/cross signals) over the close series, and renders the results two ways: as terminal reports (`ta`, `report`) and as a single self-contained offline HTML dashboard (`dashboard`) combining inline-SVG sparklines with **interactive vendored-uPlot charts** (NAV/equity/risk; ADR-009) that surface the full cycle-2 decision layer (ledger, risk, signals, backtest).

The tool runs entirely on the user's machine. There is no server, no cloud component, no multi-user concept, and no network exposure beyond outbound calls to CoinGecko. The user's CoinGecko API key (`config.local.json`), their holdings and cost basis (`coins.local.json`), the price database (`crypto.db`), and the generated dashboard (`dashboard.html`) all live in a **data directory** — either `$DOMDHI_CRYPTO_HOME` or the current working directory — and every one of them is git-ignored. The repository ships only code, tests, and `.example.json` templates; no personal or secret data is ever committed.

The intended user is a single technically-comfortable crypto holder running a CLI from their own project folder (the README mentions viewing the dashboard in a browser or in Obsidian). The architecture optimizes for that one user's privacy and offline reproducibility: data is fetched once, cached idempotently, and all analysis and rendering happen against the local cache so the dashboard works with no network connection.

### Architecture Style

**Modular monolith — a single installable Python package exposing one CLI.** The forces that chose this shape, read from the code:

- **One user, one machine, modest load.** The whole job is "fetch a few coins, crunch indicators, render a page." There is no concurrency requirement, no request rate to absorb, no team-ownership boundary that would justify splitting into services. A monolith deploys and runs as one `pip install`.
- **Clear internal seams without process boundaries.** The engine is organized into Vertical-Slice sub-packages (`shared` → `ingest`/`signals`/`portfolio` → `agent`/`backtest`/`report` → `cli`) with a strictly acyclic import graph. The boundaries are real and enforced by import direction; they just don't need network calls between them. A separate top-level package (`domdhi_crypto_mcp`) exposes the agent layer with a one-way dependency on the engine.
- **Offline-first is a feature, not a constraint to engineer around.** Baking everything into one process and one HTML file is the simplest thing that delivers the privacy and offline goals.

### Key Quality Attributes

| Attribute | Priority | Target (observed / inferred from code) |
|-----------|----------|----------------------------------------|
| Privacy / data locality | **H** | Secrets and holdings never leave the machine; all four runtime files git-ignored. *Enforced by `.gitignore` + `paths.data_dir()`.* |
| Maintainability | **H** | Small modules (~40–320 lines), acyclic imports, pure indicator math, 308 unit tests, ruff-clean. |
| Correctness of TA math | **H** | Hand-rolled indicators return NaN on partial windows rather than silent garbage; gap-filled daily series feeds them. Covered by `tests/test_ta.py`. |
| Offline operability | **H** | Dashboard is a single file with no CDN/JS-framework/server dependency; opens directly from disk. |
| Performance | **L** | No stated targets. Workload is a handful of coins × ~365 daily rows; bounded by CoinGecko's rate limit, not local compute. |
| Scalability | **L** | Single-user by design. No horizontal-scale requirement exists. |
| Availability | **L** | Not a service; "availability" means "the CLI runs when invoked." No SLA. |

---

## Tech Stack

Every choice below is what is actually declared in `pyproject.toml`, `ruff.toml`, and `.github/workflows/ci.yml`, with the rationale the code's structure and comments imply.

### Language & Runtime
| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | `>=3.11` | Single-author scripting language well-suited to data wrangling; 3.11 minimum unlocks `datetime.UTC` (used in `cli.py`/`report/dashboard/`) and modern typing syntax. |
| Tested runtimes | CPython | 3.11 / 3.12 / 3.13 | CI matrix proves the tool runs on all three; the no-`pandas-ta` choice (see ADR-001) is what keeps 3.13 green. |

### Core Libraries (runtime dependencies)
| Library | Version | Used by | Rationale |
|---------|---------|---------|-----------|
| `requests` | `>=2.31` | `ingest/coingecko.py` | Battle-tested HTTP client for the one external dependency (CoinGecko). Imported lazily inside `CoinGecko.__init__` so non-network commands don't pay for it. |
| `pandas` | `>=2.0` | `shared/db.py`, `signals/ta.py`, `report/dashboard/` | Time-series indexing, reindex/forward-fill gap repair, rolling windows, and EWM for the indicators. The whole TA layer is expressed in pandas Series. |
| `numpy` | `>=1.24` | `signals/ta.py` | `sqrt` for annualized volatility and `isnan` for clean float coercion. |

There is **no web framework, no ORM, no background-job runner, no logging library, no real-time layer.** Their absence is intentional and load-bearing — see Cross-Cutting Concerns and the ADRs.

### Storage
| Role | Technology | Version | Rationale |
|------|-----------|---------|-----------|
| Primary store | SQLite (stdlib `sqlite3`) | bundled with Python | Local-first, zero-config, single-file, transactional. No server to run or secure. See ADR-002. |
| Cache | *(none separate)* | — | SQLite *is* the cache: it persists CoinGecko responses so analysis/rendering never re-hit the network. |
| Search | *(none)* | — | Not needed; lookups are by primary key (`coin_id`, `date`). |

### Presentation
| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Terminal output | `print` + hand-formatted columns (`cli.py`) | `ta` and `report` subcommands print fixed-width tables directly. |
| Dashboard | Single-file HTML + **inline SVG**, generated in Python (`report/dashboard/` package) | No JS framework, no CDN, no server. Charts are SVG `<polyline>`/`<polygon>` strings built from the data. See ADR-004. |
| Dashboard charts | **Vendored uPlot** (MIT, ~40KB min, pinned `.js` blob in `src/domdhi_crypto/report/dashboard/vendor/`) | Interactive time-series charts (NAV/equity/risk) inlined into `dashboard.html` at generation time, exactly like the `<style>` block. **Not a Python dependency** — it is a string the renderer writes into the output, so the 3-dep core (ADR-007) is untouched; no CDN, no build step, no Node. See ADR-009. |

### Build, Packaging & Tooling
| Concern | Technology | Version | Rationale |
|---------|-----------|---------|-----------|
| Build backend | **hatchling** (PEP 621 `pyproject.toml`) | per `[build-system]` | Modern, standards-based, minimal config; pairs with the `src/` layout. See ADR-003. |
| Package layout | **src-layout, two packages** (`src/domdhi_crypto/` + `src/domdhi_crypto_mcp/`) | — | Forces tests to run against the *installed* package, catching packaging mistakes. The MCP layer is a separate top-level package so the engine is usable with no agent code on the path. See ADR-003 and `docs/_slice-architecture.md`. |
| Console entry point | `[project.scripts] domdhi-crypto = "domdhi_crypto.cli:main"` | — | Installs a `domdhi-crypto` command; `python -m domdhi_crypto` also works via `__main__.py`. |
| Lint / format | **ruff** | `>=0.6` (config in `ruff.toml`) | One fast tool for lint + import-sort + format. line-length 110, target py311, rules `E/F/W/I/UP/B`. |
| Tests | **pytest** | `>=8` | `testpaths=["tests"]`, `addopts="-q"`. 308 unit tests with the network mocked (1 MCP test skips without the `[mcp]` extra). |
| Pre-commit | **pre-commit** | `>=3.7` | Whitespace/EOF/yaml/toml/merge-conflict/large-file hooks (`v5.0.0`) + `ruff --fix` (`v0.8.4`). |
| Type checking | **none** | — | mypy is *not* a dependency and there is *no* `[tool.mypy]` config. The quality bar is ruff + tests only. See ADR-006. |

### CI/CD & Infrastructure
| Service | Technology | Rationale |
|---------|-----------|-----------|
| CI | GitHub Actions (`.github/workflows/ci.yml`) | On push to `master` and on every PR: matrix over Python 3.11/3.12/3.13, `pip install -e .`, then `ruff check .` and `pytest`. Concurrency-cancels superseded runs. **No mypy step, no `ruff format --check` step.** |
| Hosting | *(none — local CLI)* | The tool runs on the user's machine. There is nothing to host. |
| Monitoring | *(none — local CLI)* | Single-user CLI; "monitoring" is the user reading stdout. |

---

## Architecture Diagram

```
                         ┌──────────────────────────────────────────┐
                         │            User's machine                 │
                         │   (data dir = $DOMDHI_CRYPTO_HOME or CWD)  │
                         └──────────────────────────────────────────┘

   coins.local.json            config.local.json
   (holdings,            (CoinGecko key,            ┌───────────────────┐
    cost basis)           tier)                     │  CoinGecko REST    │
        │                     │                      │  api.coingecko.com │
        │                     │                      │  (demo or pro)     │
        ▼                     ▼                      └─────────┬─────────┘
   ┌─────────────────────────────────────┐                    │ HTTPS GET
   │                cli.py                │   markets/chart/   │ (+429 backoff,
   │  argparse orchestrator               │   ohlc requests    │  polite pause)
   │  init · ingest · ta · report · dash  │◄───────────────────┤
   └───┬───────┬──────────┬───────────────┘                    │
       │       │          │                      ┌─────────────┴─────────────┐
       │       │          └─────────────────────►│   ingest/coingecko.py      │
       │       │                                  │  tier host+header wiring   │
       │       │                                  │  rate-limit retry/backoff  │
       │       │                                  └────────────┬───────────────┘
       │       │                                               │ JSON
       │       ▼                                               ▼
       │   ┌────────────────────────────────────────────────────────────┐
       │   │                     shared/db.py                            │
       │   │  SQLite: coins · prices · ohlc · snapshots                  │
       │   │  idempotent ON CONFLICT upserts                             │
       │   │  load_close_series(): reindex daily + forward-fill          │
       │   └───────────────┬──────────────────────────┬─────────────────┘
       │                   │ pandas Series             │ DataFrame
       │                   ▼                           ▼
       │            ┌──────────────┐          ┌──────────────────────────┐
       │            │  signals/    │          │   report/dashboard/       │
       │            │   ta.py      │◄─────────┤  inline-SVG HTML builder  │
       │            │  RSI MACD BB │  uses    │  (imports db, ta, paths)  │
       │            │  ATR vol     │          └────────────┬──────────────┘
       │            │  signals     │                       │
       │            └──────────────┘                       ▼
       │                                             dashboard.html
       └─────────────────────────────────────────►  (self-contained, offline)

            shared/paths.py  ──  leaf: resolves data dir + fixed filenames
                                 (imported by coingecko, db, dashboard, cli)
```

On top of the Cycle-1 spine above, Cycle-2 added three layers that all read the same
`shared/db.load_close_series` frame (and `signals/ta`) — no new external dependencies, the same
acyclic shape (leaves feed the apex `cli`, and now also `domdhi_crypto_mcp` / `report/dashboard`):

```
                 shared/db.load_close_series (close+volume frame)  ·  signals/ta.analyze
                          │                                                  │
       ┌──────────────────┼────────────────────────────┬────────────────────┘
       ▼                  ▼                             ▼                      ▼
  Signal/edge layer   Backtest layer            Portfolio layer        Agent interface
  ───────────────     ─────────────             ───────────────        ───────────────
  signals/             backtest/                 shared/db.py           agent/context.py
   factors.py           data_provider             migrations             (JSON-safe snapshot)
   (registry +          virtual_account           (transactions →       domdhi_crypto_mcp/
    safe evaluator       execution_simulator       source of truth)       decision.py
    + BUILTINS)          engine ─ factors.eval    portfolio/ledger.py    (DECISION_SCHEMA +
  signals/               attribution               (NAV + realized/       validate_decision)
   effectiveness.py    backtest/arena.py            unrealized P/L)      domdhi_crypto_mcp/
   (IC / ICIR)                                     portfolio/risk.py      server.py
                                                    (corr / vol /          (FastMCP stdio;
                                                     beta / drawdown)       lazy [mcp] extra,
                                                                            ADR-007)
       │                  │                             │                      │
       └──────────────────┴───────────────┬────────────┴──────────────────────┘
                                           ▼
                            cli.py  (factors · backtest · digest · mcp · …)
                            report/dashboard/  (Cycle-3: NAV/risk/signals/equity panels,
                                               vendored uPlot inlined — ADR-009)

  report/digest.py  ──  offline Markdown brief of triggered TA signals (pure build_digest + IO wrapper)
```

---

## Component Architecture

The import graph is strictly acyclic; arrows below point in the direction of `import`.
See `docs/_slice-architecture.md` for the full DAG and per-slice dependency table.

```
   Leaves:  shared/paths   signals/ta   portfolio/risk   (import nothing internal)
                               ▲
                               │
   signals/factors ────────────┘         portfolio/ledger ── shared/db
      ▲   ▲                                    ▲
      │   └── signals/effectiveness             │
      │   └── backtest/ (engine → factors.evaluate)
      │
   domdhi_crypto_mcp/decision ── signals/factors
   agent/context ── shared/db, signals/factors, signals/ta
   report/digest  ── agent/context, shared/db, shared/paths
   report/dashboard/ ── shared/db, signals/ta, shared/paths
                         (Cycle-3: + portfolio/ledger, portfolio/risk,
                                     signals/factors, report/digest, backtest/)
   domdhi_crypto_mcp/server ── agent/context, domdhi_crypto_mcp/decision,
                                shared/db, cli.load_coins   (lazy `mcp`, ADR-007)

   cli (apex) ── ingest/coingecko, shared/db, shared/paths, signals/ta,
                 signals/factors, signals/effectiveness,
                 backtest.{engine,attribution,arena}, report/dashboard,
                 report/digest, portfolio/ledger, portfolio/risk
```

`shared/paths`, `signals/ta`, and `portfolio/risk` are leaves; `cli` is the apex.
`domdhi_crypto_mcp/server` is a second near-apex (the agent entry point) — it lives in
a separate top-level package and imports from the engine only (one-way). No cycles —
every arrow points toward a leaf.

### `shared/paths.py` — data-directory resolver
- **Responsibility**: Resolve the single data directory (`$DOMDHI_CRYPTO_HOME` or CWD) and expose the fixed filenames (`config.local.json`, `coins.local.json`, `crypto.db`, `dashboard.html`, plus the `.example` templates).
- **Technology**: stdlib `os` + `pathlib` only.
- **Dependencies**: none (leaf).
- **API Surface**: `data_dir()`, `config_path()`, `coins_path()`, `db_path()`, `dashboard_path()`, and the `*_FILE` constants.
- **Boundary**: The *only* place that decides where files live. Every other module asks `paths` rather than hard-coding a location — this is what makes the data-dir override and git-ignore scheme work uniformly.

### `ingest/coingecko.py` — CoinGecko API client
- **Responsibility**: All outbound HTTP. Loads credentials from `config.local.json`, wires the demo-vs-pro base URL and auth header, and fetches `/coins/markets`, `/coins/{id}/market_chart`, and `/coins/{id}/ohlc`.
- **Technology**: `requests` (imported lazily inside `__init__`).
- **Dependencies**: `shared/paths` (for the config path).
- **API Surface**: `load_config()`, class `CoinGecko` with `markets(ids, vs)`, `market_chart(coin_id, days, vs)`, `ohlc(coin_id, days, vs)`. Private `_get()` handles retries.
- **Boundary / contract**: This is the system's **only** trust boundary to the outside world. On `429` it backs off `5 * 2**attempt` seconds for up to 4 attempts; on other non-2xx it raises (`raise_for_status`). A polite `pause` (default 2.0s) follows each successful call. Missing/placeholder API key raises `SystemExit` with a fix-it message. Returns raw decoded JSON — shaping into rows is the caller's job (`cli._daily_rows`).

### `shared/db.py` — SQLite persistence layer
- **Responsibility**: Schema definition and all reads/writes. Four tables: `coins`, `prices` (daily close/volume/market_cap), `ohlc` (candles), `snapshots` (point-in-time live quotes). Provides the gap-filled close series the indicators need.
- **Technology**: stdlib `sqlite3` + `pandas`.
- **Dependencies**: `shared/paths`.
- **API Surface**: `connect()`, `init_db()`, `upsert_coin/prices/ohlc`, `insert_snapshot`, `load_close_series()`, `load_ohlc()`, `latest_snapshot_price()`.
- **Boundary / contract**: All writes are **idempotent upserts** (`ON CONFLICT … DO UPDATE`, except snapshots which `DO NOTHING`), so re-running `ingest` refreshes/extends without duplicating (see ADR-005). `connect`/`init_db` accept an explicit path, which keeps the layer testable against `:memory:` or a temp file. `load_close_series()` reindexes to a **continuous daily** range and forward-fills `close` — this is the contract `signals/ta.analyze` depends on (it assumes a gap-free daily series).

### `signals/ta.py` — technical indicators (hand-rolled)
- **Responsibility**: Pure indicator math and signal rules. Wilder's RSI (EWM), MACD, Bollinger Bands + %B, ATR, annualized volatility; `analyze()` assembles the latest values, and `_signals()` turns them into plain-language calls (RSI 70/30 overbought/oversold, MACD histogram sign, price-vs-SMA200 bull/bear regime, golden/death cross at 50/200, Bollinger stretch).
- **Technology**: `numpy` + `pandas` only. **No `pandas-ta`** (see ADR-001).
- **Dependencies**: none internal (leaf).
- **API Surface**: `rsi`, `macd`, `bollinger`, `atr`, `annualized_vol`, `analyze(close)`, plus private `_signals`/`_f`.
- **Boundary / contract**: Stateless and pure — takes a pandas Series of closes (or OHLC DataFrame for `atr`) and returns Series/dicts. Partial windows surface as **NaN**, never as fabricated numbers; `analyze` only computes SMA200 when `n >= 200`. Because it imports nothing from the project, it is independently unit-testable and reference-checkable.

### `signals/factors.py` — declarative factor substrate (Epic 12)
- **Responsibility**: Turn TA from fixed functions into a *factor menu*. Three layers: (1) `FUNCTION_REGISTRY` — 38 pure-numpy/pandas primitives (MAs, momentum, trend, volatility, volume, time-series `TS_*`/`DELAY`/`DECAYLINEAR`/`LOG_RETURN`, cross-section `RANK`/`ZSCORE`/`NORMALIZE`, math), each carrying `FactorFunction` metadata (signature/description/example/category); (2) `evaluate(expr, frame)` — a safe expression evaluator; (3) `BUILTIN_FACTORS` — 47 ready-made factors expressed as data strings, with `DEFERRED_FACTORS` cataloguing high/low factors that await a unified OHLCV loader.
- **Technology**: `numpy` + `pandas`, and stdlib `ast`/`operator` for the evaluator. **No `pandas-ta`** and **no `asteval`** (ADR-001) — the evaluator is a default-deny AST walk, not `eval`.
- **Dependencies**: `signals/ta` only (reuses `rsi`/`macd`/`bollinger`/`atr`/`annualized_vol` + the `sma`/`ema` helpers). Leaf otherwise.
- **API Surface**: `FUNCTION_REGISTRY`, `FactorFunction`, `evaluate(expr, frame)`, `BUILTIN_FACTORS`, `DEFERRED_FACTORS`.
- **Boundary / contract**: `evaluate` permits only registry-function calls, frame column names, numeric literals, and arithmetic/comparison operators — every other AST node (attributes, dunders, imports, lambdas, comprehensions, subscripts, arbitrary calls) raises `ValueError` before evaluation; **no arbitrary code execution**. Bounded against DoS (node-count cap; float-coerced literals; arithmetic errors normalized to `ValueError`). Operates on the close+volume frame from `shared/db.load_close_series`; high/low factors raise "unknown column" rather than fabricating values. This is the cortex spine — Epic 13 (edge validation) and Epic 14 (MCP) consume the registry + evaluator. Covered by `tests/test_factors.py`.

### `signals/effectiveness.py` — factor edge measurement (Epic 13)
- **Responsibility**: Answer "does this factor predict?" via the Information Coefficient (IC) — the Spearman rank correlation between a factor value at time *t* and the *n*-period **forward** return — plus ICIR (mean/std of rolling IC) and a `score_factors` entry point that ranks `BUILTIN_FACTORS` by ICIR.
- **Technology**: `numpy` + `pandas` only — Spearman is `.rank(pct=True).corr()` (no scipy, ADR-001).
- **Dependencies**: `signals/factors` (+ numpy/pandas). Pure leaf — does not import `shared/db`; the caller passes the frame.
- **API Surface**: `information_coefficient(factor, close, horizon)`, `rolling_ic(...)`, `icir(...)`, `score_factors(frame, factors_list, horizon, window)`.
- **Boundary / contract**: Forward return is `close.pct_change(n).shift(-n)`; the NaN tail is **never filled** (the load-bearing look-ahead invariant). `icir` returns NaN (not `inf`) when IC dispersion is zero. Factors that fail to evaluate are reported with `ic=NaN`, never crashed on. Covered by `tests/test_effectiveness.py`.

### `backtest/` — look-ahead-safe event backtester (Epic 13)
- **Responsibility**: Answer "would this strategy have actually made money without cheating?" A package of pure leaves over the close+volume daily frame: `__init__` (frozen `Bar`/`Order`/`Fill`/`Trade`/`BacktestResult` type contract), `data_provider` (look-ahead-safe bar feed), `virtual_account` (cash/position/equity/drawdown/P&L), `execution_simulator` (slippage + fees), `engine` (the event loop), `attribution` (by-factor decomposition), and `arena` (multi-strategy universe harness for cortex vs buy-and-hold vs rule baseline).
- **Technology**: `pandas` + stdlib; `engine` also calls `signals/factors.evaluate`. No `shared/db` import (frames are passed in).
- **Dependencies (internal DAG)**: `__init__` (leaf) ← {`data_provider`, `virtual_account`, `execution_simulator`} ← `engine` ← `attribution` consumes `engine`'s `BacktestResult`; `arena` wraps `engine`.
- **API Surface**: `engine.run_backtest(frame, rules, *, initial_cash, slippage_bps, fee_rate) -> BacktestResult`; `engine.SignalRule`; `attribution.attribute_by_factor(result)`; `arena.run_arena(...)`. `BacktestResult` carries `trades`, `summary`, and (since Epic 18-S5) `equity_curve: pd.Series` (per-bar marked account value, default empty) so consumers like `report/dashboard` can chart it; the dataclass is `eq=False` because a Series field makes the auto `__eq__` ambiguous.
- **Boundary / contract**: The engine only ever passes `frame.loc[:T]` to `signals/factors.evaluate` (look-ahead discipline, enforced by a truncation-invariance test); marks equity once per bar; force-closes open positions at the final bar so `total_realized_return` reconciles exactly with attribution. Operates on `shared/db.load_close_series` (close+volume daily) only — intrabar high/low execution awaits a unified OHLCV loader. Covered by `tests/test_backtest_*.py`.

### Agent interface layer — `agent/context.py` · `domdhi_crypto_mcp/decision.py` · `domdhi_crypto_mcp/server.py` (Epic 14)
- **Responsibility**: Expose the signal substrate + portfolio context to an LLM agent (Claude) over MCP and define the decision contract it must return (FR-22, FR-23). `agent/context.py` assembles a single JSON-safe snapshot (`build_context` → `{symbol, signals, position, factor_menu}` — `signals/ta.analyze` summary + latest value of every builtin factor, the holding priced from `coins.local.json`, and the full factor menu). `domdhi_crypto_mcp/decision.py` is the output contract: `DECISION_SCHEMA` (action buy/hold/sell/nothing + rationale + cited factors), `validate_decision` (hand-rolled, raises `ValueError`), and `build_trigger_context` (the event-driven why-now payload). `domdhi_crypto_mcp/server.py` wraps both as four FastMCP tools (`get_context`, `prepare_decision`, `get_decision_schema`, `validate_decision`).
- **Technology**: `agent/context` is pure numpy/pandas/stdlib (no new deps). `domdhi_crypto_mcp/decision` depends on `signals/factors` only. `domdhi_crypto_mcp/server` needs the **optional `[mcp]` extra** — imported lazily inside `build_server()` so the module loads (and tests run) without it. See ADR-007.
- **Dependencies (internal DAG)**: `domdhi_crypto_mcp/decision` ← `signals/factors`; `agent/context` ← `shared/db`, `signals/factors`, `signals/ta`; `domdhi_crypto_mcp/server` ← `agent/context`, `domdhi_crypto_mcp/decision`, `shared/db`, `cli.load_coins` (the IO boundary) — no module imports `mcp` at top level.
- **Import convention**: `domdhi_crypto_mcp` is a separate top-level package; it imports from `domdhi_crypto.*` slices only (one-way). The engine never imports from `domdhi_crypto_mcp`.
- **API Surface**: `agent.context.build_context(symbol, *, conn, coins_cfg)`; `domdhi_crypto_mcp.decision.{DECISION_SCHEMA, validate_decision, build_trigger_context}`; `domdhi_crypto_mcp.server.{build_server, run}`; `domdhi-crypto mcp` CLI subcommand (launches `run`; an absent extra → `SystemExit` with a pip-install hint).
- **Boundary / contract**: 100% JSON-serializable output — non-finite floats (NaN *and* ±Infinity) are coerced to `null`, and `_validate_context` ends with a `json.dumps(allow_nan=False)` self-check. Tools are pure w.r.t. IO (injected `conn`/`coins_cfg`) and **never raise out** to the transport: unknown symbols return `{"error": ...}`, malformed decisions return `{"ok": false, "error": ...}`. Read-only over the DB; no live-exchange calls (NFR-C2-3). Covered by `tests/test_context.py`, `tests/test_decision.py`, `tests/test_mcp_server.py`.

### `report/digest.py` — offline triggered-signal brief (Epic 15)
- **Responsibility**: Render an offline Markdown brief of *triggered* TA signals across the held coins — the human-readable "what's firing now" companion to the agent's MCP context. `build_digest` walks each non-stable coin's `agent/context.build_context`, keeps only the signals that are actually firing (`_is_triggered`), and formats per-coin sections; `build` is the IO wrapper that loads coins, opens the DB, and writes the file.
- **Technology**: stdlib (`json`/`math`/`datetime`/`pathlib`) only — no new deps. The numeric formatting helpers (`_fmt_num`/`_fmt_money`/`_fmt_pct`) NaN-guard so partial windows render as text, not garbage.
- **Dependencies**: `agent/context`, `shared/db`, `shared/paths`.
- **API Surface**: `build_digest(coins_cfg, *, conn) -> str` (pure), `build(out_path=None, *, conn=None, coins_cfg=None) -> Path` (IO wrapper); `domdhi-crypto digest` CLI subcommand.
- **Boundary / contract**: Read-only over the DB; pure `build_digest` (injected `conn`/`coins_cfg`) is independently testable, with `build` the only IO seam. Covered by `tests/test_digest.py`.

### `portfolio/ledger.py` — NAV + average-cost P/L (Epic 16)
- **Responsibility**: Replay the user-entered `transactions` table into a portfolio time series and P/L. `nav_series` produces a dated net-asset-value curve; `realized_pl`/`unrealized_pl` compute average-cost realized and unrealized profit/loss; `_replay` is the average-cost accumulator.
- **Technology**: `pandas` + stdlib `math` only.
- **Dependencies**: `shared/db` (reads `transactions` + priced via market data).
- **API Surface**: `nav_series(conn, coins_cfg)`, `realized_pl(conn, coins_cfg=None)`, `unrealized_pl(conn, coins_cfg)`.
- **Boundary / contract**: Reads the `transactions` slice (the DB's source-of-truth portion, ADR-008) plus cached prices; the existing average-cost clamp behavior on incoherent sequences (e.g. oversell) is characterization-tested (Epic 20-S4 may add optional strict validation). Surfaces empty/`n/a` when there are no transactions rather than erroring. Covered by `tests/test_ledger.py`.

### `portfolio/risk.py` — portfolio risk metrics (Epic 16, pure leaf)
- **Responsibility**: Cross-coin risk over aligned log returns: `correlation_matrix`, `portfolio_vol`, `beta_to_btc`, and `max_drawdown`. Aligns each coin's returns on a common index before computing.
- **Technology**: `numpy` + `pandas` + stdlib `math`. No scipy (ADR-001).
- **Dependencies**: `shared/db` (for the per-coin close series); otherwise a pure leaf — imports nothing else internal.
- **API Surface**: `correlation_matrix(conn, coins_cfg)`, `portfolio_vol(conn, coins_cfg)`, `beta_to_btc(conn, coins_cfg)`, `max_drawdown(series)`.
- **Boundary / contract**: Under-window or insufficient-overlap cases surface as **NaN** (never fabricated, never a crash) — the load-bearing invariant the Cycle-3 risk panel (Epic 18-S3) renders as "n/a". Stablecoins are excluded from the return matrix. Covered by `tests/test_risk.py`.

### `report/dashboard/` — offline HTML/SVG renderer (package)
- **Responsibility**: Build a single self-contained `dashboard.html`: summary cards (portfolio value, unrealized P/L, cost basis, position count), allocation bars, holdings table with a 90-day sparkline and a signal pill, and per-coin 180-day price charts (price + SMA20/50/200) with an RSI(14) strip, plus Cycle-3 panels (NAV/equity/risk via vendored uPlot).
- **Technology**: pure-Python string building; static charts are inline SVG; interactive charts use vendored uPlot inlined at generation time; styling is an inline `<style>` block (GitHub-dark palette; `theme.py`). No JS framework, no CDN. The package is split into `__init__.py` (build orchestration), `theme.py` (palette), `charts.py` (SVG/uPlot toolkit), `panels.py` (data panels + registry), `scaffold.py` (page template), and `vendor/` (uPlot static assets).
- **Dependencies**: `shared/db`, `signals/ta`, `shared/paths`; Cycle-3 adds `portfolio/ledger`, `portfolio/risk`, `signals/factors`, `report/digest`, `backtest/`.
- **API Surface**: `build(open_after=False)` (via `__init__.py`) → writes the file, returns its path; optional `--open` launches the browser via `webbrowser`.
- **Boundary / contract**: Read-only over the DB; produces one artifact. All data is baked in at generation time, so the file is fully functional offline. Missing `coins.local.json` raises `SystemExit` with a copy-the-example message. Vendored assets (`vendor/uplot.min.js`, `vendor/uplot.min.css`) are resolved package-relative via `__file__` — not through `shared/paths` (ADR-009).

### `cli.py` (+ `__main__.py`) — orchestrator / composition root
- **Responsibility**: argparse front door and host that wires every slice. Subcommands `init`, `ingest [--days]`, `ta <symbol>`, `report`, `dashboard [--open]`, `factors <symbol> [--horizon --top]`, `backtest <symbol> [--factor --entry --exit --cash --slippage-bps --fee-rate]`, `digest`, `mcp`, and `arena`. Loads `coins.local.json`, drives `ingest/coingecko` → `shared/db` ingest, and renders terminal reports.
- **Technology**: stdlib `argparse`, `json`, `datetime`.
- **Dependencies**: `report/dashboard`, `shared/db`, `shared/paths`, `signals/ta`, `ingest/coingecko`, `signals/effectiveness`, `signals/factors`, `backtest.{engine,attribution,arena}`, `report/digest`, `portfolio/ledger`, `portfolio/risk` (the apex of the DAG — every slice funnels here). `domdhi_crypto_mcp` is reached via a lazy import inside `cmd_mcp` only.
- **API Surface**: `main()` (the entry point); `cmd_*` handlers; helpers `load_coins`, `_daily_rows` (collapses `market_chart` arrays to one row per UTC date, last point wins), `_resolve` (id-or-symbol lookup), `_load_series_or_exit` (resolve + stablecoin/no-data guard + short-series warning, shared by `factors`/`backtest`).
- **Boundary / contract**: Stablecoins (`"stable": true` in `coins.local.json`) are skipped for history ingestion and TA, and rejected up front by `ta`/`factors`/`backtest`. `factors`/`backtest` validate their numeric flags (`--horizon`/`--top` ≥ 1, `--cash` > 0, `--slippage-bps`/`--fee-rate` ≥ 0) at the CLI boundary. Per-coin fetch failures are caught and printed, not fatal — ingest continues for the rest.

---

## Data Architecture

### Entity-Relationship Overview

```
coins (id PK) ──< prices    (coin_id, date PK)      daily close/volume/market_cap   ┐
              ──< ohlc      (coin_id, ts   PK)      candles (epoch-ms open)          │ regenerable
              ──< snapshots (coin_id, fetched_at PK) point-in-time live quote        ┘ cache tables

transactions  (added by migration, Epic 16 / ADR-008)  ── user-entered buys/sells   ── SOURCE OF TRUTH
              keyed coin + timestamp; replayed by ledger into NAV + realized/unrealized P/L.
              NOT re-fetchable from CoinGecko → preserved across schema change by add-only migrations.

coins.id is the CoinGecko coin id (e.g. "bitcoin"). It is the join key across all tables,
though SQLite FKs are not declared — referential integrity is maintained by the ingest code.
```

### Key Entities
| Entity | Storage | Primary Key | Access Pattern | Volume (est.) |
|--------|---------|-------------|----------------|---------------|
| `coins` | `coins` table | `id` | upsert on ingest; read on every command | one row per tracked coin (handful) |
| `prices` | `prices` table | `(coin_id, date)` | write-on-ingest, read-heavy for TA/charts | ~365 rows/coin/year of history |
| `ohlc` | `ohlc` table | `(coin_id, ts)` | write-on-ingest; read by `load_ohlc` (ATR) | ≤ ~365 candles/coin (days capped at 365) |
| `snapshots` | `snapshots` table | `(coin_id, fetched_at)` | append-on-ingest, read latest for live price/P/L | grows by one row per coin per `ingest` run |
| `transactions` | `transactions` table (added by migration, ADR-008) | coin + timestamp | user-entered (buys/sells); read by `ledger` to replay NAV + realized/unrealized P/L | grows by one row per recorded trade — **source of truth, not regenerable** |

### Consistency & Ownership
- **Single writer.** Only `cli.cmd_ingest` writes (via `db.upsert_*`/`insert_snapshot`). There is exactly one process, one connection at a time, and no concurrency — so "consistency model" is simply SQLite's local ACID transactions with explicit `commit()` per coin.
- **Idempotency is the integrity guarantee.** `prices`/`ohlc`/`coins` use `ON CONFLICT DO UPDATE` (latest fetch wins per key); `snapshots` use `DO NOTHING` (first write of a given timestamp wins, so re-running within the same second won't error). Re-ingesting is always safe (ADR-005).
- **Gap repair is a read-time concern.** Raw `prices` may have missing days; `load_close_series` reindexes to a gap-free daily range and forward-fills `close` *only when read for analysis*. Stored data is never mutated to fill gaps — keeping the store faithful to what CoinGecko returned.
- **Holdings config is not in the DB.** Tracked coins, the stablecoin flag, and the vs-currency live in `coins.local.json`, read fresh on each command. Market data (`prices`/`ohlc`/`snapshots`) is a regenerable cache.
- **`transactions` is the DB's source-of-truth slice (ADR-008).** As of Epic 16 the DB is a **partial source of truth**: the user-entered `transactions` table cannot be re-fetched from CoinGecko, so it is preserved across schema evolution by **add-only** migrations (`db.migrate`, tracked by `schema_version`). The cache tables remain safe to delete + re-ingest; the `transactions` slice is not. "Delete `crypto.db` and re-ingest" recovers only the cache. *(See ADR-008 and Risks.)*

### Data Flow

```
CoinGecko JSON
   │  cg.markets() / market_chart() / ohlc()
   ▼
cli._daily_rows()  ──collapse to one row per UTC date──┐
   │                                                   │
   ▼                                                   ▼
db.upsert_prices / upsert_ohlc / insert_snapshot  →  crypto.db  (idempotent)
                                                       │
                              db.load_close_series()   │  reindex daily + ffill
                                                       ▼
                                              pandas close Series
                                                       │
                                              ta.analyze()  → indicators + signals
                                                       │
                         ┌─────────────────────────────┴───────────────┐
                         ▼                                              ▼
                cli terminal report                    report/dashboard/__init__.build()
                (ta / report)                          inline-SVG + uPlot HTML → dashboard.html
```

---

## API Design

### API Style
**This project exposes no API of its own** — no HTTP server, no RPC, no public library surface beyond the console entry point. The relevant API is the **CoinGecko REST client** it *consumes*, plus the **CLI** it presents to the user.

### Consumed external API — CoinGecko v3
| Endpoint (via `ingest/coingecko.py`) | Purpose | Auth | Notes |
|-------------------------------|---------|------|-------|
| `GET /coins/markets` | live price, market cap, 24h/7d/30d change | API key header | one call covers all coins (`ids` joined) |
| `GET /coins/{id}/market_chart` | historical price/volume/market-cap series | API key header | `days>=90` yields daily points |
| `GET /coins/{id}/ohlc` | OHLC candles | API key header | granularity varies by `days`; `days` capped at 365 on ingest |

### CLI "endpoints" (subcommands)
| Command | Args | Auth | Description |
|---------|------|------|-------------|
| `init` | — | none | Create `crypto.db` and its schema |
| `ingest` | `--days` (default 365) | needs key | Fetch snapshot + history for all non-stable coins, upsert to DB |
| `ta` | `<symbol>` | none (reads DB) | Print indicators + signals for one coin |
| `report` | — | none (reads DB) | Live portfolio value, P/L, per-coin signal |
| `dashboard` | `--open` | none (reads DB) | Build `dashboard.html`, optionally open it |
| `factors` | `<symbol> --horizon --top` | none (reads DB) | Rank built-in factors by IC/ICIR for one coin |
| `backtest` | `<symbol> --factor --entry --exit --cash --slippage-bps --fee-rate` | none (reads DB) | Look-ahead-safe backtest of one factor rule + by-factor attribution |
| `digest` | — | none (reads DB) | Write an offline Markdown brief of currently-triggered TA signals across held coins (Epic 15) |
| `mcp` | — | none (reads DB) | Launch the FastMCP stdio server for an LLM agent; requires the optional `[mcp]` extra, else `SystemExit` with a pip-install hint (Epic 14, ADR-007) |
| `arena` | `<symbol> --factor --entry --exit --baseline-factor --cash --slippage-bps --fee-rate` | none (reads DB) | Local offline paper-trade arena (Epic 19-S2/S3): cortex equity/return vs buy-and-hold + a rule baseline, with relative performance and per-factor attribution. Wraps `arena.run_arena` (a pure leaf over the look-ahead-safe `backtest.engine`). |

### Conventions (observed)
- **Versioning**: external API is pinned to CoinGecko `/api/v3`; the package itself is `version = "0.1.0"`.
- **Tier wiring**: `tier: "demo"` vs `"pro"` in `config.local.json` selects base URL (`api.` vs `pro-api.`) and header name (`x-cg-demo-api-key` vs `x-cg-pro-api-key`).
- **Rate limiting (client-side)**: exponential backoff on HTTP 429 (`5·2^attempt`, up to 4 tries) plus a fixed 2.0s inter-call pause.
- **Error format**: errors surface as `SystemExit` (for user-fixable config problems) or printed per-coin warnings (for transient fetch failures); there is no structured error envelope.

---

## Authentication & Authorization

### Authentication
- **To CoinGecko**: a single API key sent as an HTTP header. The key is read from `config.local.json` (git-ignored). `tier` chooses the demo or pro header name. A missing or placeholder (`"PASTE…"`) key fails fast with `SystemExit` and a fix-it message.
- **To the tool itself**: **none.** It is a local single-user CLI; whoever can run the binary on the machine is the user. There is no login, session, or token concept.

### Authorization
- **Model**: not applicable. No roles, no multi-tenant access control, no per-resource permissions. The OS file permissions on the data directory are the entire access-control story.
- **Secret handling**: the API key lives only in `config.local.json`, which is git-ignored both by the project block and (defense-in-depth) by the managed `*.local.*` pattern; the repo ships `config.example.json` with a placeholder instead.

---

## Infrastructure & Deployment

### Deployment Architecture

```
There is no deployment topology — no servers, load balancers, or managed databases.

  ┌────────────────────────────────────────────┐
  │              User's machine                 │
  │                                             │
  │   pip install -e .   (or  pip install .)    │
  │        │                                    │
  │        ▼                                    │
  │   domdhi-crypto  <command>                  │
  │        │                                    │
  │   reads/writes ▼  (data dir = $DOMDHI_CRYPTO_HOME or CWD)
  │     config.local.json  coins.local.json           │
  │     crypto.db          dashboard.html        │
  └────────────────────────────────────────────┘
            │ outbound HTTPS only
            ▼
     api.coingecko.com / pro-api.coingecko.com
```

*(All of the above is inferred from code + packaging; the project has no deploy scripts, containers, or IaC because it is a local CLI.)*

### Environments
| Environment | Purpose | Location | Notes |
|------------|---------|----------|-------|
| Local (the only one) | Run the tool | User's machine | Install with pip; data dir is CWD or `$DOMDHI_CRYPTO_HOME`. |
| CI | Lint + test on every push/PR | GitHub Actions runners | Matrix 3.11/3.12/3.13; does *not* deploy anything. |

There is no staging or production environment — there is nothing to stage or serve.

### Rollback & Migration
- **Code rollback**: revert the package version / `git checkout` a prior commit and reinstall. There is no running service to roll back.
- **Data migration**: as of Epic 16 (ADR-008) there **is** a minimal migration scaffold — `db.migrate(conn)` applies an append-only `MIGRATIONS` registry tracked by a `schema_version` table, wired into `init_db`. The regenerable baseline (cache tables) is still created idempotently via `CREATE TABLE IF NOT EXISTS` in `db.SCHEMA`; *additive* schema change (e.g. the `transactions` table) lands as a migration so user source-of-truth data is preserved. "Delete `crypto.db` and re-ingest" is **only** safe for the cache tables now — it would destroy recorded transactions. *(See ADR-008 and Risks.)*

### CI/CD Pipeline

```
push to master / open PR
        │
        ▼
GitHub Actions  (matrix: Python 3.11, 3.12, 3.13)
        │
   pip install -e .   +   pip install pytest ruff
        │
   ruff check .   ──►  pytest
        │
   (no mypy, no ruff-format-check, no deploy step)
        │
        ▼
   green ✓ / red ✗   — that is the entire pipeline
```

---

## Architecture Decision Records (ADRs)

> All ADRs are `Status: Inferred` — reconstructed from the code, not from an original design record. They document the decisions the codebase clearly embodies, the alternatives a reasonable author would have weighed, and the consequences now baked in.

### ADR-001: Hand-rolled TA indicators instead of `pandas-ta`
- **Status**: Inferred
- **Date**: 2026-06-05 (reconstructed)
- **Context**: The tool needs RSI, MACD, Bollinger, ATR, and volatility. A library (`pandas-ta`) exists for exactly this. The module docstring in `signals/ta.py` states the reason directly: `pandas-ta` "breaks on numpy 2.x / Python 3.13," and CI targets 3.13.
- **Decision**: Implement every indicator by hand in pure pandas/numpy. Each function takes a Series and returns a Series; partial windows surface as NaN.
- **Alternatives Considered**:
  - **`pandas-ta`**: batteries-included, but pins/breaks against numpy 2.x and Python 3.13 — would have blocked the 3.13 CI leg and chained the project to an unmaintained transitive constraint.
  - **TA-Lib (C library)**: fast and authoritative, but requires a native build step, which breaks the "`pip install` and go" / pure-Python install story.
- **Consequences**: Zero TA dependency to keep current; the 3.11–3.13 matrix stays green; the math is reference-checkable and unit-tested (`tests/test_ta.py`). Cost: the project now *owns* the correctness of its indicators — a bug in Wilder's RSI is the project's bug, and adding a new indicator means writing it, not importing it. This is a **candidate maintenance surface** (not currently reported as painful).

### ADR-002: Local SQLite as the only store
- **Status**: Inferred
- **Date**: 2026-06-05 (reconstructed)
- **Context**: Price history and snapshots must persist between runs so analysis works offline and the network is hit only on `ingest`. The tool is single-user and local-first.
- **Decision**: Use stdlib `sqlite3` with a single `crypto.db` file in the data directory. Four tables, PK-keyed, transactional.
- **Alternatives Considered**:
  - **Flat files (CSV/Parquet/JSON)**: simple, but no upsert semantics, no transactional integrity, and awkward partial updates — the idempotent re-ingest pattern would be hand-rolled and fragile.
  - **A server DB (Postgres/MySQL)**: gives concurrency and richer features the tool does not need, at the cost of running and securing a server — directly at odds with local-first/zero-config.
- **Consequences**: Zero-config, zero-server, single-file, ACID. Trivially testable against `:memory:`. The DB is a regenerable cache, not a source of truth, which is what makes the "delete and re-ingest" migration story acceptable. Cost: no concurrency (fine for one user) and no built-in migration tooling (see ADR / Risks).

### ADR-003: src-layout package built with hatchling (PEP 621)
- **Status**: Inferred
- **Date**: 2026-06-05 (reconstructed)
- **Context**: The project must be installable, expose a `domdhi-crypto` command, and run its tests against the real installed package rather than the source tree.
- **Decision**: Adopt the `src/domdhi_crypto/` src-layout, declare everything in PEP 621 `pyproject.toml`, and use **hatchling** as the build backend with `[tool.hatch.build.targets.wheel] packages = ["src/domdhi_crypto"]`. Expose a console script and `__main__.py`.
- **Alternatives Considered**:
  - **Flat layout (package at repo root)**: less ceremony, but tests can import the source dir without installing, which hides packaging bugs (missing modules, bad entry points).
  - **setuptools / Poetry / flit backends**: all viable; hatchling was chosen for minimal config and clean PEP 621 alignment. Poetry would have added a lockfile/CLI convention the project does not otherwise use.
- **Consequences**: CI installs with `pip install -e .` and tests run against the installed package, so packaging breakage fails fast. Standards-based metadata; both `domdhi-crypto` and `python -m domdhi_crypto` work. Cost: contributors must understand the src-layout (imports resolve from the installed package, not `./`).

### ADR-004: Single-file offline HTML dashboard (inline SVG, no JS framework)
- **Status**: Inferred
- **Date**: 2026-06-05 (reconstructed)
- **Context**: The user wants a visual portfolio/TA view that works offline, carries no secrets, and needs no infrastructure. `report/dashboard/__init__.py`'s docstring states the constraint: "No web server, no CDN, no JS framework."
- **Decision**: Generate one self-contained `dashboard.html` in Python. Charts are inline SVG `<polyline>`/`<polygon>` strings; styling is an inline `<style>` block; all data is baked in at generation time. Optional `--open` uses `webbrowser`.
- **Alternatives Considered**:
  - **A JS charting lib (Chart.js / Plotly / D3)**: richer interactivity, but needs a CDN (breaks offline) or a bundled vendored blob (bloat + maintenance), and adds a frontend toolchain to a Python CLI.
  - **A served web app (Flask/Dash/Streamlit)**: live and interactive, but requires running a server and re-introduces an attack surface and an "is it up?" concern the local-first design deliberately avoids.
- **Consequences**: The dashboard is a portable artifact — opens from disk, works in a browser or Obsidian, with no network. Trivial to share or archive. Cost: charts are static (no zoom/tooltips), and the SVG/HTML is hand-built string construction — a **candidate maintenance surface** if the visuals grow (not currently reported as painful).

### ADR-005: Idempotent upsert ingestion
- **Status**: Inferred
- **Date**: 2026-06-05 (reconstructed)
- **Context**: `ingest` may be run repeatedly, with overlapping date ranges, and partial-failure mid-run is expected (per-coin fetches are wrapped in try/except). Re-runs must not duplicate or corrupt data.
- **Decision**: Make every write idempotent. `coins`/`prices`/`ohlc` use `INSERT … ON CONFLICT(pk) DO UPDATE` (latest fetch wins per key); `snapshots` use `ON CONFLICT DO NOTHING` (first write of a timestamp wins). Commit per coin so a later failure doesn't lose earlier successes.
- **Alternatives Considered**:
  - **Plain INSERT + dedupe later**: would throw `UNIQUE` errors on re-ingest and require a separate cleanup pass.
  - **Delete-then-insert per coin**: simpler to reason about but destroys data on a mid-write crash and rewrites unchanged rows needlessly.
- **Consequences**: `ingest` is safe to re-run any time; the DB is self-healing on overlap and resilient to partial failure. This is precisely what lets the DB be treated as a disposable, regenerable cache (reinforcing ADR-002). Cost: per-coin commits mean a crash can leave the DB partially updated — acceptable because the next ingest reconciles it.

### ADR-006: No static type-checking — ruff-only quality bar
- **Status**: Inferred
- **Date**: 2026-06-05 (reconstructed)
- **Context**: The project needs a defensible quality gate but is a small, single-author codebase. `mypy` is **not** a dependency, there is **no** `[tool.mypy]` config, and CI runs only `ruff check` + `pytest`.
- **Decision**: Set the quality bar at **ruff (lint + import-sort + format rules `E/F/W/I/UP/B`) plus pytest unit tests (308 tests, network mocked)**. No static type checker; the code is largely untyped.
- **Alternatives Considered**:
  - **Add mypy/pyright**: catches type errors statically, but imposes annotation overhead and a recurring fight with pandas/numpy stubs on a small codebase where tests already cover the critical math.
  - **Ruff format-check in CI**: would enforce formatting in CI too; the project relies on the pre-commit `ruff --fix` hook for that instead, keeping CI to lint + test.
- **Consequences**: Fast, low-friction checks; the test suite (not the type system) is the safety net for indicator correctness and DB behavior. Cost: type errors (e.g. a wrong-shaped pandas object) are caught only at runtime or by tests, not statically — a deliberate trade for a small, well-tested codebase. Revisit if the codebase grows or gains contributors.

### ADR-007: MCP server via an optional `[mcp]` extra — core stays 3-dep
- **Status**: Accepted
- **Date**: 2026-06-06
- **Context**: Epic 14 exposes the signal substrate + portfolio context to an LLM agent over MCP (FR-22/FR-23). The PRD names an "MCP server" in the stack, but the project has held a strict three-runtime-dependency floor (requests/pandas/numpy; ADR-001's dependency-minimal, auditable ethos). The official `mcp` SDK pulls in a meaningful chain (pydantic/anyio/httpx-sse).
- **Decision**: Adopt the official `mcp` SDK (FastMCP) but as an **optional** dependency: `[project.optional-dependencies] mcp = ["mcp>=1.2"]`. Core `dependencies` is unchanged. `domdhi_crypto_mcp/server.py` imports the SDK lazily inside `build_server()` (never at module top); the pure context-assembly (`agent/context.py`) and decision-contract (`domdhi_crypto_mcp/decision.py`) modules carry zero MCP dependency and are fully testable offline. Tests touching the SDK use `pytest.importorskip("mcp")`, so the gate (CI runs on core deps only) stays green without the extra.
- **Alternatives Considered**:
  - **Hand-rolled stdio JSON-RPC (MCP subset)**: zero new deps, maximally auditable, but reinvents a moving protocol and is more code to own.
  - **Add `mcp` to core dependencies**: simplest wiring, but breaks the 3-dep floor for every user — including those who only use the CLI/dashboard and never run the agent server.
  - **Defer the wire protocol (substrate-only)**: lowest risk, but leaves FR-22's "Claude calls the context tool" unmet this cycle.
- **Consequences**: CLI/dashboard users install nothing new; agent users run `pip install domdhi-crypto[mcp]` then `domdhi-crypto mcp`. The lazy-import discipline is load-bearing — a top-level `mcp` import would break the gate for anyone without the extra (guarded by `tests/test_mcp_server.py::test_no_top_level_mcp_import`). The pure/transport split keeps the substrate auditable and dependency-free.

### ADR-008: Schema migrations + the DB as a *partial* source of truth (amends ADR-002/-003)
- **Status**: Accepted
- **Date**: 2026-06-06
- **Context**: Epic 16 (Portfolio Context) adds a user-entered `transactions` table (buys/sells) that the ledger replays into NAV + realized/unrealized P/L. Unlike `prices`/`ohlc`/`snapshots`, this data **cannot be re-fetched from CoinGecko** — "delete `crypto.db` and re-ingest" would destroy it. That directly contradicts ADR-002/-003's premise that the DB is a wholly regenerable cache with no migration framework.
- **Decision**: Introduce a minimal, ordered migration scaffold in `shared/db.py` — a `schema_version` table, an append-only `MIGRATIONS: list[(version, sql)]` registry, and `migrate(conn) -> int` (idempotent; applies pending versions in ascending order; wired into `init_db` after the baseline `SCHEMA`). The DB becomes a **partial source of truth**: the cache tables (`prices`/`ohlc`/`snapshots`/`coins`) remain regenerable and safe to delete+re-ingest, but the `transactions` slice is user source-of-truth and is preserved across schema evolution by migrations (which are **add-only** — never DROP/rewrite). `migrate()` is the sanctioned write path for schema change; editing `SCHEMA` in place is now reserved for the regenerable baseline only.
- **Alternatives Considered**:
  - **Keep the no-migration stance, store transactions in a sidecar JSON file**: preserves ADR-002 literally, but splits the portfolio across two stores and loses SQLite's transactional/query guarantees for the exact data that most needs them.
  - **Adopt Alembic / a full migration framework**: heavyweight; violates the dependency-minimal ethos (ADR-001) for a single append-only table.
- **Consequences**: "delete and re-ingest" is **no longer a valid whole-DB recovery strategy** — it is safe only for the cache tables; losing `crypto.db` loses recorded transactions. The migration engine is non-atomic across multiple pending migrations because `sqlite3.executescript()` implicitly commits (documented in `db.migrate`'s docstring and memory `sqlite-executescript-implicit-commit-breaks-atomicity`); this is safe only while migrations stay add-only. Backup guidance for `crypto.db` should now treat it as partially irreplaceable.

### ADR-009: Dashboard charts via a vendored uPlot blob — single offline HTML, still no framework (amends ADR-004)
- **Status**: Accepted
- **Date**: 2026-06-06
- **Context**: Cycle 2 (Epics 12–16) added a substantial decision layer — factors/signals, look-ahead-safe backtests, ledger NAV + realized/unrealized P/L, and portfolio risk (correlation/vol/beta/drawdown) — but **none of it has a human-facing surface**. `report/dashboard/` (then a single `dashboard.py`) imported only `shared/db`, `signals/ta`, `shared/paths` and rendered Cycle-1 visuals (price polylines, sparklines, an RSI strip) from hand-built SVG strings. Surfacing the new layer needs genuinely interactive time-series charts (a NAV curve, a backtest equity curve, a multi-coin risk panel), and ADR-004 already flagged the hand-rolled SVG approach as a "candidate maintenance surface" that "grows fiddly if the dashboard gains panels or interactivity." That cost is now being incurred. The question was whether to keep hand-rolling, or move to a frontend framework (React/Astro) or a served app (Django/Flask).
- **Decision**: Keep the **single self-contained offline `dashboard.html`** model from ADR-004 — no server, no build step, no npm, no CDN — but stop hand-rolling interactive charts. **Vendor [uPlot](https://github.com/leeoniya/uPlot)** (MIT, ~40KB minified, zero runtime dependencies, purpose-built for time-series) as a static `.js` asset committed to the repo (`report/dashboard/vendor/uplot.min.js`), and have the dashboard package inline it into a `<script>` tag at generation time. uPlot is **not** a Python dependency — it is a string Python writes into the output — so the **3-dep core (ADR-007) is untouched**. New panels (NAV, equity, risk, triggered signals) are added to `report/dashboard/panels.py`, with `report/dashboard/__init__.py` importing `portfolio/ledger`, `portfolio/risk`, `signals/factors`, `report/digest`, and `backtest/`. Hand-rolled SVG helpers may stay for trivial static visuals or be retired per-panel. Assets in `report/dashboard/vendor/` are resolved package-relative via `__file__`.
- **Alternatives Considered**:
  - **Keep 100% hand-rolled SVG**: zero new artifacts and total control, but hand-rolling axes/tooltips/zoom for multi-series charts is exactly the maintenance surface ADR-004 warned about; interactivity stays poor.
  - **React / Astro (SSG)**: rich component/chart ecosystem and can emit static files (offline survives), but introduces the Node toolchain (npm, `node_modules`, a build step, a second language) into a 3-dep Python repo — disproportionate for ~5 panels and a recurring CI cost.
  - **Django / Flask (live server)**: dynamic and real-time, but reintroduces a running server, routing, and an "is it up?"/attack-surface concern the local-first design deliberately rejects — for a single-user tool whose vision is an agent-native decision layer, not a hosted app.
- **Consequences**: The dashboard stays a portable, offline, shareable single file while gaining real interactive charts (zoom/tooltips/cursor) without a frontend toolchain. New cost: **one pinned vendored third-party file to keep current** — record uPlot's version + source URL next to the blob and bump it deliberately (it is shipped to users inside generated HTML, so license attribution and provenance matter). This supersedes ADR-004's "inline SVG only" mechanism for charts; ADR-004's *principles* (offline, no server, no framework, data baked in at generation time) are preserved unchanged.

---

## Cross-Cutting Concerns

### Logging
- **Framework**: none. Diagnostics are plain `print()` to stdout (e.g. `"rate limited (429), waiting 5s..."`, per-coin progress and `! …failed` warnings during ingest).
- **Levels / structured**: none / no. Output is human-readable console text, not structured logs.
- **Destination**: the terminal. Appropriate for an interactive single-user CLI; there is no log file or sink.

### Error Handling
- **Strategy**: two tiers. **Fatal, user-fixable** problems (missing/placeholder API key, missing `coins.local.json`, unknown coin, no data yet) raise `SystemExit` with an actionable message. **Transient, per-item** failures during ingest (a coin's price or OHLC fetch) are caught, printed as `! …failed`, and skipped so the run continues.
- **External faults**: `coingecko._get` retries HTTP 429 with exponential backoff; other non-2xx raise via `raise_for_status` and bubble up to the per-coin try/except in `cmd_ingest`.
- **User-facing**: messages tell the user the exact fix ("Copy config.example.json -> config.local.json…").

### Caching
- **The cache is the database.** SQLite *is* the cache layer: CoinGecko responses are persisted so `ta`, `report`, and `dashboard` never touch the network — they read `crypto.db`. There is no separate in-memory or distributed cache.
- **Invalidation**: re-running `ingest` refreshes the cache via idempotent upserts; `snapshots` append a new row each run, and the latest is read for live price/P/L.

### Configuration
- **Source**: two JSON files in the data directory — `config.local.json` (CoinGecko key + tier) and `coins.local.json` (coins, holdings, cost basis, vs-currency, stablecoin flags). Plus the env var `DOMDHI_CRYPTO_HOME` to relocate the data directory.
- **Secrets**: the API key lives only in `config.local.json`, git-ignored (and matched by the defense-in-depth `*.local.*` ignore). The repo ships `*.example.json` templates with placeholders.
- **Feature flags**: none. The closest thing is per-coin `"stable": true`, which skips history ingestion and TA for that coin.

### Observability
- For a local CLI, observability is the stdout the user reads while a command runs: progress lines, row counts (`"365 daily price rows"`), rate-limit notices, and per-coin warnings. There are no metrics, traces, or health checks — and none are warranted for this deployment model.

---

## Failure & Scaling Behavior

### Dependency failure modes
| Dependency | Failure | Behavior |
|------------|---------|----------|
| CoinGecko (rate limit) | HTTP 429 | Backoff `5·2^attempt`s, up to 4 tries, then `raise_for_status` → caught per-coin, printed, skipped. |
| CoinGecko (outage / 5xx / network) | non-2xx or exception | Raised by `_get`; in `ingest` caught per-coin (`! …fetch failed`) and the run continues; in a single-coin path it surfaces to the user. |
| Missing config / holdings | file absent / placeholder key | Fast `SystemExit` with a copy-the-example fix message. |
| No data yet (`ta`/`report`/`dashboard` before `ingest`) | empty query | `load_close_series` returns `None`; commands either `SystemExit` ("Run: domdhi-crypto ingest") or skip the coin. |
| Sparse/gappy history | missing daily rows | `load_close_series` reindexes to a continuous daily range and forward-fills `close`, so rolling windows stay calendar-correct. |
| Partial windows (e.g. <200 days for SMA200) | not enough data | Indicators return NaN; `analyze` omits SMA200 and dependent signals rather than fabricating values. |

### Bottlenecks & scale
- **The only bottleneck is CoinGecko's rate limit**, deliberately respected with a 2.0s inter-call pause and 429 backoff. Local compute (pandas over a few coins × ~365 rows) is negligible.
- **Scaling axis is "more coins,"** which scales ingest time linearly (one history + one OHLC call per non-stable coin, each followed by the pause). This is fine for a personal portfolio; it would become slow for hundreds of coins, but that is outside the tool's intent.
- **No horizontal scaling** exists or is needed — single process, single user, single SQLite file.

### Degradation
- Ingest **degrades gracefully**: a failure on one coin doesn't abort the others (per-coin try/except + per-coin commit). Analysis/render commands degrade by **skipping** coins with no data rather than erroring out wholesale, so a partially-populated DB still produces a useful report and dashboard.

### SLIs
- None defined or appropriate. Success is "the command exits 0 and writes the expected output."

---

## Development Standards

### Project Structure (canonical — this is where new code goes)

The layout follows the Vertical-Slice Architecture described in `docs/_slice-architecture.md`.

```
Domdhi.Crypto/
├── pyproject.toml              # PEP 621 metadata, deps, [project.scripts], pytest config
├── ruff.toml                   # lint/format config (line 110, py311, E/F/W/I/UP/B)
├── .pre-commit-config.yaml     # whitespace/yaml/toml hooks + ruff --fix
├── .github/workflows/ci.yml    # 3.11/3.12/3.13 matrix: ruff check + pytest
├── config.example.json         # API-key template (real one is config.local.json, git-ignored)
├── coins.example.json          # holdings template (real one is coins.local.json, git-ignored)
├── README.md  LICENSE  CHANGELOG.md
│
├── src/domdhi_crypto/          # engine package — organized into Vertical-Slice sub-packages
│   ├── __init__.py
│   ├── __main__.py             # `python -m domdhi_crypto` → cli.main
│   ├── cli.py                  # host / composition root (wires every slice)
│   │
│   ├── shared/                 # core infra — bedrock, imported by all slices
│   │   ├── __init__.py
│   │   ├── paths.py            # data-dir + filename resolver (leaf)
│   │   └── db.py               # SQLite layer + migrations (imports paths; uses pandas)
│   │
│   ├── ingest/                 # CoinGecko → SQLite acquisition
│   │   ├── __init__.py
│   │   └── coingecko.py        # HTTP client; tier host+header wiring; 429 backoff
│   │
│   ├── signals/                # edge layer: TA + factor substrate + effectiveness
│   │   ├── __init__.py
│   │   ├── ta.py               # hand-rolled RSI/MACD/Bollinger/ATR + signals (leaf)
│   │   ├── factors.py          # factor registry + safe AST evaluator + BUILTIN_FACTORS
│   │   └── effectiveness.py    # IC / ICIR factor edge measurement
│   │
│   ├── portfolio/              # NAV, P/L, risk
│   │   ├── __init__.py
│   │   ├── ledger.py           # NAV + average-cost realized/unrealized P/L
│   │   └── risk.py             # correlation / vol / beta / drawdown (pure leaf)
│   │
│   ├── agent/                  # agent-interface seam (consumed by domdhi_crypto_mcp)
│   │   ├── __init__.py
│   │   └── context.py          # JSON-safe snapshot: signals + position + factor menu
│   │
│   ├── backtest/               # look-ahead-safe event backtester (Epic 13)
│   │   ├── __init__.py         # frozen Bar/Order/Fill/Trade/BacktestResult contracts (leaf)
│   │   ├── data_provider.py    # look-ahead-safe bar feed
│   │   ├── virtual_account.py  # cash/position/equity/drawdown/P&L
│   │   ├── execution_simulator.py  # slippage + fees
│   │   ├── engine.py           # event loop (calls signals/factors.evaluate)
│   │   ├── attribution.py      # by-factor decomposition of a BacktestResult
│   │   └── arena.py            # multi-strategy universe harness (cortex vs B&H vs baseline)
│   │
│   └── report/                 # output layer: digest + dashboard
│       ├── __init__.py
│       ├── digest.py           # offline Markdown triggered-signal brief
│       └── dashboard/          # offline HTML builder — split into a package
│           ├── __init__.py     # build() orchestration entry point
│           ├── theme.py        # GitHub-dark palette constants
│           ├── charts.py       # SVG/uPlot chart toolkit
│           ├── panels.py       # data panels + panel registry
│           ├── scaffold.py     # page template (HTML skeleton)
│           └── vendor/         # vendored third-party assets, NOT Python deps (ADR-009)
│               ├── uplot.min.js    # pinned uPlot blob; inlined into dashboard.html
│               └── uplot.min.css   # uPlot stylesheet; inlined into dashboard.html
│
├── src/domdhi_crypto_mcp/      # agent layer — separate top-level package, one-way dep on engine
│   ├── __init__.py
│   ├── decision.py             # DECISION_SCHEMA + validate_decision + build_trigger_context
│   └── server.py               # FastMCP stdio server; lazy [mcp] import (ADR-007)
│
├── tests/                      # pytest unit tests, network mocked (329 total; 1 MCP test skips without the [mcp] extra)
│   ├── test_paths.py
│   ├── test_coingecko.py       # tier wiring + 429 backoff, network mocked
│   ├── test_db.py              # schema/upsert/idempotency/gap-fill/migrations against :memory:/temp db
│   ├── test_ta.py              # indicator math + signals
│   ├── test_factors.py         # registry + evaluator + builtin factors
│   ├── test_effectiveness.py   # IC / ICIR + look-ahead invariant
│   ├── test_backtest_types.py
│   ├── test_backtest_data_provider.py
│   ├── test_backtest_virtual_account.py
│   ├── test_backtest_execution_simulator.py
│   ├── test_backtest_engine.py
│   ├── test_backtest_attribution.py
│   ├── test_context.py
│   ├── test_decision.py
│   ├── test_mcp_server.py      # uses importorskip("mcp") + no-top-level-import guard
│   ├── test_digest.py
│   ├── test_ledger.py
│   ├── test_risk.py
│   └── test_cli.py
│
└── docs/                       # this document + planning docs
    └── _slice-architecture.md  # canonical layout: slice tree + dependency DAG + conventions

Where to add things:
  • a new indicator         → signals/ta.py  (pure function: Series in, Series out; NaN on partial window)
  • a new factor primitive  → signals/factors.py (register with _reg + metadata; pure numpy/pandas)
  • a new built-in factor   → signals/factors.py (append a BUILTIN_FACTORS dict — it's data, not code)
  • a new CLI subcommand    → cli.py (add a sub-parser + a cmd_* handler; wire the slice import here)
  • a new table / query     → shared/db.py  (cache table: idempotent upsert; source-of-truth change: add-only MIGRATION, ADR-008)
  • a new external endpoint → ingest/coingecko.py (return raw JSON; shape it in the caller)
  • a new dashboard panel   → report/dashboard/panels.py (build the HTML/SVG or uPlot config; bake data in; degrade to n/a, never crash)
  • a new portfolio metric  → portfolio/risk.py or portfolio/ledger.py (pure over the close series; NaN on under-window, never fabricate)
  • a new vendored asset    → report/dashboard/vendor/ (record version + source URL + license; resolved via __file__; ships inside generated HTML — ADR-009; never a Python dep)
  • a new slice             → a new sub-package under src/domdhi_crypto/; wire it from cli.py only; follow the DAG in _slice-architecture.md
  • a new file location     → shared/paths.py (never hard-code a path elsewhere)
  • tests                   → tests/test_<module>.py, mock the network
  • a new agent-layer module → domdhi_crypto_mcp/ only; imports from domdhi_crypto.* (one-way; never the reverse)
```

**Import convention**: always use deep, explicit imports — `from domdhi_crypto.<slice> import <module>`. Relative imports are permitted only for siblings within the same slice. `__init__.py` files hold only a docstring — they never re-export symbols.

### Coding Conventions (observed)
- **Strictly acyclic imports.** `shared/paths`, `signals/ta`, and `portfolio/risk` are leaves; `cli` is the apex; `domdhi_crypto_mcp` depends on the engine only (one-way). Never introduce a cycle; see `docs/_slice-architecture.md` for the full DAG.
- **Deep, explicit imports.** Always `from domdhi_crypto.<slice> import <module>` — never flatten the namespace through `__init__.py`. Relative imports only for siblings within a slice.
- **Idempotent writes only** in `shared/db.py` (`ON CONFLICT … DO UPDATE`/`DO NOTHING`).
- **Pure TA.** `signals/ta.py` imports nothing from the project; indicators take a Series and return Series; partial windows yield NaN, never fabricated numbers.
- **Paths through `shared/paths.py`.** No module hard-codes a filename or directory. Vendored assets in `report/dashboard/vendor/` are resolved via `__file__` (not `paths`).
- **Lazy network import.** `requests` is imported inside `CoinGecko.__init__` so offline commands don't load it.
- **Fail with a fix.** User-fixable errors `SystemExit` with the exact remediation; transient per-coin errors print and continue.
- **ruff is the definition of clean** (line-length 110, py311 target, `E/F/W/I/UP/B`); pre-commit auto-fixes on commit.

### Testing Strategy
| Level | Framework | Coverage Target | What's Tested |
|-------|-----------|-----------------|---------------|
| Unit | pytest | none formally set; 308 tests across all modules (1 MCP test skips without the `[mcp]` extra) | TA math/signals, factor registry + safe evaluator, IC/ICIR + look-ahead invariant, the look-ahead-safe `backtest/` package, agent context/decision/MCP, digest, ledger NAV + P/L, portfolio risk, and `db` schema/upsert/idempotency/gap-fill/**migrations** — all with the network mocked |
| Integration | — | — | None as a distinct layer. The DB tests exercise real SQLite (against `:memory:`/temp files), which gives integration-level confidence for the storage layer without external services. |
| E2E | — | — | None as mocked tests. `test_cli.py` exercises the CLI surface; a real-data end-to-end run against live CoinGecko is the planned Epic 19-S1 validation (documented run record, not a CI test). |

**Principle**: the network is always mocked (no test hits CoinGecko), and the database tests run against real SQLite. The test suite — not a type checker (ADR-006) — is the safety net for correctness.

---

## Risks & Candidate Maintenance Surfaces

*The user did not report any pain points; the tool was built in two sessions and is reported as working. The following are surfaces a future maintainer should watch, flagged here proactively — none is currently described as painful.*

1. **Hand-rolled TA owns its own correctness (ADR-001).** A bug in an indicator is the project's bug, and CoinGecko/standard-reference drift won't be caught by a library upgrade. Mitigated today by `tests/test_ta.py`.
2. **Tight CoinGecko coupling.** `ingest/coingecko.py` encodes v3 paths, tier headers, and response shapes; a CoinGecko API change (endpoint, field names, granularity rules) breaks ingest. The seam is clean (one module), so the blast radius is contained, but the dependency is hard.
3. **Hand-built HTML/SVG dashboard (ADR-004), now with a vendored uPlot blob (ADR-009).** Static visuals are still string-built SVG; interactive charts (NAV/equity/risk) go through a vendored `report/dashboard/vendor/uplot.min.js` inlined into the output. New watch item: the pinned uPlot blob is a third-party file shipped inside generated HTML — keep its version/source recorded (see `report/dashboard/vendor/README.md`) and bump it deliberately (provenance + license attribution).
4. **Partial source of truth (ADR-008 amends ADR-002/-003).** The DB is no longer a wholly regenerable cache: the user-entered `transactions` table cannot be re-fetched. Schema evolution now goes through `db.migrate()` (append-only migrations) so that data survives; "delete and re-ingest" recovers only the cache tables. The add-only migration discipline (no DROP/rewrite) and `crypto.db` backups are the load-bearing invariants to preserve.
5. **No static typing (ADR-006).** Type errors surface at runtime or via tests, not statically. Low risk while the codebase is small and single-author; reconsider if it grows or gains contributors.

---

## Related Documents
- PRD: [_project-requirements.md](_project-requirements.md) *(not yet present — this project began code-first)*
- UX Spec: [design/_project-design.md](design/_project-design.md) *(not yet present)*
- Epics: [todo/_backlog.md](todo/_backlog.md)
