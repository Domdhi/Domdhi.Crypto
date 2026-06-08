# TODO: Epic 12 — Signal Substrate

| Attribute | Value |
|-----------|-------|
| **Status** | Specification Complete |
| **Author** | Dom (via `/todo epic 12`) |
| **Created** | 2026-06-06 |
| **Parent** | [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md) · [_backlog.md](_backlog.md) |
| **Phase** | 5 — Substrate & Edge Validation |

---

## Executive Summary

Turn the existing hand-rolled indicators (`ta.py`) into a **declarative factor substrate**: a pure-numpy primitive registry, a safe expression evaluator, and a built-in factor library expressed as data. This is the cortex spine — Edge Validation (Epic 13) and the Agent Interface (Epic 14) consume it. **The whole epic is a linear chain on one new file (`factors.py`), so the three stories run as three serial waves — no parallelism is available (or faked).**

### Key Deliverables
- `factors.py` — a `FUNCTION_REGISTRY` of pure-numpy primitives with metadata (the agent's factor menu)
- A safe (no-`eval`, no new dependency) expression evaluator over that registry
- ≥40 built-in factors as declarative strings, ported from the Apache-2.0 HammerGPT set

---

## Dependency Graph

```
E12-S1 (registry + primitives)  ──►  E12-S2 (evaluator)  ──►  E12-S3 (built-in factors)
   [creates factors.py]              [adds evaluator to        [adds factor data to
   [extends ta.py]                    factors.py]               factors.py + NOTICE]

Single hotspot: factors.py (all 3 stories) · strictly linear · zero parallelism.
```

---

## Phase 5: Substrate & Edge Validation

**Goal:** A factor library whose predictive edge can later be measured (Epic 13).

---

### Epic 12: Signal Substrate

**Objective:** Factors-as-data over a pure-numpy primitive registry, honoring ADR-001 (no `pandas-ta`).

---

* **Story E12-S1 (Backend, L): Pure-numpy factor primitive registry** — `CRITICAL PATH` `BOTTLENECK`
  * **Dependencies:** None · **Unblocks:** E12-S2, E12-S3 (and all of Epic 13/14)
  * **Track:** A (substrate) · **Domain:** Backend · **Estimate:** L
  * **As a** quant-minded holder, **I want** a registry of TA + time-series + cross-section primitives in pure numpy/pandas, **So that** factors compute without `pandas-ta` and stay auditable.
  * **AC:**
    * [x] Primitives (MAs, momentum, trend, volatility, volume, time-series `DELAY`/`TS_SUM`/`TS_MEAN`/`TS_STD`/`TS_MAX`/`TS_MIN`/`TS_RANK`/`TS_CORR`/`TS_ARGMAX`/`TS_ARGMIN`/`DECAYLINEAR`/`LOG_RETURN`, cross-section `RANK`/`ZSCORE`/`NORMALIZE`, math) each match a reference value within tolerance.
    * [x] The registry exposes per-function metadata (signature, description, example, category).
    * [x] Import graph: numpy/pandas only; `pandas-ta` is absent (a test asserts it is not importable/used).
  * **Files:**
    * `src/domdhi_crypto/factors.py` — **new**; `FUNCTION_REGISTRY` + primitive implementations + `_reg()` metadata helper.
    * `src/domdhi_crypto/ta.py` — **modify**; reuse existing `rsi`/`macd`/`bollinger`/`atr`/`annualized_vol` (wrap, do not duplicate); export any helpers the registry needs.
    * `tests/test_factors.py` — **new**; reference-value tests for primitives + the no-`pandas-ta` guard.
  * **Agent budget:** 1 modified (`ta.py`), 2 created (`factors.py`, `tests/test_factors.py`) — within ≤5/≤2.
  * **Research notes:** `ta.py` already implements `rsi` (Wilder/EWM), `macd`, `bollinger` (+%B), `atr` (takes an **OHLC DataFrame**), `annualized_vol`, and `_f` (float coercion, NaN→None) — reuse these as the momentum/vol primitives rather than re-deriving. ADR-001 (memory `adr-001`, conf 1.0) is the hard constraint: **pure pandas/numpy, no `pandas-ta`** (it breaks numpy 2.x / py3.13 and would redden the 3.13 CI leg). Time-series ops (`DELAY`=shift, `TS_*`=rolling, `DECAYLINEAR`=linear-weighted rolling, `LOG_RETURN`=log diff) and cross-section (`ZSCORE`/`NORMALIZE`=rolling z-score) are all small pandas one-liners. Keep `factors.py` a **leaf** (imports numpy/pandas + `ta`, nothing else internal) to preserve the acyclic graph.

---

* **Story E12-S2 (Backend, M): Safe declarative factor expression evaluator**
  * **Dependencies:** E12-S1 · **Unblocks:** E12-S3, E13 (effectiveness/backtest), E14
  * **Track:** A · **Domain:** Backend · **Estimate:** M
  * **As a** holder, **I want** factors expressed as strings evaluated safely over the registry, **So that** adding a factor is data, not code.
  * **AC:**
    * [x] A valid factor string (e.g. `"(close-EMA(close,200))/close"`) evaluates to the correct series; partial windows surface as NaN (never fabricated).
    * [x] An invalid or malicious expression (attribute access, dunders, imports, arbitrary calls) is rejected safely — **no arbitrary code execution**.
    * [x] The evaluator operates on an OHLCV-style frame sourced from `db.load_close_series` (close+volume) — see the data-shape gotcha in research notes.
  * **Files:**
    * `src/domdhi_crypto/factors.py` — **modify**; add `evaluate(expr, frame)` using a restricted AST walk (stdlib `ast`) limited to registry function calls, column names, numeric literals, and arithmetic/comparison operators.
    * `tests/test_factors.py` — **modify**; valid-expression correctness + a battery of rejected-expression security cases.
  * **Agent budget:** 2 modified, 0 created — within cap.
  * **Research notes:** HammerGPT used `asteval` for this — **do not add that dependency** (keep dependency-light per the ADR-001 ethos). Prefer a small stdlib-`ast`-walking evaluator that whitelists only `ast.Call` to registry names + `ast.Name` columns + `ast.Num/Constant` + `BinOp`/`Compare`/`UnaryOp`. **Data-shape gotcha (load-bearing):** `db.load_close_series` returns a daily, gap-filled frame with **`close` + `volume` only**; `high`/`low`/`open` live in the *separate* `ohlc` table (`db.load_ohlc`) at candle granularity with a different index. So this evaluator's frame is close+volume; factors needing high/low (ADX, Aroon, CCI, Williams%R, ATR-ratio) are **deferred** until a unified daily-OHLCV loader exists — flag that as a follow-up (candidate E12-S4 / Epic 16 data work), do not silently emit wrong values.

---

* **Story E12-S3 (Backend, M): Built-in factor library (port HammerGPT set)**
  * **Dependencies:** E12-S2 · **Unblocks:** E13-S1 (IC/ICIR over the library), E14
  * **Track:** A · **Domain:** Backend · **Estimate:** M
  * **As a** holder, **I want** ≥40 built-in factors across categories, **So that** I start with a real library, not a blank slate.
  * **AC:**
    * [x] ≥40 factor strings + categories are loaded as **data** (not per-factor Python), re-homed onto E12-S1 primitives; Apache-2.0 attribution recorded in `NOTICE`.
    * [x] Each built-in factor evaluates without error on a populated DB (close+volume factors; high/low factors explicitly excluded per E12-S2 gotcha, with a noted reason).
  * **Files:**
    * `src/domdhi_crypto/factors.py` — **modify**; add the `BUILTIN_FACTORS` list (name, expression, description, category).
    * `NOTICE` — **new**; Apache-2.0 attribution for the ported HammerGPT factor definitions.
    * `tests/test_factors.py` — **modify**; assert ≥40 builtins load and every close/volume builtin evaluates without error.
  * **Agent budget:** 2 modified (`factors.py`, `tests`), 1 created (`NOTICE`) — within cap.
  * **Research notes:** Source set = HammerGPT `insert_builtin_expression_factors.py` (Apache-2.0). Port the trend/momentum/volatility/volume/statistical/composite **strings** verbatim where they use close/volume primitives; **skip or defer** the ones requiring high/low/open (per E12-S2 gotcha). Decide the project **license** before this lands (open question in the brief) — Apache-2.0 reuse needs a compatible/permissive license + `NOTICE`.

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|--------------|
| E12-S1 | Pure-numpy factor primitive registry | L | 1 | [x] | None |
| E12-S2 | Safe declarative factor expression evaluator | M | 2 | [x] | E12-S1 |
| E12-S3 | Built-in factor library (port HammerGPT set) | M | 3 | [x] | E12-S2 |

**Total: 3 stories. Estimated: ~5–7 hours.**

---

## Wave Plan

**Shape:** file-overlap partitioned — all three stories edit the single new hotspot `factors.py` in a strict linear dependency chain (registry → evaluator → built-ins), so they MUST serialize. Shape A (single-hotspot collapse) does **not** apply because E12-S1 is L (> M), and collapsing the chain into one story would create an XL agent at real compaction risk. Three serial waves is correct here, not ceremony waste — there is genuinely zero parallelism to capture.

### Wave 1 — Registry (foundation)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E12-S1 | general-purpose | `factors.py` (new), `ta.py`, `tests/test_factors.py` (new) | 1/2 | Yes |

### Wave 2 — Evaluator (depends on Wave 1)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E12-S2 | general-purpose | `factors.py`, `tests/test_factors.py` | 2/0 | Yes (security cases) |

### Wave 3 — Built-in factors (depends on Wave 2)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E12-S3 | general-purpose | `factors.py`, `NOTICE` (new), `tests/test_factors.py` | 2/1 | No |

### Shared Hotspot Files
- **`src/domdhi_crypto/factors.py`** — touched by all 3 stories. By design (this is the file the epic builds); the linear dependency chain already forces them into separate waves, so there is no within-wave contention.

### Critical Path & Parallel Workstreams (REQUIRED)
- **Critical path:** E12-S1 → E12-S2 → E12-S3 — the entire epic; ~5–7h. This is the wall-clock floor.
- **Parallel workstreams:** none — single linear chain on one file. (Genuine parallelism arrives in Epic 13, where IC/ICIR and the backtester fan out from the evaluator.)
- **Max concurrent agents:** 1.
- **Bottleneck:** E12-S1 — it defines the registry + metadata contract every later story and epic consumes. If its primitive signatures or metadata shape are wrong, S2/S3/Epic 13/14 all churn.

---

## Execution Log

| # | Story | Date(s) | Session | Notes |
|---|-------|---------|---------|-------|
| 1 | E12-S1 | 2026-06-06 | run-todo W1 | `factors.py` created — 38 primitives, 8 categories, `FactorFunction` metadata. `ta.py` refactored to expose `sma`/`ema` helpers (DRY; 38 existing tests unchanged). 24 reference tests + no-`pandas-ta` guard. 62/62 pytest green. |
| 2 | E12-S2 | 2026-06-06 | run-todo W2 | `evaluate(expr, frame)` — stdlib-`ast` default-deny walk; no `asteval`/`eval`. Code review (security): no sandbox escape; fixed 2 MAJOR DoS vectors (deep-nest node cap, int-power float coercion) + arithmetic-error→ValueError contract, + honest rejection-before-eval test. 94/94 pytest green. Memory: `constraints/safe-ast-evaluator-dos-vectors`. |
| 3 | E12-S3 | 2026-06-06 | run-todo W3 | `BUILTIN_FACTORS` — 47 factors as data across 6 categories (trend/momentum/volatility/volume/statistical/composite), close+volume only. `NOTICE` created (Apache-2.0 / HammerGPT attribution; project stays MIT). High/low factors catalogued in `DEFERRED_FACTORS` with reasons. 47 parametrized eval tests; 146/146 pytest green. |

---

## Key Decisions

(Logged as they occur during implementation.)

---

## Validation

- [x] Build/lint succeeds: `ruff check src tests`
- [x] Tests pass: `pytest` (new `tests/test_factors.py` green; existing 38 unmodified → 146 total)
- [x] No `pandas-ta` import anywhere (guard test green)
- [x] `factors.py` import graph is leaf-safe (numpy/pandas + `ta` only)
- [x] Documentation updated (architecture: new `factors.py` module note + file tree + ADR-001 dep)
- [x] Patterns extracted to memory (`constraints/safe-ast-evaluator-dos-vectors`)

---

## Key Findings from Research

1. **Reuse `ta.py`, don't duplicate** — `rsi`/`macd`/`bollinger`/`atr`/`annualized_vol` + `_f` already exist and are reference-tested; the registry wraps them. (`src/domdhi_crypto/ta.py`)
2. **ADR-001 is the hard constraint** (memory `adr-001`, conf 1.0): pure numpy/pandas, **no `pandas-ta`** — and no `asteval` either; use stdlib `ast` for the safe evaluator. The auditability this preserves is the cortex's differentiator vs. HammerGPT.
3. **Data-shape gotcha** — `db.load_close_series` yields daily **close+volume** only; `high/low/open` are in the separate `ohlc` table (different granularity/index). First-cut factors are close/volume; high/low factors are **deferred** pending a unified daily-OHLCV loader (flagged, not faked). (`src/domdhi_crypto/db.py`)
4. **License gate** — porting Apache-2.0 factor strings (E12-S3) requires deciding the project license + adding `NOTICE` first (brief open question).
5. **Linear chain, single file** — no parallelism in this epic; that's a fact of the dependency structure, surfaced so `/run-todo` doesn't try to parallelize and hit `factors.py` contention.

---

## Dependencies to Next

Completing Epic 12 unblocks **Epic 13 (Edge Validation)** — IC/ICIR scoring and the look-ahead-safe backtester both consume the evaluator + built-in factors — and **Epic 14 (MCP Interface)**, which serves the registry metadata as the agent's factor menu.

---

**Last Updated:** 2026-06-06
