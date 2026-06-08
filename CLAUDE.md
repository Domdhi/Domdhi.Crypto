# CLAUDE.md

Domdhi.Crypto — self-hosted, local-first crypto portfolio + TA engine
(CoinGecko → SQLite → hand-rolled TA → offline HTML dashboard).
Uses the Domdhi Agents template (.claude/ conventions active).

## Stack
Python >=3.11, src-layout, hatchling. **Two packages, one distribution:**
`src/domdhi_crypto/` (engine, VSA-sliced) + `src/domdhi_crypto_mcp/` (agent layer; imports
the engine one-way, never the reverse).
requests / pandas / numpy · SQLite · ruff · pytest.
Optional `[mcp]` extra (`mcp>=1.2`) for the agent-facing MCP server — core stays 3-dep (ADR-007).

## Build & Test
- Lint:  `ruff check src tests`   (CI: `ruff check .`)
- Test:  `pytest`   (391 unit tests, network mocked; the MCP server-construction test skips without the `[mcp]` extra)
- Gate:  `node .claude/core/gate.js test`
  Specialized config (`.claude/gate.config.json`, commit 40849e2):
  build leg = `ruff check src tests`, test leg = `pytest` — no mypy,
  no `ruff format --check`. Gate is green (build 0 errors, 391/391 tests with the extra installed).

## Key Paths
Engine `src/domdhi_crypto/` is organized into **Vertical-Slice sub-packages** (full graph +
conventions in [docs/_slice-architecture.md](docs/_slice-architecture.md)):
- `cli.py` — host/composition root, wires every slice. CLI commands: init · ingest · ta ·
  report · dashboard · factors · backtest · arena · walkforward · digest · mcp
- `shared/` — db.py (schema_version + MIGRATIONS + migrate(); DB is a partial source of truth
  via the user-entered transactions table) · paths.py
- `ingest/` — coingecko.py · prices_provider.py (PricesProvider Protocol seam + get_provider factory)
- `signals/` — ta.py (indicators incl. OHLCV: ATR/Williams %R/CCI/Aroon/ADX) ·
  factors.py (declarative 67-factor substrate + safe evaluator; 62 close+volume + 5
  high/low OHLCV factors via db.load_ohlcv_daily) · effectiveness.py (IC/ICIR)
- `portfolio/` — ledger.py (NAV-over-time + avg-cost realized/unrealized P/L) ·
  risk.py (correlation / portfolio vol / beta-to-BTC / max-drawdown)
- `agent/` — context.py (build_context: signals+position+factor menu, JSON-safe; the seam
  `domdhi_crypto_mcp` consumes)
- `backtest/` — look-ahead-safe engine (data_provider, virtual_account, execution_simulator,
  engine, attribution) + arena.py (full-universe harness) + walkforward.py (out-of-sample
  sub-period segmentation — one full-frame backtest, equity curve split into folds)
- `report/` — dashboard/ (package: __init__ `build` · theme · charts · panels · scaffold ·
  vendor/ uPlot ADR-009) · digest.py (offline Markdown brief)

Agent package `src/domdhi_crypto_mcp/` — decision.py (DECISION_SCHEMA + validate_decision +
build_trigger_context) · server.py (FastMCP stdio server; lazy mcp import behind the [mcp] extra).

**Import convention:** deep/explicit only — `from domdhi_crypto.<slice> import <module>`;
`__init__.py` files never re-export. Flat until it hurts, then split the file; cluster until
it's a feature, then promote the folder.

Git-ignored runtime: crypto.db, coins.local.json, config.local.json

## Architecture
See [docs/_slice-architecture.md](docs/_slice-architecture.md) (package layout + dependency graph),
[docs/_project-architecture.md](docs/_project-architecture.md) and [docs/_project-context.md](docs/_project-context.md).

## Post-Command Commit Convention
Stage only files this command created/modified (never `git add .`).
Write the message to `docs/.output/.commit-msg`, then run `node .claude/core/commit.js`.
