# TODO: Epic 19 — "Alpha Arena for one"

| Attribute | Value |
|-----------|-------|
| **Status** | Specification Complete |
| **Author** | Dom |
| **Created** | 2026-06-07 |
| **Phase** | 9 — Prove It |
| **Source** | `docs/todo/_backlog.md` Epic 19 (FR-33, FR-34) |
| **Research** | `docs/.output/work/2026-06-07/epic19_alpha-arena/1101-research-codebase.md` |

---

## Executive Summary

Prove the cycle-2 decision cortex on real history, then paper-trade it against baselines.
Epic 19 splits into three narrow stories: a **network-mocked end-to-end pipeline validation**
test + a documented live-CoinGecko run record (E19-S1, FR-33), a **pure arena engine** that runs
the cortex strategy vs buy-and-hold + a rule baseline and reports relative performance + per-factor
attribution (E19-S2, FR-34), and the **`arena` CLI subcommand** that exposes it (E19-S3).

The arena is **thin orchestration** over the shipped `backtest.engine.run_backtest` +
`backtest.attribution.attribute_by_factor` — it adds no execution or look-ahead logic; the
look-ahead guard (NFR-C3-4/8) is inherited from the engine's time-gated provider, and buy-and-hold
is the closed-form `initial_cash * close / close.iloc[0]` (no future reads by construction).

---

## Dependency Graph

```
        Wave 1 (parallel — disjoint files)
        ┌──────────────────────────────┐
        │  E19-S1  pipeline e2e + run   │   E19-S2  arena.py core engine
        │          record (test+doc)    │           + baselines (module+test)
        └──────────────────────────────┘            │
              (validation gate, logical)            │ arena.py
                                                     ▼
                                          Wave 2
                                          ┌────────────────────────────┐
                                          │  E19-S3  arena CLI command  │
                                          │          (cli.py + test)    │
                                          └────────────────────────────┘
```

`E19-S2 → E19-S1` is declared **hard** in the backlog, but it is a *validation gate*, not a code
dependency — `arena.py` consumes only shipped modules and S1 produces a test + a doc that feed
nothing into S2. Their file sets are disjoint, so they run in parallel in Wave 1. **E19-S3 has a
real code dependency** on `arena.py`, so it waits for Wave 2.

---

## Phase 9: Prove It

**Goal:** Run the cortex on real data, then paper-trade it against baselines to measure edge.

---

### Epic E19: "Alpha Arena for one"

**Objective:** Validate on real history, then a local offline paper-trade arena vs baselines.
Reuses `backtest/` + `factors`/`decision`; no live-exchange calls.

---

* **Story E19-S1 (M): Real-data end-to-end validation + run record**
  * **As an** operator, **I want** the full pipeline exercised end-to-end with a per-stage
    non-degeneracy bar, plus a repeatable real-data run procedure, **So that** I know the cortex
    works outside mocked unit tests — not just that individual modules pass.
  * **AC:**
    * [x] A new `tests/test_pipeline_e2e.py` runs `ta.analyze → factors.evaluate (over BUILTIN_FACTORS) → engine.run_backtest → digest.build_digest` end-to-end over a **seeded realistic multi-coin DB** (network mocked, mirroring `tests/test_cli.py::factors_env`), with **no errors**.
    * [x] The test asserts the **FR-33 per-stage non-degeneracy bar**: each stage output is **non-empty**, dates are **monotonic increasing**, numeric values are **finite and not all-constant** (varying), and the backtest's `equity_curve` is **populated** (non-empty `pd.Series`).
    * [x] `docs/app/arena/_brief.md` documents a **short, repeatable live-CoinGecko run procedure** (`init → ingest → ta → factors → backtest → digest` on a small real coin set) and records the result of one run; **any stage that misses the bar is logged as a finding** in that doc.
    * [x] The doc states explicitly that the live run is an **operator step** (needs `config.local.json` API key + network) and that the automated guarantee is the mocked e2e test.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `tests/test_pipeline_e2e.py` — NEW: network-mocked end-to-end pipeline test + non-degeneracy assertions.
    * `docs/app/arena/_brief.md` — NEW: module brief + live-run procedure + recorded result + any findings.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap. *(Contingency: if the e2e test surfaces a real bug in a pipeline module, the dev fixes ≤1 source file in-scope and notes it as a finding — still within cap.)*
  * **Research notes:** Mirror `factors_env` (test_cli.py:53) for DB seeding — `db.init_db` + `db.upsert_prices` on a `tmp_path` DB, `monkeypatch` `cli.load_coins`/`cli.db.connect`. Use ≥2 non-stable coins with ≥200 daily bars (so SMA200 + factors are non-trivial) and a varying (non-flat) close series so "not all-constant" holds. `digest.build_digest(coins_cfg, *, conn)` is the pure entry. `db.load_close_series` returns `None` on no data — seed enough rows. Do NOT call live CoinGecko in the test. `docs/app/` is empty today — this creates the first module brief.

---

* **Story E19-S2 (M): Local paper-trade arena engine + baselines**
  * **As an** operator, **I want** the cortex paper-traded vs buy-and-hold (+ a rule baseline) over
    real history with per-factor attribution, **So that** I can prove edge before risking a cent.
  * **AC:**
    * [x] A new pure `arena.py` exposes a `run_arena(frame, *, cortex_rules, initial_cash=10_000.0, slippage_bps=0.0, fee_rate=0.0)` (or equivalent) that returns, for the **cortex strategy** and **each baseline**, an **equity curve** (`pd.Series`) and a **summary** dict, plus **relative performance** of the cortex vs each baseline (e.g. total-return delta).
    * [x] Baselines include **buy-and-hold** (closed-form `initial_cash * close / close.iloc[0]`) and **≥1 rule strategy** (a `SignalRule` baseline, e.g. an SMA/momentum regime rule from a `BUILTIN_FACTORS` expression) — both over the same frame as the cortex.
    * [x] **Per-factor attribution** for the cortex strategy is reported via `attribution.attribute_by_factor`.
    * [x] **Look-ahead guard holds:** the cortex/rule strategies run through `engine.run_backtest` (reusing the time-gated provider; no future-bar reads), and a test asserts **truncation-invariance** — running the arena on `frame.loc[:T]` yields a result consistent with the full-frame run up to `T` (mirrors the engine's existing look-ahead test). Buy-and-hold is future-free by construction.
    * [x] `arena.py` imports **no** `cli`/`dashboard` (stays a pure leaf); imports only `backtest.{engine,attribution}`, `factors`, and pandas/stdlib.
  * **Estimate:** M
  * **Dependencies:** E19-S1 (validation gate — logical; no code dependency, runs parallel in Wave 1)
  * **Files:**
    * `src/domdhi_crypto/arena.py` — NEW: pure arena engine + baseline builders + result type.
    * `tests/test_arena.py` — NEW: cortex-vs-baselines equity/summary, attribution presence, look-ahead truncation-invariance, buy-and-hold closed form.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap.
  * **Research notes:** `engine.run_backtest(frame, [SignalRule], *, initial_cash, slippage_bps, fee_rate) -> BacktestResult` with `.equity_curve`/`.summary`/`.trades`; `SignalRule(factor_name, expression, entry_threshold, exit_threshold)` — enter when factor > entry, exit when factor < exit. `attribution.attribute_by_factor(result) -> {factor: {n_trades,total_return,mean_return,win_rate}}`. Cortex rule expressions come from `factors.BUILTIN_FACTORS` (`{f["name"]: f["expression"]}`). Keep `arena.py` a **pure leaf** (frames passed in, no `db` import) like `risk.py`/`backtest/` — the IO/loading lives in the S3 CLI handler. Reuse the engine's truncation-invariance test approach from `tests/test_backtest_engine.py`. `BacktestResult` is `eq=False` — compare `.summary` / `.equity_curve` values, never whole instances.

---

* **Story E19-S3 (S): `arena` CLI subcommand**
  * **As an** operator, **I want** a `domdhi-crypto arena <symbol>` command, **So that** I can run
    the arena from the CLI like `backtest`, against my ingested data.
  * **AC:**
    * [x] `cli.py` gains a `cmd_arena(args)` handler registered as the `arena` subcommand via `sub.add_parser("arena")` + `set_defaults(func=cmd_arena)`, templated on `cmd_backtest`.
    * [x] It loads the series via `_load_series_or_exit(symbol)` (inherits stablecoin/no-data/short-series guards), runs `arena.run_arena`, and **prints** the cortex equity summary vs each baseline (relative performance) + the per-factor attribution table.
    * [x] Flags mirror `backtest` where sensible (`--factor`, `--entry`, `--exit`, `--cash`, `--slippage-bps`, `--fee-rate`) with the same boundary guards (`--cash > 0`, `--slippage-bps`/`--fee-rate >= 0`, unknown-factor → `SystemExit` listing how to find names).
    * [x] New tests in `tests/test_cli.py` cover: `arena` is registered, a happy-path run prints the cortex-vs-baseline summary + attribution, unknown symbol/factor and stablecoin/no-data each `SystemExit` (reuse the `factors_env` fixture).
    * [x] The architecture doc's CLI table row for `arena` (currently marked *planned, not yet implemented*) is updated to reflect it shipping.
  * **Estimate:** S
  * **Dependencies:** E19-S2 (hard — calls `arena.run_arena`)
  * **Files:**
    * `src/domdhi_crypto/cli.py` — MODIFY: add `cmd_arena` + `arena` subparser; import `arena`.
    * `tests/test_cli.py` — MODIFY: add arena CLI tests (reuse `factors_env`).
  * **Agent budget:** 2 modified, 0 created — within ≤5/≤2 cap. *(Optional: update the `arena` row in `docs/_project-architecture.md`; if done, that's 3 modified — still within cap.)*
  * **Research notes:** Template is `cmd_backtest` (cli.py:274) + its registration (cli.py:345). `expr_by_name = {f["name"]: f["expression"] for f in factors.BUILTIN_FACTORS}` + unknown-factor `SystemExit` is the guard to copy. `_load_series_or_exit(symbol)` returns `(coin_dict, series_frame)` and already rejects stablecoins/no-data. Use the `fmt(...)` print helpers already in `cli.py`. CLI tests live in `tests/test_cli.py` via the `_run(monkeypatch, *argv)` helper + `factors_env` fixture (BTC has data, DOGE no-data, USDT stable).

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|--------------|
| E19-S1 | Real-data end-to-end validation + run record | M | 1 | [x] | None |
| E19-S2 | Local paper-trade arena engine + baselines | M | 1 | [x] | E19-S1 (logical gate) |
| E19-S3 | `arena` CLI subcommand | S | 2 | [x] | E19-S2 (hard) |

**Total: 3 stories. Estimated: ~4.25 hours. — ✅ ALL DONE (2026-06-07)**

---

## Execution Log

- **2026-06-07 — Wave 1 (E19-S1, E19-S2):** Parallel dispatch. E19-S2 → `arena.py`
  (pure leaf: `run_arena` orchestrates `engine.run_backtest` + `attribution`; closed-form
  buy-and-hold; relative perf) passing the Main-authored `tests/test_arena.py` (8 tests).
  E19-S1 → `tests/test_pipeline_e2e.py` (10 tests, network-mocked ta→factors→backtest→digest
  with FR-33 non-degeneracy assertions) + `docs/app/arena/_brief.md` (first module brief;
  live-run procedure, PENDING-OPERATOR record). Gate 347/347. Code review: DONE_WITH_CONCERNS,
  0 CRITICAL/MAJOR; MINOR-1 (digest stage under-asserted) fixed — now asserts
  `## Triggered Signals` reaches the final stage. Doc coins-file location corrected.
- **2026-06-07 — Wave 2 (E19-S3):** Main-Agent-direct. Added `cmd_arena` + `arena` subparser to
  `cli.py` (templated on `cmd_backtest`; `--factor`/`--entry`/`--exit`/`--baseline-factor`/`--cash`/
  `--slippage-bps`/`--fee-rate`, default cortex `rsi_centered` vs baseline `price_vs_sma50`),
  prints cortex-vs-baselines + relative perf + by-factor attribution. 9 CLI tests in `tests/test_cli.py`
  (reuse `factors_env`); architecture-doc CLI row flipped planned→shipped. Gate 357/357.

---

## Wave Plan

**Shape:** file-overlap partitioned — three stories on a linear logical chain with **disjoint file
ownership**; the only hard code dependency (S3 → S2 via `arena.py`) forces exactly one barrier.
S1 and S2 own non-overlapping files and run in parallel in Wave 1 (S2's backlog dep on S1 is a
validation gate, not a code dependency — see Dependency Graph).

### Wave 1 — Validation + arena core (parallel, disjoint files)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E19-S1 | general-purpose | `tests/test_pipeline_e2e.py`, `docs/app/arena/_brief.md` | 0/2 | Yes (e2e assertions ARE the QA) |
| E19-S2 | general-purpose | `src/domdhi_crypto/arena.py`, `tests/test_arena.py` | 0/2 | Yes |

### Wave 2 — CLI surface (depends on Wave 1: S2's `arena.py`)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E19-S3 | general-purpose | `src/domdhi_crypto/cli.py`, `tests/test_cli.py` | 2/0 | Yes |

### Shared Hotspot Files
- **None.** All three stories own disjoint file sets. `cli.py` is touched only by S3; `arena.py` only by S2; the e2e test + run-record doc only by S1.

### Critical Path & Parallel Workstreams (REQUIRED)
- **Critical path:** E19-S2 → E19-S3 — ~M + S ≈ 2.75 h. This is the floor; S1 runs alongside and does not extend it.
- **Parallel workstreams:** Wave 1 is two independent chains — `{S1: e2e+doc}` ∥ `{S2: arena core}` — disjoint files, no shared state.
- **Max concurrent agents:** 2 (Wave 1).
- **Bottleneck:** E19-S2 (`arena.py`) — it adds the `run_arena` interface that S3's CLI command consumes. If it slips, S3 slips. S1 is off the critical path entirely.

---

## Key Findings from Research

1. **The arena is thin wiring, not a reimplementation** — `run_arena` orchestrates the shipped `engine.run_backtest` + `attribution.attribute_by_factor`; buy-and-hold is closed-form `initial_cash * close / close.iloc[0]`. This is what makes E19-S2 an M, not the backlog's L. *(`backtest/engine.py`, `backtest/attribution.py`)*
2. **Look-ahead safety is inherited, not built** — every strategy runs through the engine's time-gated provider (`frame.loc[:T]` only), so NFR-C3-4/8 holds for free; the arena's guard test is a truncation-invariance assertion, not new gating logic. *(`tests/test_backtest_engine.py`)*
3. **E19-S1's live run is an operator step `/run-todo` cannot perform** — no API key/network in the dev/CI context. The automated deliverable is a network-mocked e2e test (mirroring `test_cli.py::factors_env`); the live-CoinGecko run is a documented, repeatable procedure + recorded result in `docs/app/arena/_brief.md`. *(`tests/test_cli.py:53`)*
4. **`cmd_backtest` is the exact CLI template** — flag guards, `expr_by_name` factor lookup + unknown-factor `SystemExit`, `_load_series_or_exit` loading, and `fmt(...)` table printing all transfer directly to `cmd_arena`. *(`cli.py:274`, `:345`)*
5. **`docs/app/` is empty** — E19-S1 creates the first module brief (`docs/app/arena/_brief.md`), establishing the `app/{module}/_brief.md` convention for this project.
