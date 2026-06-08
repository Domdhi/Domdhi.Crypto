# Arena — Pipeline Prove-It Module

**Epic 19 (E19) · First module brief in `docs/app/`**

## Scope

The Arena module validates that the full Domdhi.Crypto pipeline composes
end-to-end without errors and clears the FR-33 per-stage non-degeneracy bar.
It is not an application feature; it is the standing prove-it harness that
confirms the research pipeline ships correctly assembled.

Stages exercised (in order):

1. `db.load_close_series` — load a continuous daily close+volume frame
2. `ta.analyze` — compute all technical indicators and signals
3. `factors.evaluate` over `BUILTIN_FACTORS` — evaluate the full 67-factor menu
   (62 close+volume + 5 OHLCV high/low factors via `db.load_ohlcv_daily`)
4. `engine.run_backtest` — run the look-ahead-safe event-loop backtest
5. `digest.build_digest` — render an offline Markdown signal brief

## Key Files

| Path | Role |
|------|------|
| `tests/test_pipeline_e2e.py` | Automated mocked e2e test (the standing guarantee) |
| `src/domdhi_crypto/shared/db.py` | Stage 1: `load_close_series` |
| `src/domdhi_crypto/signals/ta.py` | Stage 2: `analyze` |
| `src/domdhi_crypto/signals/factors.py` | Stage 3: `evaluate`, `BUILTIN_FACTORS` |
| `src/domdhi_crypto/backtest/engine.py` | Stage 4: `run_backtest`, `SignalRule` |
| `src/domdhi_crypto/report/digest.py` | Stage 5: `build_digest` |

## Dependencies

- `requests` / `pandas` / `numpy` (core 3-dep, ADR-001)
- `sqlite3` (stdlib)
- No new dependencies introduced by this module

---

## Real-Data Run Procedure

**This is an OPERATOR step.** It requires:
- A real `config.local.json` containing a CoinGecko API key under `"api_key"`
- Active network access to `api.coingecko.com`
- The client's polite 2-second inter-request pauses (built into `coingecko.py`)

CI and `/run-todo` cannot perform this run. The automated guarantee is
`tests/test_pipeline_e2e.py` (network-mocked, always runnable).

### Exact CLI sequence (BTC + ETH, 365-day window)

```bash
# 1. Initialise the database (idempotent — safe to re-run)
domdhi-crypto init

# 2. Ingest 365 days of price history for both coins
domdhi-crypto ingest --days 365

# 3. Run TA analysis
domdhi-crypto ta BTC
domdhi-crypto ta ETH

# 4. Evaluate the full factor menu
domdhi-crypto factors BTC
domdhi-crypto factors ETH

# 5. Run the backtest
domdhi-crypto backtest BTC
domdhi-crypto backtest ETH

# 6. Render the offline digest
domdhi-crypto digest
```

The coins list lives in `coins.local.json` (separate from `config.local.json`,
which holds only `api_key` + `tier`). Its `"coins"` array must include at minimum:

```json
[
  {"id": "bitcoin",  "symbol": "BTC", "name": "Bitcoin"},
  {"id": "ethereum", "symbol": "ETH", "name": "Ethereum"}
]
```

---

## FR-33 Non-Degeneracy Bar

An operator confirming a live run checks each stage against this checklist:

- [ ] **Stage 1 — load_close_series**: frame is non-None, non-empty,
  `index.is_monotonic_increasing`, all closes finite, `close.nunique() > 1`,
  `len(frame) >= 200`.
- [ ] **Stage 2 — ta.analyze**: dict returned with finite `price` and `rsi`,
  `n_days >= 200`, `signals` list non-empty.
- [ ] **Stage 3 — factors.evaluate**: the set of BUILTIN_FACTORS yields at least
  one pd.Series that is finite and non-constant (varying `nunique() > 1` after
  `dropna()`). Some factors raise ValueError for missing columns (ATR, etc.) —
  that is expected, documented behaviour.
- [ ] **Stage 4 — engine.run_backtest**: `equity_curve` is a non-empty pd.Series
  with monotonic DatetimeIndex and all-finite values; `summary` contains
  `total_return`, `total_realized_return`, `win_rate`, `max_drawdown`, all finite.
- [ ] **Stage 5 — digest.build_digest**: returns a non-empty `str` starting
  with `# ` (the dated Markdown header).

---

## Recorded Run

**Status: COMPLETE — live run performed 2026-06-07.**

| Field | Value |
|-------|-------|
| Date | 2026-06-07 |
| Provider / tier | CoinGecko, **demo** tier |
| Coin set | XRP, BTC, ETH, SOL, HYPE, NEAR, LINK (7 non-stable) + USDC (stable, skipped) |
| Window | `ingest --days 365` (366 daily rows/coin after gap-fill) |
| Ingest | Live fetch succeeded in ~32s (snapshot + 365 price rows + 92 OHLC candles per coin) |

### Per-stage result (FR-33 bar)

| Stage | Result | Evidence |
|-------|--------|----------|
| 1 — `load_close_series` | ✅ PASS | 366 rows/coin, monotonic daily index, finite, varying |
| 2 — `ta.analyze` (BTC) | ✅ PASS | price $62,586.75, RSI 22.8, n_days 366, signals fired (oversold / bear regime / death cross) |
| 3 — `factors` (BTC) | ✅ PASS | ranked IC/ICIR table, finite varying values (e.g. `mean_reversion_20` ICIR 1.03) |
| 4 — `backtest` (BTC) | ✅ PASS | 18 trades, equity curve populated, summary finite (total -2.85%, maxDD -25.19%) |
| 5 — `digest` | ✅ PASS | non-empty Markdown, `## Triggered Signals` for XRP/BTC/… |

**No findings** — every stage cleared the bar on real data. (The 365-day window is a down market;
the negative buy-and-hold returns below are real, not a defect.)

### Arena headline (the "prove it" result)

`domdhi-crypto arena <SYM>` (`src/domdhi_crypto/backtest/arena.py`) over the same 365-day real history, cortex = `rsi_centered` (RSI−50,
in>0/out<0), baselines = buy-and-hold + `price_vs_sma50`:

| Symbol | Cortex | Buy-and-hold | Rule (sma50) | Cortex vs B&H |
|--------|-------:|-------------:|-------------:|--------------:|
| BTC | **+2.06%** | −40.06% | −13.38% | **+42.11 pp** |
| ETH | **+33.38%** | −34.56% | −0.02% | **+67.94 pp** |

The momentum cortex sidestepped most of the year's drawdown and beat buy-and-hold by a wide margin
on both. **But BTC/ETH alone overstate the case** — see the full cross-section below.

### Cost + cross-section stress test (all 7 coins, 2026-06-07)

Same cortex/baselines, run over every non-stable coin, with and without realistic friction:

| Scenario | Cortex beats B&H | Mean cortex | Mean B&H | Mean edge |
|----------|:----------------:|------------:|---------:|----------:|
| zero-cost | 6/7 | +10.96% | −22.27% | +33.2 pp |
| 10 bps slip + 0.1% fee | 6/7 | +3.60% | −22.27% | +25.9 pp |

**What this actually says (read before trusting the headline):**
1. **The relative edge survives costs** — still 6/7 coins, mean edge only drops ~7 pp under friction.
2. **It's downside protection, not alpha.** The cortex "wins" mostly by *losing less* in a bear year
   (B&H mean −22%). Its own absolute return under costs is a modest +3.6% mean, and it is **negative on
   4/7 coins** (XRP −3.2%, BTC −2.3%, SOL −8.0%, LINK −31.2%).
3. **It lags in uptrends — the HYPE counterexample.** HYPE was the one coin that rose (B&H +77%); the
   cortex returned +44% under costs and *underperformed B&H by −33 pp* because momentum exits cut the
   rally short. A defensive momentum strategy is regime-dependent by construction.
4. **Still in-sample, single-factor, no walk-forward.** This is a *working harness + a regime-consistent
   signal*, **not** validated out-of-sample edge. Next probes: walk-forward / out-of-sample splits,
   a multi-factor cortex, and per-coin regime tagging.

**Standing automated guarantee** (re-runnable any time, no network):

```bash
.venv/bin/pytest tests/test_pipeline_e2e.py -q
```
