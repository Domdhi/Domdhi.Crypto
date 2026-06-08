# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Test suite (`pytest`): indicator math with cross-checks against independent
  textbook RSI/EMA references, idempotent-upsert and gap-fill DB tests, and a
  fully-mocked CoinGecko client test (tier/header wiring + 429 backoff).
- GitHub Actions CI: lint (`ruff`) + tests on Python 3.11, 3.12, 3.13.
- Packaging via `pyproject.toml` (hatchling). Installs a `domdhi-crypto` console
  command; also runnable as `python -m domdhi_crypto`.
- `ruff.toml` and a `pre-commit` config.
- Contributor docs: `CONTRIBUTING.md`, `SECURITY.md`, `CITATION.cff`, issue/PR
  templates.

### Changed
- Restructured into a `src/domdhi_crypto/` package (CLI entry point moved from
  `crypto.py` to `domdhi_crypto.cli`). Root directory is now config/docs only.
- User files (`config.local.json`, `coins.local.json`, `crypto.db`, `dashboard.html`)
  now resolve from the data directory — `$DOMDHI_CRYPTO_HOME` or the current
  working directory — instead of next to the source, so an installed CLI behaves
  correctly.
- `db.load_close_series` now reindexes to a continuous daily range and
  forward-fills `close`, hardening rolling indicators (e.g. SMA200) against
  missing days from the data feed.
- `pandas` import moved to module level in `db.py`.
- `ta ` on a coin flagged `"stable": true` now explains that stablecoins are
  skipped, instead of the generic "no price data" message.
- Replaced `requirements.txt` with `pyproject` dependencies.

## [0.1.0] - 2026-06-05

### Added
- Crypto TA pipeline: CoinGecko ingest → local SQLite → hand-rolled indicators
  (RSI, MACD, SMA 20/50/200, Bollinger + %B, ATR, annualized volatility).
- `init`, `ingest`, `ta`, `report`, and `dashboard` CLI commands.
- Offline, single-file HTML dashboard with inline SVG charts (no server, no CDN).
- MIT license and README with example-data dashboard screenshot.

[Unreleased]: https://github.com/Domdhi/Domdhi.Crypto/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Domdhi/Domdhi.Crypto/releases/tag/v0.1.0
