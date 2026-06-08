# TODO: Epic 18 — Decision Dashboard

| Attribute | Value |
|-----------|-------|
| **Epic** | 18 — Decision Dashboard (Cycle 3, Phase 8 — the lead) |
| **Source** | [_backlog.md](_backlog.md) · [../_project-requirements.md](../_project-requirements.md) (FR-28…FR-32) |
| **Generated** | 2026-06-06 (via `/evolve` → `/todo` cycle 2→3) |
| **Governing ADR** | ADR-009 (vendored uPlot, single offline HTML, no framework/server/build) |
| **Status** | ✅ complete — all 5 stories shipped (2026-06-06) |

---

## Executive Summary

Surface the cycle-2 decision layer in the existing offline `dashboard.html`. The compute is all done (`ledger.py`, `risk.py`, `factors.py`/`digest.py`/`context.py`, `backtest/`); this epic is **wiring + rendering**. The one new capability is interactive charts via a **vendored uPlot** blob inlined into the HTML (ADR-009) — no CDN, no npm, no build step, no server, and **not** a Python dependency (3-dep core preserved, ADR-007).

> **Shared-hotspot warning:** all 5 stories modify `src/domdhi_crypto/dashboard.py`. S1 establishes the uPlot substrate + a panel-assembly seam; S2–S5 each add one panel. This is **NOT naive-parallel** — run S1 first (root), then S2–S5 sequentially or with explicit per-panel section ownership to avoid contention on `dashboard.py`.

---

## Dependency Graph

```
            ┌─────────────────────────────┐
   Wave 1   │ E18-S1 uPlot substrate +     │   (root: vendored asset, inline,
            │        dashboard panel seam  │    one interactive chart proves it)
            └──────────────┬──────────────┘
                           │ (all panels render through the substrate)
        ┌──────────┬───────┴───────┬──────────┐
   W2  E18-S2     E18-S3         E18-S4      E18-S5
       NAV+P/L    Risk panel     Signals     Backtest curve
       (ledger)   (risk.py)      (factors)   (backtest/)
        └──────────┴───────────────┴──────────┘
             all modify dashboard.py → sequence / section-own
```

The S2–S5 → S1 edges are hard (panels need the substrate). The S2–S5 mutual edges are *file-contention* edges, not logical ones.

---

## Phase 8: Surface It

**Goal:** One offline `dashboard.html` that renders NAV+P/L, risk, triggered signals, and a backtest equity curve from the cycle-2 modules, with interactive uPlot charts.

### Epic E18: Decision Dashboard

**Objective:** Wire `ledger`/`risk`/`factors`/`backtest` into `dashboard.py` and render them with vendored uPlot (FR-28…FR-32, ADR-009).

* **Story E18-S1 (Frontend/Backend): Vendored uPlot charting substrate**
  * **As an** agent operator, **I want** the dashboard to render interactive charts offline, **So that** I can explore my data with no server or build step.
  * **AC:**
    * [x] uPlot (MIT, ~40KB minified) committed as a static asset (e.g. `src/domdhi_crypto/vendor/uplot.min.js` + `uplot.min.css`), with a `vendor/README` recording **version + source URL + license** (ADR-009 maintenance note). — uPlot v1.6.31, `vendor/README.md` records version/source/MIT/sha256.
    * [x] `dashboard.py` inlines the uPlot JS+CSS into `dashboard.html` at generation time (read the asset, embed in `<script>`/`<style>` — same pattern as the existing inline `<style>` block), NOT a CDN link. — `_load_vendor` + `{uplot_js}`/`{uplot_css}` template slots; no `src=http`/CDN.
    * [x] The generated HTML opens with the **network disabled** and renders at least one interactive (zoom/cursor/tooltip) uPlot chart. — `new uPlot(` proof chart; no external resource refs.
    * [x] `pyproject.toml` runtime core dependencies are **unchanged** (3 deps; uPlot is not added; ADR-007 preserved). — deps still 3; uPlot ships as wheel data via `force-include`.
    * [x] A panel-assembly seam exists so S2–S5 each add one panel without rewriting `build()`. — `_PANEL_FUNCS` registry + `_assemble_panels(ctx)`; `{panels}` slot.
  * **Files:**
    * NEW `src/domdhi_crypto/vendor/uplot.min.js`, `src/domdhi_crypto/vendor/uplot.min.css`, `src/domdhi_crypto/vendor/README.md`
    * MOD `src/domdhi_crypto/dashboard.py` (inline loader + panel seam), `src/domdhi_crypto/paths.py` (if a vendor-asset path helper is added), `pyproject.toml`/`MANIFEST` (package the vendored asset)
    * MOD `tests/test_dashboard.py` (NEW if absent) — assert the generated HTML contains the inlined uPlot source and no `http`/`cdn` chart link
  * **Research notes:** `dashboard.build(open_after=False)` (`dashboard.py:145`) owns IO — it reads `paths.coins_path()`, `db.connect()`, loops coins, concatenates f-strings, `write_text`, returns the path. It currently imports only `db, paths, ta`. Existing inline-asset pattern: the `<style>` block is embedded as a string literal — mirror it for uPlot (read the vendored file, embed). Package-data: hatchling needs the `vendor/*.js`/`*.css` declared so they ship in the wheel (check `pyproject.toml [tool.hatch.build]`). Keep the hand-rolled SVG helpers (`_poly`:40, `_sparkline`:54, `_price_chart`:65, `_rsi_strip`:121) for now — uPlot is additive. Charts need data as JS arrays; emit `[xs, ys]` from Python via `json.dumps` (already imported).
  * **Est:** M · **Status:** ✅ done · **Deps:** None

* **Story E18-S2 (Backend): NAV + P/L panel**
  * **As a** holder, **I want** my NAV curve and realized/unrealized P/L on the dashboard, **So that** I can see my position over time.
  * **AC:**
    * [x] A dated NAV line chart renders from `ledger.nav_series(conn, coins_cfg)` (uPlot).
    * [x] Realized + unrealized P/L figures render from `ledger.realized_pl(conn, coins_cfg)` and `ledger.unrealized_pl(conn, coins_cfg)` (use `_pl_color`:139, `_fmt_money`:28).
    * [x] Empty NAV / no transactions → panel shows "n/a"/empty, never errors (NaN-safe).
  * **Files:** MOD `src/domdhi_crypto/dashboard.py` (NAV panel) · MOD `tests/test_dashboard.py`
  * **Research notes:** `ledger.nav_series` returns a dated `pd.Series` (may be empty); convert index→epoch-seconds + values→list for uPlot. `realized_pl`/`unrealized_pl` are scalars, finite-guarded. `dashboard.py` must add `from . import ledger`. The IO (`conn`, `coins_cfg`) is owned by `build()`; pass them into the pure ledger calls — do NOT call `db.connect()` inside the panel.
  * **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

* **Story E18-S3 (Backend): Risk panel**
  * **As a** holder, **I want** correlation/vol/beta/drawdown on the dashboard, **So that** I can see real diversification at a glance.
  * **AC:**
    * [x] Correlation matrix (`risk.correlation_matrix`) renders as a table/heatmap; portfolio vol (`risk.portfolio_vol`), beta-to-BTC (`risk.beta_to_btc`), and max-drawdown (`risk.max_drawdown` on the NAV series) render as figures.
    * [x] NaN / under-window outputs surface as "n/a" (use `_fmt_pct`:32 / `_fmt_money`), never fabricated, never a crash.
  * **Files:** MOD `src/domdhi_crypto/dashboard.py` (risk panel) · MOD `tests/test_dashboard.py`
  * **Research notes:** `risk.*` all take `(conn, coins_cfg)` except `max_drawdown(series)` which takes a Series (feed it the `ledger.nav_series` from S2, or per-coin closes). `correlation_matrix` returns a `pd.DataFrame` indexed by symbol (may be empty/NaN under-window). `beta_to_btc` returns `dict[symbol,float]` (empty when no BTC configured). Add `from . import risk`.
  * **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

* **Story E18-S4 (Backend): Triggered-signals view**
  * **As a** holder, **I want** to see which factor/digest signals are currently firing, **So that** the agent's "why now" is visible to me.
  * **AC:**
    * [x] Per-coin, the dashboard lists currently-triggered signals with their values (TA signals + notable factor values).
    * [x] No data for a coin → the coin is skipped/empty, not errored.
  * **Files:** MOD `src/domdhi_crypto/dashboard.py` (signals panel) · MOD `tests/test_dashboard.py`
  * **Research notes:** `context.build_context(symbol, *, conn, coins_cfg)` (`context.py`) returns `result["signals"]["ta"]["signals"]` (plain-English list like "RSI 72 - overbought") + `result["factor_values"]` (~44 factor floats) + a `position` block — the digest already consumes exactly this. `digest.build_digest(coins_cfg, *, conn)` has the triggered-signal selection logic (`_is_triggered`) — reuse or mirror it rather than re-deriving. Add `from . import context` (and/or `digest`). All JSON-safe (finite-guarded).
  * **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

* **Story E18-S5 (Backend): Backtest equity curve + attribution**
  * **As a** holder, **I want** a backtest's equity curve + by-factor attribution rendered, **So that** I can see strategy performance visually.
  * **AC:**
    * [x] A `backtest/` run's equity curve renders as an interactive uPlot line; per-factor attribution renders as a table.
    * [x] Absent a backtest run, the panel is omitted/empty without error (don't force a run inside `build()` unless cheap + deterministic).
  * **Files:** MOD `src/domdhi_crypto/dashboard.py` (backtest panel) · MOD `tests/test_dashboard.py`
  * **Research notes:** `backtest/engine.py` returns a `BacktestResult` with an equity curve (one point per bar) + `summary` (total_return, total_realized_return, win_rate, max_drawdown); `backtest/attribution.py` groups closed-trade returns by `Trade.triggering_factor`. Decide whether the dashboard *runs* a backtest (needs a strategy/factor choice) or *reads a cached result* — prefer reading a cached/optional result to keep `build()` fast and deterministic. Look-ahead guard is internal to the engine; no new safety surface here.
  * **Est:** M · **Status:** ✅ done · **Deps:** E18-S1

---

## Story Index

| Story | Title | Size | Wave | Status | Dependencies |
|-------|-------|------|------|--------|-------------|
| E18-S1 | Vendored uPlot substrate + panel seam | M | 1 | ✅ done | None |
| E18-S2 | NAV + P/L panel | M | 2 | ✅ done | E18-S1 |
| E18-S3 | Risk panel | M | 2 | ✅ done | E18-S1 |
| E18-S4 | Triggered-signals view | M | 2 | ✅ done | E18-S1 |
| E18-S5 | Backtest equity curve + attribution | M | 2 | ✅ done | E18-S1 |

**Total: 5 stories. Estimated: ~6–9 hours.**

---

## Wave Plan

**Shape:** single shared hotspot (`dashboard.py`). One root story (S1) then a fan of panels (S2–S5) that all modify the same file.

### Wave 1 — Substrate (root)
| Story | Agent Type | Files Owned | Needs QA? |
|-------|-----------|-------------|-----------|
| E18-S1 | Main-Agent-direct (Path A) | `dashboard.py`, `vendor/*`, `paths.py`, `pyproject.toml`, `tests/test_dashboard.py` | yes (offline-render assertion) |

### Wave 2 — Panels (depend on Wave 1)
| Story | Agent Type | Section Owned in `dashboard.py` | Needs QA? |
|-------|-----------|---------------------------------|-----------|
| E18-S2 | delegated / direct | NAV+P/L panel fn | yes |
| E18-S3 | delegated / direct | Risk panel fn | yes |
| E18-S4 | delegated / direct | Signals panel fn | yes |
| E18-S5 | delegated / direct | Backtest panel fn | yes |

### Shared Hotspot Files
- **`src/domdhi_crypto/dashboard.py`** — modified by ALL 5 stories. Wave 1 must land the panel-assembly seam (each panel = a self-contained `_panel_*()` returning an HTML string, assembled in `build()`) so Wave 2 stories edit **disjoint functions**, not the same lines. If run concurrently, assign each its own `_panel_*` function and have the lead own the single `build()` assembly edit. Otherwise run Wave 2 strictly sequentially.

### Critical Path & Parallel Workstreams
- Critical path: **S1 → (any panel)**. S1 is the gate; until the substrate + seam exist, no panel can render through uPlot.
- After S1, the 4 panels are logically independent (different source modules) but **file-coupled** on `dashboard.py` — parallelize only with the `_panel_*` section-ownership discipline above.

---

## Key Findings from Research
1. **`dashboard.py` owns its IO** (`build()` reads coins + `db.connect()`); the cycle-2 modules it must call (`ledger`, `risk`, `context`/`digest`) are **pure** (`(conn, coins_cfg)` injected) — pass `build()`'s `conn`/`coins_cfg` down; never open a second connection in a panel.
2. **uPlot is additive, not a rewrite** — keep the hand-rolled SVG helpers; add uPlot for the new interactive curves (NAV, equity). ADR-009 governs.
3. **Package-data gotcha** — the vendored `vendor/*.js`/`*.css` must be declared to hatchling or it won't ship in the wheel; add a `tests/test_dashboard.py` assertion that the inlined source is present and there is no remote chart link (enforces "offline").
4. **`json.dumps` is already imported** in `dashboard.py` — emit chart data as JS arrays through it (finite-guarded upstream).
5. **Backtest panel should read, not run** — prefer an optional cached `BacktestResult` over forcing a (strategy-dependent, slower) run inside `build()`, to keep dashboard generation fast and deterministic.
6. **Shared-hotspot is the only real risk** — the `_panel_*()` seam from S1 is what makes Wave 2 safe; land it first.

---

## Execution Log
- **2026-06-06 — Wave 1 (E18-S1):** Vendored uPlot v1.6.31 (`vendor/uplot.min.js`+`.css`+`README.md`, MIT). Added `paths.vendor_dir()`, dashboard `_load_vendor`/`_json_script`/`_uplot_chart`/`_panel` helpers + `_PANEL_FUNCS` registry + `_assemble_panels`, `{uplot_js}`/`{uplot_css}`/`{panels}` template slots, and a proof uPlot price chart. `pyproject` `force-include` ships the assets in the wheel (verified). Code review: DONE_WITH_CONCERNS → fixed MINOR-1 (`</script>` breakout hardening via `_json_script`), MINOR-2 (audible panel-failure log), MINOR-3 (proof-panel + hardening tests). 316 tests green (8 new in `tests/test_dashboard.py`).
- **2026-06-06 — Wave 2 (E18-S2/S3/S4/S5):** Main-Agent-direct sequential (shared `dashboard.py`). `_panel_nav` (NAV uPlot + realized/unrealized P/L), `_panel_risk` (correlation table + vol + β-to-BTC + max-drawdown, finite-guarded `_pct_or_na`/`_num_or_na`), `_panel_signals` (per-coin triggered signals via `context.build_context` + mirrored `_is_triggered`), `_panel_backtest` (default `price_vs_sma20` rule per coin → equity-curve uPlot + attribution table). Contract change (approved): `BacktestResult.equity_curve` field (`eq=False`), populated in `engine.run_backtest`. Code review: DONE_WITH_CONCERNS → fixed MAJOR-1 (HTML-escape user symbols in body/attr + `_json_script` div-id lookup), MINOR-1 (`eq=False`), MINOR-2 (hoist `nav` into ctx), NIT-1 (`_finite` in `_series_xy`). Gate green **327 tests** (e2e SKIP=PASS, no suite); independent build verified 4 uPlot charts + all panels, no raw NaN.
