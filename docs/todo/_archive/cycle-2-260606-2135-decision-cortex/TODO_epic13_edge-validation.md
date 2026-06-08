# TODO: Epic 13 — Edge Validation

| Attribute | Value |
|-----------|-------|
| **Status** | Specification Complete |
| **Author** | Dom |
| **Created** | 2026-06-06 |
| **Epic** | E13 — Edge Validation (Phase 5, Cycle 2 Decision Cortex) |
| **Backlog** | [docs/todo/_backlog.md](_backlog.md) — Epic 13 |

---

## Executive Summary

Epic 13 turns the factor substrate (Epic 12) into measured edge: it answers "does this factor predict?" (IC/ICIR) and "would this strategy have actually made money without cheating?" (a look-ahead-safe backtester), then explains outcomes by factor (attribution). Three new compute leaves — `effectiveness.py`, the `backtest/` package, and `backtest/attribution.py` — plus one new `cli.py` `factors` subcommand. Every module consumes `factors.evaluate` + `BUILTIN_FACTORS` and `db.load_close_series`; nothing touches the network.

**Load-bearing scope decision (from research):** the backtester's price source is `db.load_close_series` — a daily, gap-filled, `["close", "volume"]` frame. `db.load_ohlc` is a *different time base* (epoch-ms, sub-daily candles, no volume) and cannot be joined without the deferred unified-OHLCV loader (E12-S4/Epic 16). The backtester therefore operates on **close+volume daily bars only**; high/low-dependent execution (intrabar stops) is out of scope for this epic.

---

## Dependency Graph

```
  Effectiveness track            Backtest track
  ───────────────────            ──────────────
  E13-S1 (effectiveness)         E13-S3 (scaffold + shared types)
      │                              │
      ▼                       ┌──────┼──────┐
  E13-S2 (factors CLI)        ▼      ▼      ▼
                           E13-S4  E13-S5  E13-S6
                          (data   (virtual (exec
                           prov.)  acct)    sim)
                              └──────┼──────┘
                                     ▼
                                 E13-S7 (engine)
                                     │
                                     ▼
                                 E13-S8 (attribution)

  Wave 1: S1 ∥ S3
  Wave 2: S2 ∥ S4 ∥ S5 ∥ S6   (S2 needs S1; S4/S5/S6 need S3)
  Wave 3: S7                   (needs S4, S5, S6)
  Wave 4: S8                   (needs S7)
```

---

## Phase 5: Substrate & Edge Validation (the spine)

**Goal:** Measure whether factors predict (IC/ICIR) and backtest strategies honestly (no look-ahead), with outcomes explainable by factor.

---

### Epic E13: Edge Validation

**Objective:** Add `effectiveness.py` (IC/ICIR), the `backtest/` package (look-ahead-safe event backtester), and by-factor attribution — all pure leaves over the Epic-12 substrate.

---

* **Story E13-S1 (M): IC / ICIR factor effectiveness**
  * **As a** holder, **I want** each factor scored by IC/ICIR against forward returns, **So that** I know which signals actually predict.
  * **AC:**
    * [x] `effectiveness.py` exposes a function that, given a factor Series and a close Series, computes **Information Coefficient (IC)** as the Spearman rank correlation between the factor value at time *t* and the *n*-period **forward** return — forward return is `close.shift(-n)` based, so the last *n* rows are NaN and never filled.
    * [x] IC matches a hand-computed rank-correlation reference (computed independently in the test) within `1e-6`.
    * [x] **ICIR** = mean(rolling IC) / std(rolling IC) over a configurable window. The rolling std uses `min_periods=2` (a **documented exception** to the project's default `min_periods=window` NaN convention, because the IC series is already sparse) → ICIR is NaN until ≥ 2 defined IC points exist, never fabricated. State this exception in the function docstring.
    * [x] **Look-ahead sanity guard (deterministic):** a pure-noise factor built as `pd.Series(np.random.default_rng(42).standard_normal(N), index=close.index)` scores IC ≈ 0 (|IC| < 0.1) against the forward return; a perfectly-aligned future factor (the forward return itself, as the factor) scores IC ≈ 1 (|IC| > 0.99) — both asserted with the fixed seed `42`, proving the forward-return alignment is correct and the test is not flaky.
    * [x] A scoring entry point takes a list of factor dicts (the `BUILTIN_FACTORS` shape: `{name, expression, ...}`), evaluates each via `factors.evaluate(expr, frame)`, and returns per-factor `{name, ic, icir}` ranked by ICIR descending. Factors that raise on evaluation (e.g. unknown column) are reported with `ic=NaN`, not crashed on.
  * **Estimate:** M
  * **Dependencies:** None (E12-S2 `factors.evaluate` already shipped)
  * **Files:**
    * `src/domdhi_crypto/effectiveness.py` — NEW. IC/ICIR math + a `score_factors(frame, factors, horizon, ...)` entry point. Reuses `factors` primitives conceptually (`.rank(pct=True)` + `.corr()` for Spearman — no scipy).
    * `tests/test_effectiveness.py` — NEW. Reference-value IC test, ICIR test, the look-ahead sanity guard (noise→0, aligned→1), NaN-on-partial-window test, and a `score_factors` ranking test over a small synthetic frame.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** `db.load_close_series(conn, coin_id)` returns a daily `DatetimeIndex` frame with `["close","volume"]` (or `None`). Forward return = `close.pct_change(n).shift(-n)` OR `np.log(close.shift(-n)/close)` — pick pct for IC (rank-invariant either way). Spearman = `a.rank(pct=True).corr(b.rank(pct=True))` (pandas `.corr` default Pearson on ranks = Spearman). Reusable `factors.py` primitives: `RANK` (`_rank` L254), `TS_CORR` (`_ts_corr` L207), `LOG_RETURN` (`_log_return` L233), `PCT_CHANGE` (`_pct_change` L241). NaN convention: `.rolling(w)` with default `min_periods` yields NaN on partial windows — do not override. Test idiom: `np.allclose(..., equal_nan=True)` for Series, `pytest.approx` for scalars; synthetic close = `np.cumsum(np.sin(np.arange(N)/5)+np.cos(np.arange(N)/3))+100` (strictly positive, non-monotonic). **Pure leaf:** imports `factors` (+ numpy/pandas) only — no `db` needed (caller passes the frame).

---

* **Story E13-S2 (S): `factors` CLI subcommand (IC/ICIR report)**
  * **As a** holder, **I want** a `factors` CLI command that prints each built-in factor's IC/ICIR ranked, **So that** I can see which signals predict from the terminal.
  * **AC:**
    * [x] `domdhi-crypto factors <symbol>` resolves the symbol via the existing `_resolve` helper, loads its close series via `db.load_close_series`, scores `BUILTIN_FACTORS` through `effectiveness.score_factors`, and prints a fixed-width ranked table (factor name, category, IC, ICIR) sorted by ICIR descending.
    * [x] Floats render via the existing `fmt(x, d)` helper (`"n/a"` for None/NaN); the table matches the `report` command's column style (header + `-`-rule separator).
    * [x] An optional `--horizon N` flag (default e.g. 5) sets the forward-return horizon; an optional `--top N` limits rows.
    * [x] No data for the symbol (`load_close_series` → None) raises `SystemExit` with the existing "Run: domdhi-crypto ingest" style fix-it message; unknown symbol raises `SystemExit` via `_resolve`'s existing path.
    * [x] `tests/test_cli.py` gains coverage: the sub-parser registers `factors` with `func=cmd_factors`, and `cmd_factors` on a populated in-memory DB prints a table containing a known factor name (captured via `capsys`).
  * **Estimate:** S
  * **Dependencies:** E13-S1
  * **Files:**
    * `src/domdhi_crypto/cli.py` — MODIFIED. Add `from . import effectiveness`; add a `pf = sub.add_parser("factors")` block in `main()` with `--horizon`/`--top` args and `set_defaults(func=cmd_factors)`; add `def cmd_factors(args):` above `main()`.
    * `tests/test_cli.py` — MODIFIED. Add `cmd_factors` registration + output tests (first `cmd_*` handler coverage in this file).
  * **Agent budget:** 2 modified, 0 created — within ≤5/≤2 cap
  * **Research notes:** Subcommand pattern is uniform: `sub.add_parser("name").set_defaults(func=cmd_name)` then `args.func(args)` dispatches. Reuse `_resolve(args.symbol, coins)` (id-or-symbol), `load_coins()`, and `fmt(x, d)` (L39–41). Output Pattern B (the `report` table): header with `{col:<N}`/`{col:>N}` f-strings + a 78-char `-` rule. `test_cli.py` currently tests only `_resolve`/`_version` — no `cmd_*` coverage exists yet, so add a populated-DB fixture mirroring `test_db.py`'s `db.init_db(tmp_path/"x.db")` + `db.connect(path)` pattern and upsert a few price rows.

---

* **Story E13-S3 (S): Backtest package scaffold + shared types**
  * **As a** maintainer, **I want** a `backtest/` package with the shared dataclasses every backtest module consumes, **So that** the engine, account, simulator, and attribution share one typed contract.
  * **AC:**
    * [x] `src/domdhi_crypto/backtest/__init__.py` defines the shared, frozen dataclasses used across the package with these **exact field names** (the cross-module contract — S4–S8 reference them verbatim):
      * `Bar(timestamp: pd.Timestamp, close: float, volume: float)`
      * `Order(timestamp: pd.Timestamp, side: str, notional: float)` — `side` is `"buy"` or `"sell"`.
      * `Fill(timestamp: pd.Timestamp, price: float, fee: float, side: str)` — `price` is post-slippage.
      * `Trade(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp, realized_return: float, triggering_factor: str)` — `triggering_factor` is the factor `name` whose signal opened the trade (set by the engine, read by attribution).
      * `BacktestResult(trades: list[Trade], summary: dict)` — `summary` carries at least `total_return` (equity-curve, includes unrealized), `total_realized_return` (sum of closed-trade returns), `win_rate`, `max_drawdown`.
    * [x] The module carries a prose docstring in the house style (purpose, ADR-001 note, "deliberate leaf over `db` + numpy/pandas only", import-DAG position) and uses the 79-char `# ---- #` section dividers.
    * [x] Dataclasses are `@dataclass(frozen=True)`; no behavior beyond simple derived helpers (e.g. `Trade.holding_period`). No imports of sibling backtest modules (this is the leaf of the package's internal graph).
    * [x] `tests/test_backtest_types.py` constructs each dataclass, asserts immutability (frozen → `FrozenInstanceError` on assignment) and any derived helper.
  * **Estimate:** S
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/backtest/__init__.py` — NEW. Package marker + shared frozen dataclasses (the cross-module contract).
    * `tests/test_backtest_types.py` — NEW. Construction + immutability + derived-helper tests.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** This is the bottleneck story — every other backtest module imports these types, so its field names are a hard contract. Mirror the `FactorFunction` frozen-dataclass style already in `factors.py` (`@dataclass(frozen=True)`, line 39). Keep it pure: stdlib `dataclasses` + typing only; no `db`/numpy needed here. House docstring + divider style per `ta.py`/`factors.py` headers. Timestamps follow `load_close_series`' daily `DatetimeIndex` (use `pd.Timestamp` or the index label type).

---

* **Story E13-S4 (M): Look-ahead-safe data provider**
  * **As a** holder, **I want** a bar feed that at event time *T* can never return a bar with timestamp > *T*, **So that** the backtest's reported edge is real, not leaked.
  * **AC:**
    * [x] `data_provider.py` wraps a `db.load_close_series` frame (close+volume daily) and serves bars in ascending time order as `Bar` objects.
    * [x] At any cursor/event time *T*, the provider's "history up to *T*" API returns only bars with `timestamp <= T` — a **look-ahead guard test** asserts that no returned bar has `ts > T` for several *T* values, and that requesting a future bar raises or returns None rather than leaking it.
    * [x] A forward-return / "next bar" accessor used for settlement returns NaN (or None) when the next bar does not exist yet (end of series) — never a fabricated value.
    * [x] Iteration is deterministic across re-runs (stable ordering by the daily index; no reliance on dict ordering or randomness).
  * **Estimate:** M
  * **Dependencies:** E13-S3
  * **Files:**
    * `src/domdhi_crypto/backtest/data_provider.py` — NEW. Look-ahead-safe bar iterator/cursor over a close+volume frame, yielding `Bar` (from `__init__`).
    * `tests/test_backtest_data_provider.py` — NEW. Look-ahead guard (no `ts > T` ever returned), end-of-series NaN/None, deterministic ordering.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** Price source is **`load_close_series` only** (daily `DatetimeIndex`, ascending, gap-filled close, NaN volume on synthetic gaps) — NOT `load_ohlc` (epoch-ms, sub-daily, different time base; cannot be joined this epoch). The index is already sorted ascending (`db` does `ORDER BY date`), so the look-ahead guard is "slice index ≤ T". `.shift(-1)` gives the next bar and NaN-pads the tail — that NaN tail *is* the natural end-of-series guard; treat NaN-labeled next-bar as "not yet settled" and skip. Imports `backtest` shared types + numpy/pandas only (and `db` types via the passed-in frame — accept the frame as a constructor arg, don't import `db`, to stay a leaf). Determinism: no `Math.random`/`set` ordering.

---

* **Story E13-S5 (M): Virtual account (positions, cash, P/L)**
  * **As a** holder, **I want** a virtual account that tracks cash, position, and equity as fills are applied, **So that** the backtest reports honest returns and drawdown.
  * **AC:**
    * [x] `virtual_account.py` exposes an account that starts with a configurable cash balance, applies `Fill`s (buy reduces cash by notional + fee and increases position; sell does the inverse), and exposes current `cash`, `position`, and `equity(mark_price)` (= cash + position × mark).
    * [x] An explicit `mark(timestamp, price)` method appends `(timestamp, equity(price))` to the equity curve; the engine (E13-S7) calls it once per bar so the curve has one point per bar (no auto-recording on `apply_fill` — marking is the caller's responsibility, defined here as the contract). An equity-curve accessor returns the recorded series, enabling **max drawdown** (max peak-to-trough decline) — asserted against a hand-computed reference.
    * [x] Realized P/L per closed position and aggregate realized/unrealized P/L are exposed and match a hand-computed multi-fill reference within `1e-6`.
    * [x] The account never goes to a fabricated state: selling more than held, or buying beyond cash, is either rejected or clamped per a documented rule (test asserts the chosen rule).
  * **Estimate:** M
  * **Dependencies:** E13-S3
  * **Files:**
    * `src/domdhi_crypto/backtest/virtual_account.py` — NEW. Cash/position/equity accounting + equity curve + drawdown + realized/unrealized P/L.
    * `tests/test_backtest_virtual_account.py` — NEW. Multi-fill P/L reference, equity-curve + max-drawdown reference, the over-sell/over-buy rule.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** Consumes `Fill`/`Trade` from `backtest.__init__`. Pure accounting — stdlib + numpy only, no `db`. **`mark(timestamp, price)` is the only way the equity curve grows** (the engine calls it every bar) — do not auto-record on `apply_fill`, or bars with no fill would be missing from the curve and drawdown would be wrong. Max drawdown reference idiom: running max of equity, `(equity - running_max)/running_max`, take the min. Match `ta.py` tolerance style (`< 1e-6` accumulated floats). Document the over-trade rule explicitly (reject vs clamp) since it's a behavioral contract the engine relies on.

---

* **Story E13-S6 (S): Execution simulator (slippage + fees)**
  * **As a** holder, **I want** orders converted to fills with modeled slippage and fees, **So that** backtest returns are net of realistic trading costs, not idealized.
  * **AC:**
    * [x] `execution_simulator.py` converts an `Order` + the executing `Bar` into a `Fill`: fill price = bar close adjusted by a configurable slippage (bps or fraction, applied adverse to order side — buys fill higher, sells lower), and fee = configurable rate × notional.
    * [x] Zero-slippage + zero-fee config reproduces the bar close exactly (asserted) — the cost model is additive and disable-able.
    * [x] Slippage direction is correct: a buy fills at `close × (1 + slip)`, a sell at `close × (1 − slip)` — asserted in both directions; fee is always a positive cost regardless of side.
    * [x] Deterministic: same order + bar + config → identical fill across re-runs (no randomness).
  * **Estimate:** S
  * **Dependencies:** E13-S3
  * **Files:**
    * `src/domdhi_crypto/backtest/execution_simulator.py` — NEW. `Order` + `Bar` → `Fill` with slippage + fee.
    * `tests/test_backtest_execution_simulator.py` — NEW. Zero-cost identity, slippage direction (buy up / sell down), fee positivity, determinism.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** Consumes `Order`/`Fill`/`Bar` from `backtest.__init__`. Pure function — numpy/stdlib only, no `db`, no randomness (determinism AC). Slippage adverse-to-side is the standard convention. Keep config as explicit params (slippage_bps, fee_rate) defaulting to small realistic values; document units.

---

* **Story E13-S7 (L): Look-ahead-safe event backtest engine**
  * **As a** holder, **I want** an engine that walks bars forward, generates orders from a factor signal, simulates execution, and reports trade records + stats, **So that** I get an honest, reproducible edge measurement.
  * **AC:**
    * [x] `engine.py` runs an event loop over `data_provider` bars: at each bar *T* it may only use information available at *T* (factor values computed on the close-up-to-*T* frame — **no future bars**), emits `Order`s per a simple, injectable signal rule (e.g. factor crosses a threshold), routes them through `execution_simulator`, updates the `virtual_account`, and calls `account.mark(T, bar.close)` once per bar so the equity curve has one point per bar.
    * [x] Each opened `Trade` records the `name` of the factor whose signal opened it in `Trade.triggering_factor` (the field defined in E13-S3) — this is what attribution (E13-S8) groups on.
    * [x] **All open positions are closed at the final bar** (a forced exit at the last bar's close) so that `total_realized_return` accounts for every trade and reconciles with attribution; document this end-of-run flatten.
    * [x] **Look-ahead guard (integration):** a test proves the engine's decision at *T* is identical whether or not bars after *T* exist in the frame (truncating the future cannot change a past decision) — the canonical no-leak assertion.
    * [x] Returns a `BacktestResult` whose `summary` carries both `total_return` (from the equity curve, includes any unrealized PnL) and `total_realized_return` (sum of closed-trade `realized_return`), plus `win_rate` and `max_drawdown` — all net of the simulator's slippage/fees, each matching a hand-computed reference on a small deterministic scenario. (With end-of-run flatten, `total_realized_return` reconciles to attribution; see E13-S8.)
    * [x] **Deterministic across re-runs:** running the same engine on the same frame + config twice yields byte-identical `BacktestResult` (trade list + stats).
  * **Estimate:** L
  * **Dependencies:** E13-S4, E13-S5, E13-S6
  * **Files:**
    * `src/domdhi_crypto/backtest/engine.py` — NEW. Event loop wiring data_provider → signal → execution_simulator → virtual_account; returns `BacktestResult`.
    * `tests/test_backtest_engine.py` — NEW. Truncation-invariance look-ahead guard, stats reference (return/win-rate/drawdown), determinism (run twice → identical).
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** Integrates all three Wave-2 backtest modules + the shared types. Signal rule should be injectable (a callable factor-string + threshold) so attribution (S8) can tag each trade with its triggering factor. Factor values at *T* come from `factors.evaluate(expr, frame.loc[:T])` — slice the frame to ≤ T before evaluating so rolling windows can't peek ahead (this is the engine-level look-ahead discipline; the truncation-invariance test enforces it). Stats: total return from the equity curve, win rate = winning trades / total, max drawdown from `virtual_account`. No randomness anywhere (determinism AC). Pure leaf over `db`-shaped frames passed in by the caller (the future `cli` backtest command or a test); does not import `db`.

---

* **Story E13-S8 (M): By-factor attribution**
  * **As a** holder, **I want** backtest outcomes decomposed by the factor that triggered each trade, **So that** wins and losses are explainable per signal.
  * **AC:**
    * [x] `attribution.py` takes a completed `BacktestResult` and returns per-factor contribution grouped by `Trade.triggering_factor`: number of trades, total/mean `realized_return`, and win rate.
    * [x] The sum of per-factor total realized returns reconciles to `BacktestResult.summary["total_realized_return"]` (the sum of closed-trade returns — **not** the equity-curve `total_return`, which includes unrealized PnL) within `1e-6` — no trade double-counted or dropped. Because E13-S7 flattens all positions at the final bar, every trade is closed and the reconciliation is exact.
    * [x] A factor that triggered no trades is either absent or reported with zeroed/NaN stats per a documented rule (test asserts it); an empty `BacktestResult` returns an empty attribution without error.
  * **Estimate:** M
  * **Dependencies:** E13-S7
  * **Files:**
    * `src/domdhi_crypto/backtest/attribution.py` — NEW. Group `BacktestResult.trades` by triggering factor → per-factor contribution.
    * `tests/test_backtest_attribution.py` — NEW. Reconciliation-to-aggregate test, no-trade-factor rule, empty-result edge.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap
  * **Research notes:** Consumes `BacktestResult`/`Trade` from `backtest.__init__`; group on `Trade.triggering_factor` (the exact field name pinned in E13-S3, set by the engine in E13-S7). Reconcile to `summary["total_realized_return"]` (NOT `total_return`). Pure grouping/aggregation — pandas `groupby` over the trade list or hand-rolled dict accumulation; no `db`. Reconciliation assertion is the integrity guard (sum of parts == whole); it is exact only because S7 flattens open positions at the final bar.

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|--------------|
| E13-S1 | IC / ICIR factor effectiveness | M | 1 | [x] | None |
| E13-S2 | `factors` CLI subcommand (IC/ICIR report) | S | 2 | [x] | E13-S1 |
| E13-S3 | Backtest package scaffold + shared types | S | 1 | [x] | None |
| E13-S4 | Look-ahead-safe data provider | M | 2 | [x] | E13-S3 |
| E13-S5 | Virtual account (positions, cash, P/L) | M | 2 | [x] | E13-S3 |
| E13-S6 | Execution simulator (slippage + fees) | S | 2 | [x] | E13-S3 |
| E13-S7 | Look-ahead-safe event backtest engine | L | 3 | [x] | E13-S4, E13-S5, E13-S6 |
| E13-S8 | By-factor attribution | M | 4 | [x] | E13-S7 |

**Total: 8 stories. Estimated: ~12–15 hours.**

---

## Wave Plan

**Shape:** file-overlap partitioned — Epic 13's stories form a real dependency DAG (package scaffold → leaf modules → integrating engine → attribution) that role-splitting (Tests/Code/Verify) would distort; each story is a self-contained module+test unit with zero file overlap within any wave. No single-hotspot file exists (per-module test files avoid a shared-test-file hotspot), so the single-hotspot collapse does not apply.

### Wave 1 — Independent foundations (depends on nothing)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E13-S1 | general-purpose | `effectiveness.py`, `tests/test_effectiveness.py` | 0/2 | Yes |
| E13-S3 | general-purpose | `backtest/__init__.py`, `tests/test_backtest_types.py` | 0/2 | No |

### Wave 2 — Leaf modules (depends on Wave 1)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E13-S2 | general-purpose | `cli.py`, `tests/test_cli.py` | 2/0 | Yes |
| E13-S4 | general-purpose | `backtest/data_provider.py`, `tests/test_backtest_data_provider.py` | 0/2 | Yes |
| E13-S5 | general-purpose | `backtest/virtual_account.py`, `tests/test_backtest_virtual_account.py` | 0/2 | Yes |
| E13-S6 | general-purpose | `backtest/execution_simulator.py`, `tests/test_backtest_execution_simulator.py` | 0/2 | No |

### Wave 3 — Integrating engine (depends on Wave 2: S4, S5, S6)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E13-S7 | general-purpose | `backtest/engine.py`, `tests/test_backtest_engine.py` | 0/2 | Yes |

### Wave 4 — Attribution (depends on Wave 3: S7)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E13-S8 | general-purpose | `backtest/attribution.py`, `tests/test_backtest_attribution.py` | 0/2 | Yes |

### Shared Hotspot Files
- **None.** Every story owns disjoint files. `cli.py`/`test_cli.py` (E13-S2) are touched by no other Epic-13 story. Per-module backtest test files (rather than one shared `test_backtest.py`) deliberately avoid a test-file hotspot so Wave 2's three backtest stories run fully parallel.

### Critical Path & Parallel Workstreams (REQUIRED)
- **Critical path:** E13-S3 → (E13-S4 ∥ E13-S5 ∥ E13-S6) → E13-S7 → E13-S8 — the backtest chain; ~4 waves, the wall-clock floor regardless of agent count (engine cannot integrate before its three collaborators exist).
- **Parallel workstreams:** two independent chains — **effectiveness/CLI** (S1 → S2) ∥ **backtest** (S3 → {S4,S5,S6} → S7 → S8). The effectiveness chain finishes in Wave 2; the backtest chain is the critical path.
- **Max concurrent agents:** 4 (Wave 2: S2, S4, S5, S6).
- **Bottleneck:** **E13-S3** (defines the shared `Bar`/`Order`/`Fill`/`Trade`/`BacktestResult` dataclasses every backtest module imports — its field names are a hard contract; if its shape is wrong, Wave 2–4 rework) and **E13-S7** (the engine integrates all three Wave-2 modules; if it slips, attribution slips).

---

## Execution Log

- **2026-06-06 — Wave 1 (E13-S1, E13-S3):** `effectiveness.py` (IC/ICIR + `score_factors`) and `backtest/__init__.py` (frozen `Bar`/`Order`/`Fill`/`Trade`/`BacktestResult` contract) landed. 20 new tests, gate green at 166/166. Code review (Opus) found 2 MAJOR, both fixed pre-commit: (1) `icir` returned `inf` on zero-variance IC and sorted a degenerate factor to the top of `score_factors` → now returns NaN (sorts last); (2) the no-fill forward-return-tail test was tautological → rewritten to assert IC equals the dropna reference AND differs from a zero-filled-tail counterfactual. Also narrowed `score_factors`' `except` to the `evaluate()` call so real IC bugs surface loudly.

- **2026-06-06 — Wave 2 (E13-S2, E13-S4, E13-S5, E13-S6):** the `factors` CLI command (+ `fmt` NaN→"n/a"), `backtest/data_provider.py` (look-ahead-safe bar feed), `backtest/virtual_account.py` (cash/position/equity/drawdown/P&L), and `backtest/execution_simulator.py` (slippage+fees) landed. 28 new tests, gate green at 197/197. Code review (Opus) found 2 MAJOR robustness bugs on edge paths, both fixed pre-commit: `DataProvider.bar_at` raised TypeError on a duplicate timestamp (now de-duped in `__init__`, keep=last); `VirtualAccount.max_drawdown` divided by zero on a zero-equity peak (now guarded). Added regression tests for unsorted/dup input and zero-peak drawdown. One lead test bug fixed too: the `factors_env` fixture monkeypatched `cli.db.connect` with a self-referential lambda (`cli.db` is the same module object as `db`) → infinite recursion; fixed by capturing the original `connect` first. Memories promoted: `constraints/pytest-monkeypatch-self-ref-lambda-recursion`, `constraints/pandas-loc-scalar-vs-series-on-dup-index`, `constraints/drawdown-divide-by-zero-on-zero-peak`.

- **2026-06-06 — Wave 3 (E13-S7):** `backtest/engine.py` — the look-ahead-safe event-loop engine (`run_backtest` + `SignalRule`) wiring DataProvider → factor signal on `frame.loc[:T]` → execution_simulator → virtual_account, with per-bar `mark()`, final-bar flatten, and net-of-cost `Trade.realized_return`. 9 tests, gate green at 206/206. Code review (Opus) found 1 CRITICAL + 2 MAJOR, all hidden behind the zero-cost happy path, all fixed pre-commit: (CRITICAL) all-in buy with `fee_rate>0` could overshoot cash by 1 ULP and abort the run — fixed with a loop stepping qty down against the actual cost sum (+ regression test with the reviewer's repro values); (MAJOR) a column-less factor expression returned a scalar → `.iloc[-1]` AttributeError crashed the run — now guarded with `hasattr(series,"iloc")`; (MAJOR) the truncation-invariance test truncated *after* the trade closed (trivially passing) — added a cut-between-entry-and-exit case asserting entry-decision invariance. Documented the deliberate same-bar entry+flatten semantic (suppressing final-bar entry would itself break truncation-invariance). Memory promoted: `constraints/allin-buy-sizing-float-overshoot`.

- **2026-06-06 — Wave 4 (E13-S8):** `backtest/attribution.py` — `attribute_by_factor` groups closed trades by `triggering_factor` into `{n_trades, total_return, mean_return, win_rate}`. 6 tests, gate green at 212/212. Code review (Opus) PASS with zero CRITICAL/MAJOR/MINOR — confirmed the per-factor totals are a true partition of the trade set (reconciles exactly to `summary["total_realized_return"]`), win_rate's strict `>0` matches the engine's definition, and division is always safe. **Epic 13 complete: all 8 stories shipped.**

## Key Findings from Research

1. **Backtester price source is `load_close_series`, not `load_ohlc`** — `load_ohlc(conn, coin_id)` returns an epoch-ms, sub-daily, no-volume frame on a *different time base* that cannot be joined to the daily close series without the deferred unified-OHLCV loader (E12-S4/Epic 16). The backtester operates on **close+volume daily bars only**; intrabar high/low execution is out of scope. (`docs/.output/work/2026-06-06/edge-validation-epic13/1333-research-codebase.md` §A)
2. **Forward returns via negative shift** — `close.pct_change(n).shift(-n)` (or `np.log(close.shift(-n)/close)`); the NaN tail is the natural look-ahead guard and must never be filled. This is the single most important correctness invariant in Epic 13. (research-patterns §2, §4)
3. **Reusable `factors.py` primitives** — `RANK` (L254), `TS_CORR` (L207), `LOG_RETURN` (L233), `PCT_CHANGE` (L241), `TS_RANK` (L196). Spearman rank-IC = `.rank(pct=True)` on both series then `.corr()` — no scipy needed. (research-patterns §3)
4. **CLI subcommand pattern is uniform** — `sub.add_parser("factors").set_defaults(func=cmd_factors)`; reuse `_resolve`, `load_coins`, `fmt(x,d)` (L39–41); output Pattern B = fixed-width table + 78-char `-` rule (the `report` style). `test_cli.py` has no `cmd_*` coverage yet — E13-S2 adds the first. (research-codebase §B)
5. **`evaluate(expr, frame)` requires a `["close","volume"]` frame** — exactly the `load_close_series` shape; `BUILTIN_FACTORS` is a `list[dict]` with `{name, expression, description, category}` (43 entries). Factors that need absent columns raise — effectiveness must catch and report `ic=NaN`, not crash. (research-codebase §C)
6. **House style is enforced by convention, not tooling** — multi-paragraph module docstrings with ADR-001 + import-DAG notes, 79-char `# ---- #` dividers, `@dataclass(frozen=True)`, NaN-on-partial-window, `np.allclose(equal_nan=True)` / `pytest.approx`, one-test-per-behavior with an independently-coded reference value. No mypy; ruff (line 110, E/F/W/I/UP/B) + pytest are the gate. (research-patterns §1, §6)
7. **Greenfield confirmed** — no existing `effectiveness.py`, `backtest/`, or related test files; `cli.py` is the only existing source file modified by the entire epic; the acyclic import graph holds (new modules accept frames as args rather than importing `db`, keeping them leaves). (research-codebase §E)
