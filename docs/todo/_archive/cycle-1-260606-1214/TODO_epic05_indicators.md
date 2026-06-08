# TODO — Epic 5: Indicators & Signals

**Parent:** [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
**Phase:** 2 — Technical Analysis
**Status:** Complete (shipped)
**Stories:** E5-S1, E5-S2
**Last Updated:** 2026-06-06

---

## Executive Summary

Epic 5 is the analytical heart of Domdhi.Crypto: the layer that turns a gap-filled daily close series into auditable indicator values and then into plain-language buy/sell/hold signals. It is **brownfield and already shipped** — the code exists at commit `ad85772`, lives in `src/domdhi_crypto/ta.py`, and is covered by `tests/test_ta.py`. This checklist records the epic for traceability; every task is checked because the capability is in the tree and green, not because there is open work.

The epic delivers on the project's defining constraint: the math is **hand-rolled in pure pandas/numpy**, with no `pandas-ta` and no internal imports. That keeps the indicators verifiable against textbook references and keeps the dependency surface portable across Python 3.11/3.12/3.13. Partial windows return `NaN` rather than fabricated values, so a coin with too little history never produces a misleading signal.

### Key Deliverables

- **`ta.py` indicator math** — Wilder's RSI, MACD (line/signal/histogram), Bollinger Bands (mid/upper/lower/%B), ATR, SMA, and annualized volatility, each implemented in pure pandas/numpy with NaN on under-window positions.
- **`analyze()` / `_signals()` signal layer** — converts the latest indicator values into per-coin readouts: RSI 70/30 overbought/oversold/neutral, MACD histogram momentum, SMA200 bull/bear regime, and golden-cross / death-cross (SMA50 vs SMA200) calls.
- **SMA200 partial-data guard** — when fewer than 200 days are available, `sma200` is `None` and every SMA200-dependent signal is omitted rather than computed on incomplete data.

### Optimization Summary

E5-S1 is an **L** story — the only non-S/M unit in this epic. The size flags genuine unknowns: matching independent textbook references within tolerance for six separate indicators is where the correctness risk concentrated. It was kept whole (not split) because the indicators share the same import-graph contract and the same verification harness; splitting per-indicator would have multiplied test scaffolding without isolating real risk. E5-S2 (M) was correctly sequenced after E5-S1 — signals are a thin readout over indicator outputs and could not be validated until the underlying math was pinned.

---

## Execution Log

| Date | Event |
|------|-------|
| (pre-`ad85772`) | E5-S1 indicator math implemented in `ta.py` and verified against textbook references in `test_ta.py`. |
| (pre-`ad85772`) | E5-S2 `analyze()`/`_signals()` layer implemented atop E5-S1; regime + cross + RSI text pinned. |
| `ad85772` | Epic shipped as part of the working tree; 12 `test_ta.py` tests passing within the 27-test suite. |
| 2026-06-06 | Per-epic checklist generated for traceability; all tasks confirmed `[x]`. |

---

## Key Decisions

- **Pure pandas/numpy, no `pandas-ta`** (ADR-001) — auditability and portability over convenience. `ta.py` imports only `numpy`/`pandas` and nothing internal, so it sits as a leaf in the import DAG.
- **NaN on partial windows** — under-window positions return `NaN`; no fabricated values leak into signals.
- **SMA200 is `None` below 200 days** — regime and cross signals are omitted, not approximated, when history is too short.
- **Signals are a thin readout layer** — `_signals()` consumes the latest indicator values only; all math stays in the indicator functions, keeping the two stories cleanly separated within one file.

---

## AI Task Management Protocol

- This is a **brownfield, shipped** epic. Tasks are marked `[x]` because the capability exists and is covered by passing tests — not as live work to dispatch.
- A `/do` wave that selects an E5 story should treat it as **verification / no-op** unless a regression is found.
- Acceptance Criteria below are **verbatim** from the backlog source of truth (`docs/todo/_backlog.md`). Do not paraphrase or edit them here; the backlog is canonical.
- Both stories share `ta.py` but own **distinct, non-overlapping function surfaces** (E5-S1 owns the indicators; E5-S2 owns `analyze`/`_signals`). The overlap is tolerated only because both are inert/shipped — it is never a live parallel-wave concern.

### Key Legend

- `[x]` — Done / shipped and verified by tests
- `[ ]` — Open / not yet implemented
- `(Backend)` `(Test)` `(Database)` `(Config)` `(DevOps)` `(Frontend)` — domain tag routing the implementation agent

---

## Context

Epic 5 sits in **Phase 2 (Technical Analysis)**. It depends downstream on the Phase 0 storage layer — specifically the gap-filled daily close series from E2-S3 — and feeds the Phase 3 presentation layer (the offline HTML dashboard E6-S1 and the terminal reports E7-S1/E7-S2 all render the signals this epic produces). The indicator functions themselves (E5-S1) are a graph leaf with no internal dependencies, which is why they could be built and verified first.

---

## Story E5-S1: Hand-rolled auditable indicators

- **Dependencies:** None
- **Unblocks:** E5-S2 (signal generation), E6-S1 (dashboard), E7-S1 / E7-S2 (terminal reports)
- **Track:** Technical Analysis
- **Domain:** (Backend)
- **Estimate:** L

**As a** self-custody technical holder,
**I want** RSI/MACD/Bollinger/ATR/SMA/volatility implemented in pure pandas/numpy,
**So that** the math is auditable and verifiable against textbook references, not a black box.

### Acceptance Criteria

- Given a known close series, When `rsi()` is computed, Then it matches an independent Wilder's-RSI reference within tolerance. *(FR-11, NFR-Q3, test_ta)*
- Given a known series, When `macd()`/`bollinger()` are computed, Then line/signal/histogram and mid/upper/lower/%B match textbook references within tolerance.
- Given a series shorter than an indicator's window, When computed, Then under-window positions are `NaN` (no fabricated values).
- Given the import graph, When `ta.py` is imported, Then it imports only `numpy`/`pandas` and nothing internal; `pandas-ta` is absent. *(NFR-M1, NFR-PO2, ADR-001)*

### Tasks

- [x] (Backend) Implement Wilder's RSI in `rsi()` over the close series
- [x] (Backend) Implement MACD line/signal/histogram in `macd()`
- [x] (Backend) Implement Bollinger Bands mid/upper/lower and %B in `bollinger()`
- [x] (Backend) Implement ATR in `atr()`
- [x] (Backend) Implement SMA and `annualized_vol()` volatility helper
- [x] (Backend) Add the shared float/format helper `_f` used across indicators
- [x] (Backend) Return `NaN` for under-window positions across all indicators (no fabricated values)
- [x] (Backend) Keep `ta.py` imports limited to `numpy`/`pandas`, no internal imports, no `pandas-ta`
- [x] (Test) Verify `rsi()`/`macd()`/`bollinger()` against independent textbook references within tolerance in `test_ta.py`

---

## Story E5-S2: Signal generation rules

- **Dependencies:** E5-S1, E2-S3
- **Unblocks:** E6-S1 (dashboard), E7-S1 / E7-S2 (terminal reports)
- **Track:** Technical Analysis
- **Domain:** (Backend)
- **Estimate:** M

**As a** self-custody technical holder,
**I want** `analyze()`/`_signals()` to turn the latest indicators into plain-language calls,
**So that** I get RSI/MACD/regime/cross/Bollinger readouts per coin.

### Acceptance Criteria

- Given SMA50 crossing above SMA200, When `analyze()` runs, Then a "golden cross (50D > 200D)" signal is emitted; below → "death cross". *(FR-12, test_ta)*
- Given price above SMA200, When `analyze()` runs, Then "above 200D SMA (bull regime)" is emitted; below → "bear regime".
- Given fewer than 200 days, When `analyze()` runs, Then `sma200` is `None` and SMA200-dependent signals are omitted (not computed on partial data).
- Given RSI of 75 / 25 / 50, When signals are built, Then text is "overbought" / "oversold" / "neutral" respectively.

### Tasks

- [x] (Backend) Implement `analyze()` to assemble the latest indicator values into a result object
- [x] (Backend) Implement `_signals()` to map latest values to plain-language calls
- [x] (Backend) Emit golden-cross / death-cross from SMA50 vs SMA200 relationship
- [x] (Backend) Emit bull/bear regime from price vs SMA200
- [x] (Backend) Set `sma200` to `None` and omit SMA200-dependent signals below 200 days
- [x] (Backend) Map RSI 70/30 thresholds to overbought / oversold / neutral text
- [x] (Backend) Surface MACD histogram momentum in the signal readout
- [x] (Test) Cover golden/death cross, regime, partial-data omission, and RSI thresholds in `test_ta.py`

---

## Validation

- **Build / Lint:** `ruff check src tests` — passes clean (rules `E/F/W/I/UP/B`, line 110, target py311).
- **Test:** `pytest` — `tests/test_ta.py` contributes 12 tests covering indicator correctness (against textbook references), NaN-on-partial-window behavior, regime/cross signal text, and RSI threshold mapping. All green within the 27-test suite.

---

## Work Document References

- Backlog (source of truth): [../todo/_backlog.md](../todo/_backlog.md) — Epic 5 stories E5-S1, E5-S2
- PRD: [../_project-requirements.md](../_project-requirements.md) — FR-11, FR-12, NFR-Q3
- Architecture: [../_project-architecture.md](../_project-architecture.md) — ADR-001 (no `pandas-ta`)
- Source: `src/domdhi_crypto/ta.py`
- Tests: `tests/test_ta.py`

---

## Dependencies to Next

- **E6-S1 (Offline HTML Dashboard)** consumes `analyze()` output to render per-coin charts, the RSI strip, and signal badges.
- **E7-S1 (Per-coin TA terminal readout)** and **E7-S2 (Portfolio report)** print the same signals to the terminal.
- No Phase 4 story modifies `ta.py`; this epic is closed and inert.
