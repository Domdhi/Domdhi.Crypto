# Feature Ideas: Domdhi.Crypto

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Last Updated** | 2026-06-06 |

---

## How to Use This Document

Living capture of feature ideas across the lifecycle. Ideas flow in from `/brainstorm`, feedback, implementation discoveries, and retros. `/create:project-requirements` and `/create:project-epics` (and `/evolve`'s re-plan) pull from here. Ideas are raw — they need not be approved.

**Priority:** Must / Should / Could / Won't(this version) · **Status:** Idea / Exploring / Accepted / Deferred / Rejected

---

## Strategic direction (cycle 2 pivot — 2026-06-06)

Domdhi.Crypto evolves from a portfolio + TA engine into a **local-first, agent-native crypto *decision cortex*** — the durable, auditable substrate an LLM agent consumes to make and *explain* trading decisions. Settled after surveying prior art:

- **Don't reinvent Ghostfolio** (self-hosted *tracking* — already solved, heavyweight) → keep the ledger thin, just enough position context to weight decisions.
- **Don't reinvent Freqtrade/Jesse/Hummingbot** (*execution/backtesting* engines — mature) → delegate execution; borrow Jesse's look-ahead-bias rigor.
- **The open gap = the LLM decision/attribution layer.** Incumbents are quant/rule engines (FreqAI = classic ML; JesseGPT = coding assistant). Nobody ships an auditable agent that reasons over signals + portfolio context and *cites why*. Our hand-rolled, inspectable TA (ADR-001) is the superpower here.
- **Empirical reality check (nof1 Alpha Arena, Dec 2025):** 4 of 6 frontier LLMs *lost money* trading autonomously. So the product is NOT "an LLM that trades" — it's the infrastructure that makes an agent's decisions *measurable, attributable, and edge-validated before a cent is risked.* Sequence: crawl (decision-support, human pulls trigger) → walk (paper-trade, prove edge vs buy-and-hold) → run (gated live).
- **Borrowable code:** HammerGPT/Hyper-Alpha-Arena (Apache-2.0) — expression-factor registry, IC/ICIR scoring, time-gated event backtester, decision-context prompt contract. ⚠️ It sits on `pandas-ta` (the dep ADR-001 rejects) — borrow the *pattern*, keep hand-rolled pure-numpy primitives.

---

## Ideas

### Category: Signal Substrate (Limb 4)

| # | Idea | Description | Priority | Status | Source |
|---|------|-------------|----------|--------|--------|
| 1 | Expression-factor registry | Factors as declarative strings (`"(close-EMA(close,200))/close"`) over a registry of pure-numpy primitives (extend `ta.py`). Adding a factor = adding a string, not code. Registry metadata (sig/desc/example) doubles as the agent's documented menu. | Must | Accepted | brainstorm / HammerGPT |
| 2 | Time-series + cross-section operators | Add `DELAY`, `TS_*` (SUM/MEAN/STD/MAX/MIN/RANK/CORR/ARGMAX), `DECAYLINEAR`, `LOG_RETURN`, `NORMALIZE`, `ZSCORE` as pure functions — the ~69-fn vocabulary HammerGPT exposes, minus `pandas-ta`. | Must | Accepted | HammerGPT |
| 3 | Port the 64 HammerGPT factor definitions | Lift the Apache-2.0 factor *strings* (trend/momentum/volatility/volume/statistical/composite) as data onto our hand-rolled primitives. | Should | Idea | HammerGPT |
| 4 | Portfolio-level risk | Correlation matrix across holdings, portfolio volatility, beta-to-BTC, max drawdown (pure numpy/pandas, new `risk.py` leaf). | Should | Idea | brainstorm |

### Category: Edge Validation (Limb 2)

| # | Idea | Description | Priority | Status | Source |
|---|------|-------------|----------|--------|--------|
| 5 | IC / ICIR factor scorer | Rank-correlation of factor vs *forward* return; ICIR = trailing mean(IC)/std(IC) over a sliding window. ~tens of lines pure numpy. Answers "does this signal predict anything?" before any trade sim. | Must | Accepted | HammerGPT / Look-Ahead-Bench |
| 6 | Look-ahead-safe backtester | Event-driven sim: `VirtualAccount` + `ExecutionSimulator` (slippage+fees) + a *time-gated* `HistoricalDataProvider` that exposes only bars ≤ event time (the look-ahead guard). Read Look-Ahead-Bench (arXiv 2601.13770) first. | Must | Accepted | HammerGPT / Jesse |
| 7 | By-factor attribution | "Why did the agent win/lose, broken down by factor" — the missing third piece after substrate + backtest. | Should | Idea | HammerGPT (Attribution AI) |

### Category: Agent Decision Interface (Limb 5)

| # | Idea | Description | Priority | Status | Source |
|---|------|-------------|----------|--------|--------|
| 8 | MCP decision interface | Expose signals + portfolio context as a structured MCP tool surface Claude consumes; registry-as-docs gives the agent its factor menu automatically. | Must | Accepted | brainstorm / awesome-trading-agents |
| 9 | Decision-context contract | Prompt shape borrowed from HammerGPT: `{output_format}` (force parseable JSON decision) + `{trigger_context}` (why-now + signal values + position). Event-driven triggers, not continuous poll. | Should | Idea | HammerGPT |

### Category: Output Channel (Limb 3)

| # | Idea | Description | Priority | Status | Source |
|---|------|-------------|----------|--------|--------|
| 10 | Alerts & scheduled digest | `digest`/`check` command + threshold rules; paired with `/schedule` to drop a daily brief (with rationale) into an Obsidian vault. Run-it → tells-you. No server. | Should | Idea | brainstorm |

### Category: Portfolio Context (Limb 1 — trimmed)

| # | Idea | Description | Priority | Status | Source |
|---|------|-------------|----------|--------|--------|
| 11 | Thin transaction/position layer | Just enough to weight decisions: NAV-over-time from the snapshots already stored; optional transaction ledger for derived cost basis. NOT a full tax-lot/rebalancing tracker (that's Ghostfolio's job). Requires schema migrations (DB becomes partial source-of-truth). | Could | Idea | brainstorm / Ghostfolio delta |

### Category: Capstone

| # | Idea | Description | Priority | Status | Source |
|---|------|-------------|----------|--------|--------|
| 12 | "Alpha Arena for one" | Local, offline, reproducible arena where the cortex agent paper-trades vs buy-and-hold + rule strategies, scored with look-ahead-safe backtest + by-factor attribution. The "walk" rung *as the product*. Uncontested: nof1 = hosted/real-money, HammerGPT = Docker+live keys; nobody owns the safe local bench. | Could | Exploring | brainstorm / nof1 |

### Category: Execution (gated, distant)

| # | Idea | Description | Priority | Status | Source |
|---|------|-------------|----------|--------|--------|
| 13 | Gated execution adapter | Delegate paper-then-live orders to Freqtrade/CCXT behind a hard human-in-the-loop gate. Withdrawal-disabled + IP-allowlisted keys, hard caps, kill-switch. The "run" rung — last, not soon. | Won't (this version) | Deferred | brainstorm / nof1 safety |

---

## Parking Lot

- Provider abstraction (`coingecko.py` → pluggable `prices` provider) to de-risk single-vendor coupling (Architecture Risk #2) — enabler before the substrate deepens the dependency.
- Multi-timeframe analysis (weekly resample from daily).
- License decision for the project before lifting Apache-2.0 code (HammerGPT) — keep permissive to allow reuse; avoid pasting GPL/AGPL (Freqtrade/Ghostfolio).
