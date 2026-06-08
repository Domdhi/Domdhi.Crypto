# TODO — Epic 7: Terminal Reports

| Attribute | Value |
|-----------|-------|
| **Parent** | [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md) |
| **Phase** | 3 — Dashboard & Reporting |
| **Epic** | 7 — Terminal Reports |
| **Status** | Complete (shipped) |
| **Stories** | E7-S1, E7-S2 |
| **Last Updated** | 2026-06-06 |

---

## Executive Summary

Epic 7 gives Domdhi.Crypto its browser-free reading surface. Where Epic 6 renders the
single-file offline HTML dashboard, Epic 7 prints the same underlying signals straight
to the terminal — so a self-custody holder can get a fast, no-browser read of one coin
or the whole portfolio from a single command.

Both stories are **brownfield / already-shipped**: the code exists at commit `ad85772`,
works end-to-end, and is covered by the existing pytest suite. This checklist documents
done work for FR traceability and definition-of-done verification — it is **inert** and
should not be re-dispatched as a live build wave unless a regression is found.

### Key Deliverables

- **`cli.py` `ta` subcommand** (E7-S1) — `domdhi-crypto ta <symbol>` prints a fixed-width
  per-coin indicator + signal table (RSI/MACD/Bollinger/regime/cross readouts) and exits
  `0`; fails fast with a "run `domdhi-crypto ingest`" message on an empty DB; omits
  SMA200-dependent signals when fewer than 200 days are available.
- **`cli.py` `report` subcommand** (E7-S2) — `domdhi-crypto report` prints live portfolio
  value, profit/loss, and per-coin signals; counts stablecoin `amount × price` toward total
  value with a `stablecoin` tag; degrades to `n/a` per coin on an empty DB rather than
  crashing.

---

## Optimization Summary

`/review:optimize-backlog` has **not** been run on this backlog. Sequencing here follows
the authoritative phase/wave ordering from the parent index: Epic 7 sits in Phase 3 and
consumes the close series (Epic 2) and signals (Epic 5) already in place. Both stories own
distinct, non-overlapping function surfaces inside the shared `cli.py` file (`cmd_ta`/`fmt`
vs `cmd_report`); because both are shipped/inert there is no live wave conflict.

---

## Execution Log

| Date | Story | Event | Notes |
|------|-------|-------|-------|
| pre-`ad85772` | E7-S1 | Shipped | `ta <symbol>` terminal readout landed with the original pipeline |
| pre-`ad85772` | E7-S2 | Shipped | `report` portfolio readout landed with the original pipeline |
| 2026-06-06 | — | Checklist generated | Recorded for FR traceability; epic marked Complete (shipped) |

---

## Key Decisions

- **Two render surfaces, one signal source.** Terminal reports (Epic 7) and the HTML
  dashboard (Epic 6) both read the same stored series and `analyze()` signals — the
  difference is presentation only, so the two never diverge in logic.
- **Fail-fast, not crash.** `ta` on an empty DB raises a `SystemExit` that tells the user
  to run `ingest`; `report` instead degrades to `n/a` per coin so a partial portfolio still
  prints. The asymmetry is intentional: a single-coin query has nothing to show, while a
  portfolio view should still render the rows it can.
- **Stablecoins count toward value, not signals.** A stablecoin holding contributes
  `amount × price` to total portfolio value but carries a `stablecoin` signal tag rather
  than indicator calls, since pegged assets produce meaningless TA.
- **Shared-file ownership is safe only because inert.** Both stories edit `cli.py` alongside
  shipped Epic 4 stories; this is tolerated solely because none will be re-dispatched as
  live work.

---

## AI Task Management Protocol

- This checklist is the **definition-of-done record** for Epic 7. The source of truth for
  stories and acceptance criteria is [`_backlog.md`](_backlog.md).
- Acceptance criteria below are reproduced **verbatim** from the backlog.
- Because the epic is **shipped/inert**, all task checkboxes are `[x]`. A `/do` wave that
  picks up a story here should treat it as a **verification / no-op** unless a regression is
  found; only then should items be re-opened.
- Do not re-implement shipped behavior. If a regression surfaces, open a new story rather
  than mutating this record.

### Key / Legend

| Symbol | Meaning |
|--------|---------|
| `[x]` | Task complete (shipped & verified) |
| `[ ]` | Task open / not yet done |
| ✅ shipped | Story is live in the codebase, recorded for traceability |
| ⬜ todo | Story is open, genuine build-wave work |
| (Domain) | Implementation domain tag for agent routing |

---

## Context

Epic 7 is the terminal half of Phase 3 (Dashboard & Reporting). It depends on the coin
resolution layer (Epic 4 — `_resolve`/`load_coins`), the signal layer (Epic 5 — `analyze`/
`_signals`), and the gap-filled close series (Epic 2 — `load_close_series`). It produces no
new persisted state: it reads the DB and prints. It is the last shipped epic before the
single open Phase 4 hardening wave (Epic 11), which adds CLI tests and a `--version` path
that touch the same `cli.py` file.

---

## Story E7-S1: Per-coin TA terminal readout

| Field | Value |
|-------|-------|
| **Dependencies** | E4-S2 (coin resolution), E5-S2 (signal rules) |
| **Unblocks** | Browser-free per-coin TA check; complements E6-S1 dashboard view |
| **Track** | Phase 3 — Dashboard & Reporting |
| **Domain** | Backend |
| **Estimate** | S |
| **Status** | Complete (shipped) — ✅ shipped |
| **Files** | `src/domdhi_crypto/cli.py` (`cmd_ta`, `fmt`) |

**As a** self-custody technical holder,
**I want** `ta <symbol>` to print a full indicator + signal table,
**So that** I get a quick no-browser check for one coin.

### Acceptance Criteria

- Given a populated DB, When `domdhi-crypto ta BTC` runs, Then a fixed-width indicator/signal table prints and the process exits `0`. *(FR-14)*
- Given an empty/unpopulated DB, When `ta` runs, Then `SystemExit` tells the user to run `domdhi-crypto ingest` (no traceback). *(FR-10)*
- Given fewer than 200 days, When `ta` runs, Then SMA200-dependent signals are omitted. *(FR-12)*

> **Note:** Same file as E4-S1/S2/S3 and `cmd_report`; owns `cmd_ta`/`fmt` only. Inert/shipped.

### Tasks

- [x] Wire `cmd_ta(symbol)` handler to the `ta <symbol>` argparse subcommand
- [x] Resolve the target coin by id or symbol via `_resolve` (case-insensitive)
- [x] Load the gap-filled close series and run `analyze()` to produce indicators + signals
- [x] Render a fixed-width indicator/signal table via the `fmt` helper and exit `0`
- [x] On an empty/unpopulated DB, raise `SystemExit` instructing the user to run `domdhi-crypto ingest` (no traceback)
- [x] Omit SMA200-dependent signals when fewer than 200 days are available
- [x] Covered by the existing pytest suite (network mocked)

---

## Story E7-S2: Portfolio report terminal readout

| Field | Value |
|-------|-------|
| **Dependencies** | E4-S2 (coin resolution), E5-S2 (signal rules), E2-S3 (gap-filled close series) |
| **Unblocks** | Whole-position glance without the browser; complements E6-S1 dashboard view |
| **Track** | Phase 3 — Dashboard & Reporting |
| **Domain** | Backend |
| **Estimate** | M |
| **Status** | Complete (shipped) — ✅ shipped |
| **Files** | `src/domdhi_crypto/cli.py` (`cmd_report`) |

**As a** self-custody technical holder,
**I want** `report` to print live portfolio value, P/L, and per-coin signals,
**So that** I see the whole position at a glance without the browser.

### Acceptance Criteria

- Given a populated DB and holdings, When `report` runs, Then total value, P/L, and per-coin signals print. *(FR-14)*
- Given a stablecoin holding, When `report` runs, Then its `amount × price` counts toward total value with a `stablecoin` signal tag. *(FR-4)*
- Given an empty DB, When `report` runs, Then it degrades by printing `n/a` per coin rather than crashing.

> **Note:** Owns `cmd_report` only within the shared `cli.py`. Inert/shipped.

### Tasks

- [x] Wire `cmd_report` handler to the `report` argparse subcommand
- [x] Load holdings, resolve each coin, and fetch its latest price + signals
- [x] Compute and print total portfolio value and profit/loss
- [x] Print per-coin signals alongside each holding
- [x] Count stablecoin `amount × price` toward total value with a `stablecoin` signal tag
- [x] On an empty DB, degrade to printing `n/a` per coin rather than crashing
- [x] Covered by the existing pytest suite (network mocked)

---

## Validation

| Gate | Command | Expected |
|------|---------|----------|
| Build / Lint | `ruff check src tests` | Clean (rules `E/F/W/I/UP/B`, line-length 110, py311) |
| Test | `pytest` | All tests pass (≥27, network mocked) |

Both stories are shipped; validation here confirms no regression in `cmd_ta`/`fmt` or
`cmd_report`.

---

## Work Document References

- Backlog (source of truth): [todo/_backlog.md](_backlog.md) — Phase 3 › Epic 7
- Parent index: [TODO_DomdhiCrypto.md](../TODO_DomdhiCrypto.md)
- PRD: [_project-requirements.md](../_project-requirements.md) — FR-14 (terminal reports), FR-4 (stablecoins), FR-10/FR-12
- Architecture: [_project-architecture.md](../_project-architecture.md)
- Sibling Phase 3 epic: Epic 6 — Offline HTML Dashboard ([TODO_epic06_dashboard.md](TODO_epic06_dashboard.md))

---

## Dependencies to Next

- **Phase 4 — Epic 11 (Test & Release Hardening)** touches the same `cli.py` file Epic 7
  owns. **E11-S2** adds a `--version` path and **E11-S3** adds `tests/test_cli.py`; both
  relate to `cli.py` and are sequenced (E11-S3 → E11-S2), never run in the same parallel
  wave. Epic 7's shipped `cmd_ta`/`fmt`/`cmd_report` surfaces are inert during that wave, so
  there is no live conflict — but any future edit to `cli.py` must respect the same
  one-story-per-file-per-wave rule.
- No open work blocks on Epic 7; it is a terminal (leaf) capability of the shipped pipeline.
