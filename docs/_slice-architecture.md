# Slice Architecture — package layout & dependency graph

Domdhi.Crypto ships **two import packages in one distribution** (`pip install domdhi-crypto`):

- **`domdhi_crypto/`** — the engine, organized into Vertical-Slice sub-packages.
- **`domdhi_crypto_mcp/`** — the agent-facing layer (FastMCP `server` + FR-23 `decision`
  contract). A *separate top-level package* that imports **from** the engine, never the
  reverse, so the engine is usable with no agent code on the path. The `mcp` SDK stays an
  optional extra (`pip install domdhi-crypto[mcp]`); ADR-007's 3-dep core is preserved.

## Engine slices (`src/domdhi_crypto/`)

```
__init__.py  __main__.py  cli.py        ← host / composition root (wires every slice)
├── shared/      db.py, paths.py            core infra — SQLite + path resolution
├── ingest/      coingecko.py,              CoinGecko → SQLite acquisition; PricesProvider
│                prices_provider.py         Protocol seam (get_provider factory) over the vendor
├── signals/     ta.py, factors.py,         the edge layer: TA primitives, declarative
│                effectiveness.py           factor substrate + safe evaluator, IC/ICIR
├── portfolio/   ledger.py, risk.py         NAV/avg-cost P&L, correlation/vol/beta/drawdown
├── agent/       context.py                 agent-interface seam (consumed by domdhi_crypto_mcp)
├── backtest/    engine.py, data_provider,  look-ahead-safe engine + arena (universe harness)
│                virtual_account, execution_simulator, attribution, arena.py,
│                walkforward.py             + walk-forward out-of-sample sub-period segmentation
└── report/      digest.py,                 offline Markdown digest
    └── dashboard/   offline HTML dashboard — split into a package:
        __init__.py (build orchestration) · theme.py (palette) · charts.py (SVG/uPlot
        toolkit) · panels.py (data panels + registry) · scaffold.py (page template) ·
        vendor/ (uPlot, ADR-009 — static assets live next to the module that inlines them)
```

## Dependency graph (a clean DAG — arrows point only downward, no cycles)

```
                 cli ───────────────┐         domdhi_crypto_mcp
                  │ (host)           │              │ (separate package)
        ┌─────────┼─────────┬────────┴──┐          ▼
        ▼         ▼         ▼           ▼     ┌──► agent, shared, signals
      report ──► agent   backtest   portfolio │   (one-way: mcp → engine)
        │   └─────┤ └─► signals └─► shared ◄──┘
        └─► signals, portfolio, backtest, shared
                  ▼          ▼
               signals     shared        shared  → (none)   ← bedrock
               (pure)     (bedrock)      signals → (none)   ← pure leaf
```

Verified cross-slice imports (each slice → what it depends on):

| slice | depends on |
|-------|------------|
| `shared` | (none) — bedrock |
| `signals` | (none) — pure leaf |
| `ingest` | shared |
| `portfolio` | shared |
| `agent` | shared, signals |
| `backtest` | signals |
| `report` | agent, backtest, portfolio, shared, signals |
| `cli` | all slices (host) |
| `domdhi_crypto_mcp` | agent, shared, signals (engine only) |

## Conventions (keep the structure clean)

1. **Deep, explicit imports.** Always `from domdhi_crypto.<slice> import <module>` — never
   re-export through `__init__.py` to flatten the namespace. The slice is visible at every
   call site, so `grep portfolio` finds every portfolio user. `__init__.py` files hold only
   a docstring.
2. **Flat until it hurts, then split the file; cluster until it's a feature, then promote
   the folder.** A new capability starts as one module inside the right slice. When a single
   module grows past ~400 lines or takes on a second responsibility, split it. When a cluster
   of modules all serve one capability, promote them into a sub-package (how `backtest/` and
   these slices came to be).
3. **One distribution, two packages.** Add a sibling top-level package under `src/` only when
   shipping a genuinely separate concern with a one-way dependency on the engine (as
   `domdhi_crypto_mcp` does). Everything else is an intra-engine slice. A *third* distribution
   (its own `pyproject.toml`) is warranted only if a part needs an independent release cadence
   or independent consumers.
4. **Assets live in their owning slice.** Vendored/static files sit next to the module that
   uses them (e.g. `report/dashboard/vendor/`), resolved package-relative via `__file__` — not
   through `shared.paths`.
