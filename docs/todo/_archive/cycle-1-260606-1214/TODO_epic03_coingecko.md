# TODO — Epic 3: CoinGecko Client

**Parent:** [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
**Phase:** 1 — Data & Core Ingestion
**Status:** Complete (shipped)
**Stories:** E3-S1, E3-S2
**Last Updated:** 2026-06-06

---

## Executive Summary

Epic 3 is the system's only outbound trust boundary: the HTTP client that talks to CoinGecko. It wires the correct host and authentication header from the configured tier, paces and retries requests so a free-tier key survives rate limits and transient blips, and refuses to run with missing or placeholder credentials. Everything downstream (ingest, TA, dashboard, reports) consumes data this client pulls — but no other module reaches the network.

This epic is **brownfield**: both stories are already implemented at commit `ad85772`, covered by `test_coingecko.py`, and green. The checklist below records the shipped contract for traceability, not for re-implementation. A build wave that picks up this file should treat it as a verification/no-op unless a regression surfaces.

### Key Deliverables

- `coingecko.py` — demo/pro tier host + auth-header wiring driven by the `tier` field, defaulting to demo when absent.
- 429 backoff with bounded retries plus a fixed inter-call pause, so ingest stays inside the free-tier rate limit and recovers from transient 429s rather than failing hard or silently.
- Fail-fast credential loading from `config.local.json` (the credential side of config loading), so first-run setup mistakes produce an actionable fix-it message instead of a traceback.

---

## Optimization Summary

The two stories are sequenced E3-S1 → E3-S2: tier wiring must establish the host, session, and header surface before backoff/pacing layers retry behavior over the request path. Both own distinct, non-overlapping function surfaces within the single physical file `coingecko.py` (E3-S1 owns the constructor and public endpoint methods; E3-S2 owns the private `_get` retry surface), so the split is clean. Credential loading (`load_config`) is owned upstream by E1-S2 in the same file and is a precondition for this epic, not part of it. Because all three are shipped/inert, the shared file carries no live-wave conflict.

---

## Execution Log

| Date | Story | Action | Outcome |
|------|-------|--------|---------|
| (pre-`ad85772`) | E3-S1 | Implemented tiered demo/pro client wiring | Shipped, covered by `test_coingecko.py` |
| (pre-`ad85772`) | E3-S2 | Implemented 429 backoff + polite pacing | Shipped, covered by `test_coingecko.py` |
| 2026-06-06 | — | Recorded epic checklist for traceability | Both stories marked Complete (shipped) |

---

## Key Decisions

- **Tier drives wiring, demo is the default.** Absent `tier` falls back to demo host + `x-cg-demo-api-key`, so a first-time free-tier user needs no extra configuration.
- **`requests` imported lazily inside `__init__`.** Keeps import-time side effects out of the module graph and honors the portability/privacy posture (no network library pulled in until a client is actually constructed).
- **Retries raise rather than return `None`.** Exhausting the 429 retry budget surfaces a real failure to the caller (ingest's per-coin isolation handles it) instead of masking it as empty data.
- **Pacing is a fixed pause on every 2xx.** Politeness is unconditional and verifiable against a mocked clock, not an adaptive heuristic.

---

## AI Task Management Protocol

- Work one story at a time, top to bottom; respect the E3-S1 → E3-S2 dependency edge.
- Each Acceptance Criterion is a contract — verify it, do not reinterpret it.
- This epic is shipped/inert. Do not re-implement. If a task is unchecked, that is a regression signal: investigate before acting.
- Keep this file's task state and the backlog's story status in sync.

### Key Legend

- `[x]` — done / shipped and verified
- `[ ]` — not done (for a shipped epic, an unchecked box means a regression to investigate)
- `[~]` — in progress
- `[!]` — blocked

---

## Context

Epic 3 lives in **Phase 1 (Data & Core Ingestion)** and sits between Phase 0's foundation (paths, config, schema) and Epic 4's ingest orchestration. It depends on E1-S2 (fail-fast config loading provides the credentials the client authenticates with) and unblocks E3-S2's retry layer plus, cross-epic, E4-S3's per-coin ingest. The client is the single point in the codebase that crosses the network boundary; this concentration is deliberate and keeps the privacy/data-locality story auditable.

---

## Story E3-S1: Tiered demo/pro client wiring

- **Dependencies:** E1-S2
- **Unblocks:** E3-S2, E4-S3 (cross-epic)
- **Track:** Data / Core Ingestion
- **Domain:** Backend
- **Estimate:** M

**As a** self-custody technical holder,
**I want** the client to wire the correct host + auth header from my `tier`,
**So that** both free-demo and pro keys work without code changes.

### Acceptance Criteria

- Given `tier: "demo"`, When a `CoinGecko` client is constructed, Then `base` is the demo host and the session carries `x-cg-demo-api-key`. *(FR-5, test_coingecko)*
- Given `tier: "pro"`, When constructed, Then `base` is the pro host with `x-cg-pro-api-key`.
- Given `tier` absent, When constructed, Then it defaults to demo wiring; `requests` is imported lazily inside `__init__`. *(NFR-PR3)*

### Tasks

- [x] Construct `CoinGecko` with a tier-selected base host and authenticated session
- [x] Wire the demo host + `x-cg-demo-api-key` header for `tier: "demo"`
- [x] Wire the pro host + `x-cg-pro-api-key` header for `tier: "pro"`
- [x] Default to demo wiring when `tier` is absent
- [x] Import `requests` lazily inside `__init__` (no module-level network import)
- [x] Expose the `markets` / `market_chart` / `ohlc` endpoint methods over the wired session
- [x] Cover tier wiring (demo, pro, default) in `test_coingecko.py`

---

## Story E3-S2: Rate-limit backoff and polite pacing

- **Dependencies:** E3-S1
- **Unblocks:** E4-S3 (cross-epic — reliable ingest under rate limits)
- **Track:** Data / Core Ingestion
- **Domain:** Backend
- **Estimate:** M

**As a** self-custody technical holder,
**I want** transient 429s retried with backoff and a fixed inter-call pause,
**So that** ingest stays within the free-tier rate limit and survives blips.

### Acceptance Criteria

- Given the API returns 429 then 200, When `_get` is called, Then it sleeps, retries, and returns the 200 payload. *(FR-6, NFR-R2, test_coingecko)*
- Given 429 on every attempt, When `_get` exhausts 4 retries, Then it raises (no silent `None`).
- Given a 2xx response, When `_get` returns, Then a `pause`-length sleep has occurred (verifiable with a mocked clock). *(NFR-PF2)*

### Tasks

- [x] Implement `_get` with bounded 429 retry and backoff sleep between attempts
- [x] Return the 200 payload after a 429→200 sequence
- [x] Raise (no silent `None`) when 4 retries are exhausted on persistent 429
- [x] Apply a fixed `pause`-length sleep on every successful (2xx) response
- [x] Cover the 429 retry path and pacing in `test_coingecko.py` with a mocked clock

---

## Validation

- **Build / Lint:** `ruff check src tests` — passes clean (line 110, py311, rules E/F/W/I/UP/B).
- **Test:** `pytest` — `test_coingecko.py` covers tier wiring (demo/pro/default host + header) and the 429 retry/pacing path. Network is mocked; no live calls.

---

## Work Document References

- Backlog (source of truth): [_backlog.md](./_backlog.md) — Phase 1, Epic 3
- Client source: `src/domdhi_crypto/coingecko.py`
- Tests: `tests/test_coingecko.py`
- Credential example: `config.example.json`

---

## Dependencies to Next

- **Epic 4 (Ingest Orchestration)** consumes this client. E4-S3 (per-coin failure isolation + stablecoin skip) depends on E3-S1 to drive history fetches and relies on E3-S2's backoff so one coin's rate-limit blip does not abort the whole run.
- No Phase 4 (open) story touches `coingecko.py`; this epic is inert with respect to the live build wave.
