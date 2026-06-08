# TODO: Epic 20 — Hardening & Debt (+ Walk-Forward Validation)

| Attribute | Value |
|-----------|-------|
| **Status** | Specification Complete |
| **Author** | Dom |
| **Created** | 2026-06-07 |
| **Phase** | 10 — Harden It |
| **Source** | `docs/todo/_backlog.md` Epic 20 (FR-35…FR-38) + new walk-forward story (FR-34 follow-up) |
| **Research** | `docs/.output/work/2026-06-07/epic20_hardening-debt/1157-research-codebase.md` |

---

## Executive Summary

Close cycle-3 carry-forward debt and add the out-of-sample robustness check the Epic 19 arena flagged
as its unmet bar. Five fully independent stories (zero file overlap → one parallel wave): complete the
HammerGPT factor port, put CoinGecko behind a provider seam, cover the stablecoin guard for `ta`, add
optional transaction-sequence validation, and add **walk-forward sub-period validation** so a strategy's
edge can be checked across disjoint time folds rather than one flattering full-period number.

---

## Dependency Graph

```
   Wave 1 — all 5 stories independent, disjoint files, parallel
   ┌──────────────────────────────────────────────────────────────────┐
   │ E20-S1 factors.py      E20-S2 prices_provider+coingecko+cli       │
   │ E20-S3 test_cli.py     E20-S4 ledger.py        E20-S5 walkforward │
   └──────────────────────────────────────────────────────────────────┘
   No inter-story dependencies. Each ships its own code + test.
```

---

## Phase 10: Harden It

**Goal:** Tie off carried-forward debt and add out-of-sample validation for the cortex.

---

### Epic E20: Hardening & Debt (+ Walk-Forward)

**Objective:** Close FR-35…FR-38 plus the FR-34 walk-forward follow-up. Independent, parallel-safe stories.

---

* **Story E20-S1 (M): Extend the HammerGPT factor library toward the full set**
  * **As a** holder, **I want** more of the HammerGPT factor set available as data, **So that** my factor menu is closer to complete, not a 47-of-~64 subset.
  * **AC:**
    * [x] Additional close+volume-expressible factors from the HammerGPT-derived set are added to `BUILTIN_FACTORS` in `factors.py` as **pure data strings** (no new Python per factor), each with `name`/`expression`/`category` and a one-line description, evaluating without error over a close+volume frame.
    * [x] Every newly added factor is automatically covered by the existing parametrized test (`tests/test_factors.py:416`) — run it and confirm green; add a count-assertion update if one exists.
    * [x] Any factor that genuinely requires high/low (OHLCV) columns is NOT added to `BUILTIN_FACTORS` but recorded in `DEFERRED_FACTORS` with its blocking reason (mirrors the existing 5 deferred: `adx_14`, `aroon_25`, `cci_20`, `williams_r_14`, `atr_ratio_14`).
    * [x] `NOTICE` (Apache-2.0 HammerGPT attribution) is verified present and covers the additions — **do NOT recreate it; it already exists.**
    * [x] A one-line comment near `BUILTIN_FACTORS` records the new count and that factors beyond it await the high/low OHLCV loader.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/factors.py` — append builtin factor dicts (+ deferred entries / count comment).
  * **Agent budget:** 1 modified, 0 created — within ≤5/≤2 cap.
  * **Research notes:** `BUILTIN_FACTORS`=47, `DEFERRED_FACTORS`=5 (all high/low-blocked), total 52 vs the ~64 target — **the remaining ~12 are NOT enumerated anywhere in this repo** (they live in HammerGPT's `insert_builtin_expression_factors.py`). The implementer must enumerate the close+volume-expressible remainder from that external source; `FUNCTION_REGISTRY` (38 primitives) already covers the known close/volume patterns, so most should be data-only. **Honest scope:** add as many close+volume factors as the registry can express toward ~64; if the external list is unavailable, derive additional documented close+volume factors (momentum/trend/volatility/volume/statistical categories) consistent with the existing builtins and note the cap. Do not invent high/low factors — defer them.

---

* **Story E20-S2 (M): Provider abstraction for prices**
  * **As a** maintainer, **I want** `coingecko.py` behind a `prices`-provider seam, **So that** single-vendor coupling (Architecture Risk #2) can be swapped without touching callers.
  * **AC:**
    * [x] A new `prices_provider.py` defines a minimal provider interface (a `typing.Protocol` named e.g. `PricesProvider`) declaring the methods `cmd_ingest` consumes: `markets(ids, vs)`, `market_chart(coin_id, days, vs)`, `ohlc(coin_id, days, vs)`.
    * [x] `CoinGecko` is documented/typed as satisfying `PricesProvider` (structural — no inheritance required); a small factory or typed seam (e.g. `get_provider() -> PricesProvider`) lets `cli.cmd_ingest` depend on the interface, not the concrete class.
    * [x] Ingest behavior is **unchanged** with CoinGecko as the default provider; all existing `tests/test_coingecko.py` and CLI ingest tests stay green.
    * [x] The seam is covered by a test (network mocked, same pattern as `test_coingecko.py`: `MagicMock` session, patched `time.sleep`, `config={}` constructor) proving a stand-in provider conforming to the Protocol drives `cmd_ingest` without touching CoinGecko.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/prices_provider.py` — NEW: `PricesProvider` Protocol (+ optional `get_provider` factory).
    * `src/domdhi_crypto/coingecko.py` — MODIFY: declare conformance (a `PricesProvider`-typed annotation / docstring; no behavior change).
    * `src/domdhi_crypto/cli.py` — MODIFY: `cmd_ingest` obtains the provider via the seam (type the local as `PricesProvider`).
    * `tests/test_coingecko.py` — MODIFY: add a Protocol-conformance / stand-in-provider test.
  * **Agent budget:** 3 modified, 1 created — within ≤5/≤2 cap.
  * **Research notes:** `coingecko.py` is 89 lines; `CoinGecko` has `__init__`, `_get`, `markets`, `market_chart`, `ohlc`. `cmd_ingest` is the ONLY callsite (`CoinGecko()` then `.markets()`/`.market_chart()`/`.ohlc()`). Keep the seam a pure `Protocol` (ADR-001: no new deps; `typing.Protocol` is stdlib). Tests bypass `load_config` via `config={}` and replace `cg.session` with `MagicMock()`, patching `coingecko.time.sleep`. **Do not touch `cmd_ingest`'s fetch loop logic** — only the provider acquisition line.

---

* **Story E20-S3 (XS): Stablecoin guard test for `ta`**
  * **As a** holder, **I want** a stablecoin symbol to yield a clear "stablecoin — no TA" message in `ta`, **So that** I'm not sent to a misleading "Run: ingest" dead-end — and so the guard is regression-protected.
  * **AC:**
    * [x] A new test `test_ta_stablecoin_exits` in `tests/test_cli.py` asserts that `domdhi-crypto ta USDT` raises `SystemExit` (USDT is already flagged stable in the `factors_env` fixture), mirroring the existing `test_backtest_stablecoin_exits`.
    * [x] The test passes against the CURRENT `cmd_ta` guard (`cli.py:129`) — no `cli.py` change is required; this closes the coverage gap, not a code gap.
  * **Estimate:** XS
  * **Dependencies:** None
  * **Files:**
    * `tests/test_cli.py` — MODIFY: add `test_ta_stablecoin_exits` (reuse `factors_env`).
  * **Agent budget:** 1 modified, 0 created — within ≤5/≤2 cap.
  * **Research notes:** The guard already exists — commit `0fabfef` added `_load_series_or_exit`, and `cmd_ta` rejects stablecoins at `cli.py:129`; `factors`/`backtest`/`arena` all have passing stablecoin-exit tests. The ONLY gap is `cmd_ta` has no stablecoin test. Pattern: copy `test_backtest_stablecoin_exits` (in `tests/test_cli.py`), swap the subcommand to `ta`. Do NOT modify `cli.py`.

---

* **Story E20-S4 (S): Optional transaction-sequence validation**
  * **As a** holder, **I want** optional validation of transaction sequences, **So that** incoherent input (e.g. oversell) can be caught when I want it — without changing the default behavior.
  * **AC:**
    * [x] A new `validate_transactions(rows) -> list[str]` in `ledger.py` returns a list of human-readable problems for an incoherent sequence (at minimum: an **oversell** — a sell whose amount exceeds the running held quantity — and a **leading sell** with no prior buy). An empty list means coherent.
    * [x] It is **pure and opt-in**: calling it does not change `nav_series`/`realized_pl`/`unrealized_pl`. The existing average-cost CLAMP behavior (`ledger.py:116-118`) is untouched, and the characterization tests `test_oversell_clamps_to_flat` and `test_leading_sell_uses_zero_basis` stay green.
    * [x] New tests in `tests/test_ledger.py` cover: a coherent sequence → `[]`; an oversell → a message naming the coin/timestamp; a leading sell → a message; and a re-assertion that the clamp path is unchanged when validation is not called.
  * **Estimate:** S
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/ledger.py` — MODIFY: add `validate_transactions`.
    * `tests/test_ledger.py` — MODIFY: add validation tests.
  * **Agent budget:** 2 modified, 0 created — within ≤5/≤2 cap.
  * **Research notes:** Clamp is `ledger.py:116-118` (`if total_amount <= 0: total_amount = 0.0; total_cost = 0.0`). `db.load_transactions(conn, coin_id=None)` returns rows ordered by `ts` (sqlite3.Row, columns incl. coin_id/ts/side/amount). **`db.py` does NOT need changes** — the backlog's listing of it was speculative. `validate_transactions` walks rows per coin tracking running quantity; it is a read-only checker, NOT wired into the replay. Keep `ledger.py` pure (it already imports only `db` + pandas/math).

---

* **Story E20-S5 (M): Walk-forward sub-period validation**
  * **As an** operator, **I want** a strategy's return measured across sequential out-of-sample time folds, **So that** I can tell whether its edge is consistent or driven by one flattering sub-period (the Epic 19 "ETH carries the mean" problem).
  * **AC:**
    * [x] A new pure leaf `walkforward.py` exposes `walk_forward(frame, cortex_rules, *, n_splits=4, initial_cash=10_000.0, slippage_bps=0.0, fee_rate=0.0) -> WalkForwardResult` that runs ONE look-ahead-safe `engine.run_backtest` over the full frame, then segments its equity curve into `n_splits` **contiguous, non-overlapping** folds and reports per-fold strategy return vs a buy-and-hold benchmark over the same fold.
    * [x] `WalkForwardResult` (a frozen `eq=False` dataclass) carries `folds: list[FoldResult]` (each with `index`, `start`, `end`, `cortex_return`, `benchmark_return`, `edge = cortex - benchmark`, `n_trades`), plus aggregates `n_folds`, `cortex_win_rate` (fraction of folds with `edge > 0`), `mean_edge`, `mean_cortex_return`, `mean_benchmark_return`.
    * [x] **Honesty constraint (documented in the module docstring AND enforced by a test):** this is out-of-sample SUB-PERIOD segmentation, NOT walk-forward parameter optimization — there is no train/fit step (factor thresholds are fixed). Look-ahead safety is inherited from `engine.run_backtest` (the single full-frame run uses only past data at each bar); folds partition the resulting safe equity curve. A test asserts each fold's `cortex_return` equals the corresponding slice of a direct `engine.run_backtest` equity curve (faithful, no re-derivation).
    * [x] Edge cases: `n_splits=1` → a single fold equal to the whole-period result; `n_splits < 1` or `n_splits > len(frame)` → `ValueError`. Folds together cover the full index with no gaps or overlaps.
    * [x] `walkforward.py` is a pure leaf: imports only `backtest.engine` (+ pandas + `dataclasses`); NO `cli`/`dashboard`/`db`/`arena` imports.
  * **Estimate:** M
  * **Dependencies:** None
  * **Files:**
    * `src/domdhi_crypto/walkforward.py` — NEW: `walk_forward` + `FoldResult`/`WalkForwardResult`.
    * `tests/test_walkforward.py` — NEW: fold partitioning, per-fold returns, aggregates, faithful-passthrough/look-ahead, edge cases.
  * **Agent budget:** 0 modified, 2 created — within ≤5/≤2 cap.
  * **Research notes:** Reuse `engine.run_backtest(frame, rules, *, initial_cash, slippage_bps, fee_rate) -> BacktestResult` (`.equity_curve` per-bar pd.Series, `.trades` with `exit_ts`). Mirror `arena.py`'s pure-leaf + `eq=False` discipline (Series fields break frozen `__eq__`). **Design (load-bearing):** run the backtest ONCE on the full frame (preserves long-window factors like SMA200 — per-fold short windows would null them out), then per fold compute `cortex_return = equity.loc[fold].iloc[-1]/equity.loc[fold].iloc[0] - 1` and `benchmark_return = close.loc[fold].iloc[-1]/close.loc[fold].iloc[0] - 1`; `n_trades` = trades whose `exit_ts` falls in the fold. Segment by splitting the equity-curve index into `n_splits` contiguous ranges (e.g. `np.array_split` on positions). This is exactly the cross-fold consistency check that would validate (or debunk) the Epic 19 arena's +33pp mean edge — see `docs/app/arena/_brief.md`.

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|--------------|
| E20-S1 | Extend HammerGPT factor library | M | 1 | [x] | None |
| E20-S2 | Provider abstraction for prices | M | 1 | [x] | None |
| E20-S3 | Stablecoin guard test for `ta` | XS | 1 | [x] | None |
| E20-S4 | Optional transaction-sequence validation | S | 1 | [x] | None |
| E20-S5 | Walk-forward sub-period validation | M | 1 | [x] | None |

**Total: 5 stories. Estimated: ~6 hours. — ALL COMPLETE (2026-06-07).**

---

## Execution Log

- **2026-06-07** — `/run-todo` single parallel wave (Sonnet subagents), all 5 stories shipped.
  Gate green: ruff clean, **391 tests** (357 baseline + 34 new). Plan:
  `docs/.output/plans/260607-1527-run-todo-epic20_hardening-debt.md`.
  - **E20-S1**: `signals/factors.py` BUILTIN_FACTORS 47→62 (+15 close+volume data factors); DEFERRED unchanged (5); count comment updated; NOTICE untouched. Auto-covered by parametrized eval test.
  - **E20-S2**: NEW `ingest/prices_provider.py` (`@runtime_checkable` `PricesProvider` Protocol + lazy `get_provider()` factory); `cmd_ingest` routed through the seam; CoinGecko conforms structurally (no import cycle); conformance + end-to-end seam tests added.
  - **E20-S3**: `test_ta_stablecoin_exits` added — guard already shipped (`0fabfef`), no `cli.py` change (test-coverage gap closed).
  - **E20-S4**: `portfolio/ledger.py` `validate_transactions(rows)->list[str]` — pure, opt-in, per-coin oversell + leading-sell detection; `_replay` clamp untouched.
  - **E20-S5**: NEW `backtest/walkforward.py` `walk_forward` + `FoldResult`/`WalkForwardResult` (frozen eq=False); ONE full-frame `engine.run_backtest`, equity curve segmented via `np.array_split`; look-ahead safety inherited (no train step).

## Key Decisions

- **Path remap (TODO authored pre-VSA-slice):** all target files had moved into slices
  (`signals/`, `ingest/`, `portfolio/`, `backtest/`); new modules landed in their slices
  (`ingest/prices_provider.py`, `backtest/walkforward.py`) with deep explicit imports.
- **E20-S5 robustness (code-review MAJOR, fixed):** `walk_forward` now normalises the input
  frame (`sort_index` + drop duplicate timestamps `keep="last"`) to mirror the engine's
  `DataProvider`, so the equity curve and the close/index slices reference the same bars —
  prevents a silent fold misalignment on unsorted frames and an `IndexError` on duplicate
  timestamps. Regression test added.

---

## Wave Plan

**Shape:** file-overlap partitioned — all 5 stories own **disjoint file sets** with no inter-story
dependencies, so they form a single parallel wave (zero file overlap within the wave). No role-split or
hotspot collapse applies; this is the genuine all-independent case.

### Wave 1 — all five (parallel, disjoint files)
| Story | Agent Type | Files Owned | Budget (mod/new) | Needs QA? |
|-------|-----------|-------------|------------------|-----------|
| E20-S1 | general-purpose | `factors.py` | 1/0 | Yes |
| E20-S2 | general-purpose | `prices_provider.py`, `coingecko.py`, `cli.py`, `tests/test_coingecko.py` | 3/1 | Yes |
| E20-S3 | general-purpose (or Main-direct, XS) | `tests/test_cli.py` | 1/0 | Yes |
| E20-S4 | general-purpose | `ledger.py`, `tests/test_ledger.py` | 2/0 | Yes |
| E20-S5 | general-purpose | `walkforward.py`, `tests/test_walkforward.py` | 0/2 | Yes |

### Shared Hotspot Files
- **None.** Every story owns a disjoint set. `cli.py` → only E20-S2; `tests/test_cli.py` → only E20-S3 (different file from `cli.py`, no overlap); `factors.py`/`ledger.py`/`walkforward.py` each single-owner.

### Critical Path & Parallel Workstreams (REQUIRED)
- **Critical path:** any single M story (E20-S1, E20-S2, or E20-S5) — ~1–2 h. There is no dependency chain; the floor is the slowest single story.
- **Parallel workstreams:** 5 fully independent chains, each owning a disjoint file set — `{S1 factors}` ∥ `{S2 provider}` ∥ `{S3 ta-test}` ∥ `{S4 ledger}` ∥ `{S5 walk-forward}`.
- **Max concurrent agents:** 5 (the single wave).
- **Bottleneck:** none structural. E20-S1 carries the only external-knowledge risk (the remaining HammerGPT factor list isn't in-repo) — it may ship a partial port with the cap documented rather than block the wave.

---

## Key Findings from Research

1. **All five stories are file-disjoint and dependency-free** — one parallel wave, max 5 agents, no hotspot. *(research §Overlap)*
2. **E20-S3 collapsed to XS** — the stablecoin guard already shipped (`_load_series_or_exit`, commit `0fabfef`); only `cmd_ta`'s test is missing. No `cli.py` change. *(research §E20-S3)*
3. **E20-S4 needs no `db.py`** — `db.load_transactions` already returns ts-ordered rows; the validator is a pure read-only checker in `ledger.py`. The backlog's `db.py` listing was speculative. *(research §E20-S4)*
4. **E20-S1 has an external-knowledge boundary** — only 52 of the ~64 HammerGPT factors are catalogued in-repo; the remaining ~12 live in HammerGPT's source. `NOTICE` already exists. Scope the port to close+volume-expressible factors and document the cap. *(research §E20-S1)*
5. **Walk-forward must run ONE full-frame backtest, then segment** — per-fold independent backtests would null out long-window factors (SMA200 needs 200 bars; 4 folds of 365 bars ≈ 91 each). Segmenting the single look-ahead-safe equity curve preserves factor lookback and is still genuinely out-of-sample. *(E20-S5 research notes)*
