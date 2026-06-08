# Project Context: Domdhi.Crypto

**Onboarded**: 2026-06-06
**Phase**: Reverse-Engineered
**Tech Stack**: Python 3.11+ src-layout CLI, hatchling, requests/pandas/numpy, SQLite, ruff, pytest

## Quick Reference
- **Architecture**: [docs/_project-architecture.md](_project-architecture.md)
- **Slice layout**: [docs/_slice-architecture.md](_slice-architecture.md) — canonical two-package layout + dependency DAG
- **Context**: this file

## Entry Points
- `domdhi-crypto` console script → `domdhi_crypto.cli:main`
- `python -m domdhi_crypto` → `__main__.py`
- Subcommands: init, ingest, ta, report, dashboard, factors, backtest, digest, mcp, arena

## Build & Test
- **Build/lint**: `ruff check src tests`  (project CI uses `ruff check .`; note: template gate also runs `ruff format --check` + `mypy --strict`, but mypy is NOT installed/declared — see architecture Risks)
- **Test**: `pytest`  (391 unit tests, network mocked; the MCP server-construction test skips without the `[mcp]` extra)

## Key Paths

Two packages ship in one distribution (`pip install domdhi-crypto`):

**Engine — `src/domdhi_crypto/`** (Vertical-Slice sub-packages)
- `src/domdhi_crypto/cli.py` — host / composition root (argparse orchestrator, wires every slice)
- `src/domdhi_crypto/shared/db.py` — SQLite store (idempotent upserts, gap-fill series load, schema migrations)
- `src/domdhi_crypto/shared/paths.py` — data-dir resolver ($DOMDHI_CRYPTO_HOME)
- `src/domdhi_crypto/ingest/coingecko.py` — CoinGecko API client (tiers, 429 backoff)
- `src/domdhi_crypto/signals/ta.py` — hand-rolled RSI/MACD/Bollinger/ATR + signals (pure leaf)
- `src/domdhi_crypto/signals/factors.py` — declarative factor substrate + safe AST evaluator (Epic 12)
- `src/domdhi_crypto/signals/effectiveness.py` — IC/ICIR factor effectiveness (Epic 13)
- `src/domdhi_crypto/portfolio/ledger.py` — NAV + average-cost realized/unrealized P/L (Epic 16)
- `src/domdhi_crypto/portfolio/risk.py` — correlation / vol / beta / drawdown (Epic 16, pure leaf)
- `src/domdhi_crypto/agent/context.py` — JSON-safe agent context snapshot (signals + position + factor menu)
- `src/domdhi_crypto/backtest/` — look-ahead-safe event backtester + arena harness (Epic 13/19)
- `src/domdhi_crypto/report/digest.py` — offline Markdown triggered-signal brief (Epic 15)
- `src/domdhi_crypto/report/dashboard/` — offline single-file HTML package (inline SVG + vendored uPlot, ADR-009)

**Agent layer — `src/domdhi_crypto_mcp/`** (separate top-level package; one-way dep on engine)
- `src/domdhi_crypto_mcp/decision.py` — DECISION_SCHEMA + validate_decision + build_trigger_context (Epic 14)
- `src/domdhi_crypto_mcp/server.py` — FastMCP stdio server; lazy `[mcp]` import (Epic 14, ADR-007)

**Config & CI**
- `pyproject.toml` / `ruff.toml` — packaging + lint config (core 3-dep; optional `[mcp]` extra)
- `.github/workflows/ci.yml` — CI (3.11/3.12/3.13 matrix: ruff check + pytest)
- Git-ignored runtime state: `crypto.db`, `coins.local.json`, `config.local.json`

## Implementation Commands
- `/create:project-brief` — capture the vision when ready
- `/create:project-epics` — break work into implementable stories
- `/review:personalize` — give the specialized agents names
- `/review:code-review` — review code changes
- `/review:qa` — generate tests
- `/review:check-sync` — detect doc drift
- `/review:update-docs` — fix doc drift
- `/review:optimize-agents` — re-align agents with codebase
- `/prime` — reload context in new session
- `/do` — execute a single story
- `/run-todo` — execute a full TODO checklist
- `/end` — save session state
