# Cycle 2 Summary — DomdhiCrypto · "Decision Cortex"

**Closed:** 2026-06-06  ·  **Span:** 2026-06-06 → 2026-06-06 (single intensive build day)  ·  **Stamp:** 260606-2135
**Completion:** 15 done / 0 open / 0 deferred / 0 blocked  (100%)

> Story counts are at the epic-group level (15 backlog stories). At the per-epic
> AC-checklist grain, 92 checklist items across the 5 `TODO_epic*.md` files, all `[x]`.
> Gate green throughout: **308 tests passing**, ruff clean.

## What shipped

The full agent-native **Decision Cortex** spine — the five "limbs" from the cycle-2
pivot doc (`_feature-ideas.md`), turned from idea into working code. 13 new source
modules; ~15k line delta across 160 files (incl. docs/plans/telemetry).

- **Epic 12 — Signal Substrate** (3 stories, `a63764b`): `factors.py` — declarative
  factor expressions over a pure-numpy primitive registry + a safe AST evaluator +
  a built-in factor library (HammerGPT set, hand-rolled per ADR-001). Registry
  metadata doubles as the agent's documented factor menu.
- **Epic 13 — Edge Validation** (3 stories, `8831eb6`): `effectiveness.py` (IC/ICIR
  factor scoring vs forward returns) + the `backtest/` package — a **look-ahead-safe**
  event engine (data_provider, virtual_account, execution_simulator, engine,
  attribution). By-factor attribution reconciles to closed-trade returns within 1e-6.
- **Epic 14 — Agent Decision Interface** (4 stories, `09fc7ed`): `context.py`
  (JSON-safe signals+position+factor menu) + `decision.py` (decision schema +
  validator + trigger context) + `mcp_server.py` (FastMCP stdio server). MCP kept an
  optional `[mcp]` extra; core stays 3-dep (ADR-007).
- **Epic 15 — Alerts & Scheduled Digest** (2 stories, `ac18204`): `digest.py` —
  offline Markdown brief of triggered TA signals. Pure build + IO wrapper.
- **Epic 16 — Portfolio Context (thin)** (3 stories, `82849aa`): DB migration scaffold
  (`schema_version` + `MIGRATIONS` + `migrate()`) + user-entered `transactions` table
  + `ledger.py` (NAV-over-time + average-cost realized/unrealized P/L) + `risk.py`
  (correlation / portfolio vol / beta-to-BTC / max-drawdown). The DB became a
  **partial source of truth** (ADR-008).

## What production is telling us

No live/production telemetry yet — the engine has been **built and unit-tested
(network mocked) but never run on real data**. The standing `/listen` intake
(`docs/.output/intake/2026-06-06.md`) predates this cycle entirely (Epic-11 /
template-validation era), so it carried no cycle-2 product signal. Re-plan was
seeded from `_feature-ideas.md`, the four epic retros, and the in-session ADR-009
decision instead.

The single loudest signal came from the session itself: **the decision layer has no
human-facing surface** — `dashboard.py` still imports only `db, ta, paths` and renders
Cycle-1 visuals; none of factors/backtest/ledger/risk/digest is visible to a human.

## Lessons (from 4 retros)

- **Adversarial per-wave code review beats a green suite** — found a CRITICAL + MAJOR
  behind passing tests in *every* epic (e.g. `json-safety-isnan-misses-infinity`,
  `boundary-validator-must-guard-nondict-before-membership`). Non-optional going forward.
- **TDD-first signature pinning** (lead writes the test, dev fills the impl) kept
  delegated agent output well-targeted and on-contract.
- **Interview-before-sizing** resolved the Epic-14 transport fork cheaply (→ ADR-007)
  before any code was written. We repeated it this cycle for the dashboard (→ ADR-009).
- **Pure/IO boundary** (inject `conn`+`coins_cfg`, never `db.connect()` in a leaf)
  carried cleanly across Epics 14/15/16 — unit-testable with no monkeypatching.
- **Empty-registry-first** shipped the migration engine proven in isolation before the
  first real migration plugged in risk-free.
- **Friction:** `general-purpose/sonnet` rogue-committed 4× across Epics 13/14/16 when
  the dispatch prompt omitted the "DO NOT COMMIT" line — fixed by baking it into
  `/run-todo`'s Path-B template during the sweep (`c424692`).

## Carried forward to cycle 3

- **Lead (decided this session):** Decision Dashboard — surface ledger/risk/factors/
  digest/backtest in the offline HTML via vendored uPlot (**ADR-009**).
- **Prove it on reality:** run the full `ingest → ta → factors → backtest → digest`
  loop on real coins; the "walk" rung — `_feature-ideas.md` Idea 12 "Alpha Arena for
  one" (paper-trade the cortex vs buy-and-hold, scored by the backtester/attribution).
- **Hardening / debt:** finish the HammerGPT 64-factor port (Idea 3); provider
  abstraction to de-risk CoinGecko coupling (parking lot); stablecoin guard in
  `cmd_factors`/`cmd_backtest` (Epic-13 retro, High); transaction-sequence validation
  (Epic-16 deferred follow-up).
- **Stays out:** Epic 17 gated live-execution adapter (Won't, this version).
