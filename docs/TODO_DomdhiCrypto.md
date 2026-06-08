# Implementation Index — Domdhi.Crypto (Cycle 3 · See It & Prove It)

| Attribute | Value |
|-----------|-------|
| **Project** | Domdhi.Crypto |
| **Generated** | 2026-06-06 (via `/evolve` cycle 2→3) |
| **Source of truth** | archived — [todo/_archive/cycle-3-260607-1854-see-it-prove-it/_backlog.md](todo/_archive/cycle-3-260607-1854-see-it-prove-it/_backlog.md) |
| **Status** | ✅ Cycle 3 CLOSED & ARCHIVED (2026-06-07) — Epics 18 + 19 + 20 all shipped (100%). **Cycle 4 not yet planned** — run `/evolve` to re-plan from evidence. |
| **Scope** | 3 phases · 3 epics · 13 stories (13 done · 0 todo) · +1 deferred epic (E17) |

> **This cycle is closed.** It is kept as a standing index; the working backlog + per-epic checklists were archived (cleanup-only `/evolve`, no cycle-4 re-plan). See the close-out record: [todo/_archive/cycle-3-260607-1854-see-it-prove-it/_cycle-summary.md](todo/_archive/cycle-3-260607-1854-see-it-prove-it/_cycle-summary.md).
>
> **Prior cycles archived:** Cycle 3 → [todo/_archive/cycle-3-260607-1854-see-it-prove-it/](todo/_archive/cycle-3-260607-1854-see-it-prove-it/) · Cycle 2 → [todo/_archive/cycle-2-260606-2135-decision-cortex/](todo/_archive/cycle-2-260606-2135-decision-cortex/) · Cycle 1 → [todo/_archive/cycle-1-260606-1214/](todo/_archive/cycle-1-260606-1214/).

---

## Phase Map

| Phase | Name | Goal | Epics | Stories | Done | Status |
|-------|------|------|-------|---------|------|--------|
| 8 | Surface It (lead) | Surface ledger/risk/factors/backtest in the offline dashboard via vendored uPlot (ADR-009) | 1 (18) | 5 | 5 | ✅ done |
| 9 | Prove It | Run the cortex on real data; paper-trade vs buy-and-hold (the "walk" rung) | 1 (19) | 3 | 3 | ✅ done |
| 10 | Harden It | Finish factor port; provider abstraction; stablecoin guard; ledger validation | 1 (20) | 4 | 4 | ✅ done |
| — | Deferred | Gated live execution adapter (the distant "run" rung) | 1 (17) | — | — | 🅿️ deferred |
| **Total (active)** | | | **3** | **12** | **12** | **✅ 12 done · 0 todo** |

---

## Epic Index

| Epic | Title | Stories | Status | Checklist |
|------|-------|---------|--------|-----------|
| 18 | Decision Dashboard | 5 | ✅ done (2026-06-06) | [_archive/cycle-3…/TODO_epic18_decision-dashboard.md](todo/_archive/cycle-3-260607-1854-see-it-prove-it/TODO_epic18_decision-dashboard.md) |
| 19 | Alpha Arena for one | 3 | ✅ done (2026-06-07) | [_archive/cycle-3…/TODO_epic19_alpha-arena.md](todo/_archive/cycle-3-260607-1854-see-it-prove-it/TODO_epic19_alpha-arena.md) |
| 20 | Hardening & Debt | 4 | ✅ done (2026-06-07) | [_archive/cycle-3…/TODO_epic20_hardening-debt.md](todo/_archive/cycle-3-260607-1854-see-it-prove-it/TODO_epic20_hardening-debt.md) |
| 17 | Gated Live Execution Adapter | — | 🅿️ deferred (Won't, this version) | — |

> **ID note:** epic numbers continue across cycles (cycle 1 ended at 11, cycle 2 at 16). Cycle 3 starts at 18; **Epic 17 is reserved** for the deferred execution adapter. Per just-in-time breakdown, only the **lead** epic (18) is materialized into a runnable TODO now; Epics 19–20 are broken down when reached (`/create:project-epics-todo` then `/todo`, or `/todo` with no arg to auto-resolve the next epic).

---

## Cross-Epic Dependencies

The structure is linear by phase: surface (everything to show already shipped in cycle 2) → prove (needs the cortex, done) → harden (independent debt). The only intra-cycle hard dep is the dashboard's vendored-uPlot root and the arena's real-data gate.

| Dependency | Type | Reason |
|------------|------|--------|
| 18-S2…S5 → 18-S1 | hard | Panels render through the vendored uPlot substrate + dashboard wiring |
| 18-S2…S5 | shared-file | All touch `dashboard.py` — sequence or use explicit section ownership, not naive parallel |
| 19-S2 → 19-S1 | hard | The arena runs only after the pipeline is validated on real data |
| 19 → cycle 2 | hard (satisfied) | Reuses `backtest/` + `decision.py` (shipped) |
| 20-S1…S4 | parallel-safe | Own distinct files (`factors.py`, `coingecko.py`, `cli.py`, `ledger.py`) |

---

## Build Order (suggested waves)

> **Status:** ✅ Cycle 3 delivered (all waves shipped) and archived. The waves below are the as-built record; the working checklists now live in the cycle-3 archive.

1. **Wave 1 (lead):** E18-S1 (vendored uPlot substrate + dashboard wiring) — the dependency root.
2. **Wave 2:** E18-S2 (NAV+P/L) · E18-S3 (risk) · E18-S4 (signals) · E18-S5 (backtest curve) — sequence on the shared `dashboard.py`.
3. **Wave 3:** E19-S1 (real-data run) → E19-S2 (arena).
4. **Wave 4 (parallel debt):** E20-S1 (factor port) · E20-S2 (provider) · E20-S3 (stablecoin guard) · E20-S4 (ledger validation).

**Cross-cutting:** record the vendored uPlot version/source/license next to the blob (ADR-009); keep the `pandas-ta`-absent CI guard; keep the "DO NOT COMMIT — orchestrator owns commits" line in dispatch prompts (cycle-2 retro).

---

## Related Documents
- Backlog (archived): [todo/_archive/cycle-3-260607-1854-see-it-prove-it/_backlog.md](todo/_archive/cycle-3-260607-1854-see-it-prove-it/_backlog.md)
- Cycle 3 close-out summary: [todo/_archive/cycle-3-260607-1854-see-it-prove-it/_cycle-summary.md](todo/_archive/cycle-3-260607-1854-see-it-prove-it/_cycle-summary.md)
- Brief: [_project-brief.md](_project-brief.md) · PRD: [_project-requirements.md](_project-requirements.md)
- Architecture (carried forward; ADR-009 added): [_project-architecture.md](_project-architecture.md)
- Feature ideas (bridges to cycle 4): [todo/_feature-ideas.md](todo/_feature-ideas.md)
- Cycle 2 archive: [todo/_archive/cycle-2-260606-2135-decision-cortex/](todo/_archive/cycle-2-260606-2135-decision-cortex/)
