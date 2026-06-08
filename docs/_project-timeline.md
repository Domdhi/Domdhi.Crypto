# Domdhi.Crypto Project Timeline

*Generated 2026-06-07 — 10 commits, 1 weeks*

<!-- last:4aa0681b20724541daaef6a894b0191d3c0fb295 -->

## Week of Jun 1, 2026

### Sun Jun 7 (10 commits, 45 files)
**Documentation** (9 commits)
- /sweep p7 — timeline refresh + sweep report
- /sweep p5 — agent re-alignment (6 agents updated)
- /run-todo epic20_hardening-debt — final report
- /sweep p1 — code review, 2 findings (0C/0M/1m/1nit)
- /sweep p2 — retro cycle 3 (consolidated)
- /sweep p3 — applied 4 doc-drift fixes, 3 memories written
- /sweep p5 — agent re-alignment (4 agents updated)
- /sweep p5b — 0 skill-evolution proposals staged (E20 signal is dispatch-gap)
- /sweep p6 — defrag: 1 merge, 2 cross-refs, 0 splits (42 -> 42)

**Features** (1 commit)
- Epic 20 — hardening & debt + walk-forward validation (5 stories)


---

## Week of Jun 1, 2026

### Sat Jun 6 (2 commits, 3 files)
- docs: /sweep p7 — timeline refresh + final report
- docs: /end — Epic 18 (Decision Dashboard) shipped + full /sweep

### Sun Jun 7 (16 commits, 106 files)
**Fixes** (1 commit)
- auto-migrate DB on connect so read-only commands work on legacy DBs

**Documentation** (6 commits)
- /todo — create TODO for epic19_alpha-arena (3 stories)
- E19-S1 — record live real-data pipeline run (FR-33 closed)
- arena — full-universe + cost stress test corrects BTC/ETH headline
- /review:security — first audit (STRONG, 0 critical/major, ship-ready)
- /todo — create TODO for epic20_hardening-debt (5 stories)
- /sweep p2-3 — sync all docs to the VSA slice architecture

**Chores** (4 commits)
- sync guardrail — drop git-amend nudge
- sync .claude template 4.67 → 4.69 (merge)
- sync .claude template → v4.70 (merge)
- sync .claude template to v4.72

**Features** (2 commits)
- wave 1 — E19-S1, E19-S2 arena core + pipeline e2e
- wave 2 — E19-S3 arena CLI + Epic 19 complete

**Refactoring** (3 commits)
- extract agent layer into separate domdhi_crypto_mcp package
- slice engine into Vertical-Slice sub-packages
- split report/dashboard.py into a package


---

## Week of Jun 1, 2026

### Sat Jun 6 (21 commits, 78 files)
**Documentation** (15 commits)
- /sweep p7 — health PASS (lint 70, conformance ok, 0 broken refs) + timeline refresh
- /sweep — final report (Epic 15/16 sweep complete)
- ADR-009 — vendored uPlot for dashboard charts (amends ADR-004)
- reconcile cycle-2 tracking with shipped reality (pre-/evolve)
- /review:feedback — Domdhi.Crypto template-performance report
- /review:check-readiness — CONCERNS, 11 issues found
- /review:check-readiness remediation — fix 7 safe drift items
- /review:check-readiness remediation — fix 4 PRD judgment items
- /review:feedback digest refresh — fleet rollup sync (v4.67)
- /run-todo epic18_decision-dashboard — final report + handoff
- /sweep p1 — code review, 2 findings (0C/0M/1 MINOR/1 NIT)
- /sweep p2 — retro epic18 decision-dashboard
- /sweep p5 — agent re-alignment (1 agent updated)
- /sweep p5b — 0 skill-evolution proposals staged (no new evidence)
- /sweep p6 — defrag: 0 merges, 0 splits, 4 cross-refs (36→36)

**Features** (4 commits)
- /evolve — cycle 2 archived, cycle 3 planned (See It & Prove It)
- wave 1 — E18-S1 vendored uPlot substrate + panel seam
- wave 2 — E18-S2..S5 dashboard decision panels
- /sweep p3 — applied retro recs (2 code fixes, 3 doc-drift, 2 memories)

**Chores** (2 commits)
- sync .claude template 4.64 -> 4.67
- track uv.lock


---

## Week of Jun 1, 2026

### Sat Jun 6 (20 commits, 114 files)
**Documentation** (12 commits)
- /sweep p7 — health PASS (lint 70, conformance ok) + timeline refresh
- /sweep — final report (Epic 14 sweep complete)
- /todo — create TODO for Epic 15 alerts-digest (2 stories)
- /review:feedback — Domdhi.Crypto template-performance report
- /run-todo epic15-alerts-digest — final report + handoff
- /todo — create TODO for epic16-portfolio-context (3 stories)
- reconcile master index — Epics 12-15 done, Epic 16 active
- /run-todo epic16-portfolio-context — final report
- /sweep p1 — code review, 8 findings (0C/0M/5m+3nit)
- /sweep p5 — agent re-alignment (2 agents updated: architect ADR-007/008, code-reviewer risk map +ledger/risk)
- /sweep p5b — 0 new skill proposals (Epic 16 signal is a dispatch-gap, fixed in p3; carryovers out of scope)
- /sweep p6 — defrag: 0 merges, 0 splits, 9 cross-refs (30 memories, healthy)

**Features** (6 commits)
- /review:evolve-skills — IMPROVE code-review (pass-rate Δ +25 pts)
- wave 1 — E15-S1.1 digest engine + output path
- wave 2 — E15-S1.2 digest CLI command + wiring (Epic 15 complete)
- wave 1 — E16-S1 migrations + Epic 16 Wave 1 wrap
- wave 2 — E16-S2 NAV + thin ledger (Epic 16 complete)
- /sweep p3 — 4 retro recs (DO-NOT-COMMIT template fix, ADR-008, CLAUDE.md drift, digest mkdir), 2 memories

**Chores** (1 commit)
- sync .claude/ from Domdhi.Agents template — R1 e2e gate + skill-eval/evolve fixes

**E16-S3** (1 commit)
- add risk.py — portfolio-level risk leaf


---

## Week of Jun 1, 2026

### Sat Jun 6 (17 commits, 59 files)
**Documentation** (10 commits)
- /review:sweep p7 — timeline refresh + final report
- /end — Epic 13 shipped + swept, findings + doc drift resolved
- /todo — create TODO for epic14-mcp-decision-interface (4 stories)
- agent-updates — log E14-S1 rogue commit (lead prompt omission)
- /sweep p1 — code review, 5 findings (0C/1M/3m+1nit)
- /sweep p2 — retro epic14-mcp-decision-interface
- /sweep p4 — promoted 0 concepts (15 already-represented candidates deferred to manual review)
- /sweep p5 — agent re-alignment (1 agent updated, 10 current)
- /sweep p5b — 1 skill-evolution proposal staged (code-review cross-cutting check), 1 rejected
- /sweep p6 — defrag: 0 merges, 0 splits, 4 cross-refs (26 memories, healthy)

**Fixes** (1 commit)
- resolve sweep CLI findings + doc drift

**E14-S2** (1 commit)
- add decision-contract module (decision.py)

**E14-S1** (1 commit)
- implement context.py MCP context-provider module

**Features** (4 commits)
- wave 1 — E14-S1, E14-S2 (Epic 14 MCP Decision Interface)
- wave 2 — E14-S3 FastMCP server + optional [mcp] extra (Epic 14)
- wave 3 — E14-S4 mcp CLI command + docs (Epic 14 complete)
- /sweep p3 — applied retro recs: F-1 mcp boundary fix, run-todo template hardening, doc-drift fixes, 2 memories


---

## Week of Jun 1, 2026

### Fri Jun 5 (7 commits, 369 files)
**Features** (1 commit)
- crypto TA pipeline + offline HTML dashboard (CoinGecko + SQLite)

**Documentation** (4 commits)
- legible ANSI-shadow DOMDHI banner in README
- add MIT license + dashboard screenshot (example data)
- template validation test plan for the Python stack
- /onboard — Domdhi.Crypto reverse-engineered

**Refactoring** (1 commit)
- src/ layout + tests, CI, packaging, and OSS docs

**Chores** (1 commit)
- install domdhi-agents template v4.47.0


### Sat Jun 6 (61 commits, 345 files)
**Documentation** (35 commits)
- /create:project-brief — Domdhi.Crypto (reverse-engineered)
- /create:project-requirements — Domdhi.Crypto PRD (reverse-engineered)
- /create:project-epics — Domdhi.Crypto backlog (brownfield)
- /create:project-todo — Domdhi.Crypto master index
- /create:project-epics-todo all — 9 per-epic checklists
- /do completion — E11-S1
- /review:feedback — Domdhi.Crypto template-performance report
- /review:check-sync — all, 1 drift item (test count), 0 dead links
- fill template-validation-test-plan
- /review:sweep p1 — code review, 2 findings (0C/0M/1minor+1nit)
- /review:sweep p2 — retro (template-validation)
- /review:sweep — add C15 (promoter over-promotes fresh memories)
- /review:sweep p5 — agent re-alignment (0 updated, all CURRENT)
- /review:sweep p6 — defrag: 0 merges/0 splits/0 cross-refs (14 mem, no near-cap)
- /review:sweep — sweep report + C15/C16 findings
- /end — template-validation v4.47.0 + sweep (16 findings, C11 headline)
- /run-todo epic11-hardening — final report + handoff
- /review:feedback — Domdhi.Crypto template-performance report
- /end — Epic 11 complete, coins.local.json rename, repo published
- /listen — 4 signals (2026-06-06)
- /triage — 2 promoted, 1 deferred, 1 killed (2026-06-06)
- fix doc drift — CLAUDE.md gate note + backlog status (T.1, T.2)
- /review:feedback — Domdhi.Crypto template-performance report
- /evolve validation test plan — exercise cycle rollover on Python stack
- /evolve cycle 2 re-plan — brief, PRD, backlog, index (decision cortex)
- /evolve validation — completed report (EV1-EV6, all phases)
- enhancement proposal — /evolve should leave the next TODO runnable
- /todo — Epic 12 Signal Substrate (3 stories, execution-ready)
- /run-todo epic12-signal-substrate — final report
- /todo — create TODO for Epic 13 Edge Validation (8 stories)
- /review:sweep p1 — code review, 5 findings (0C/0M/4m+1nit)
- /review:sweep p2 — retro epic13-edge-validation
- /review:sweep p5 — agent re-alignment (0 updated, all current)
- /review:sweep p5b — 0 skill-evolution proposals (2 intake candidates rejected as misattributed)
- /review:sweep p6 — defrag: 0 merges, 0 splits, 3 cross-refs (22 memories, healthy)

**Features** (13 commits)
- E11-S1 — add paths.py unit test (data-dir contract)
- wave 1 — E11-S2, E11-S4
- wave 2 — E11-S3
- /evolve — cycle 1 archived, cycle 2 planned
- wave 1 — E12-S1 pure-numpy factor primitive registry
- wave 2 — E12-S2 safe declarative factor expression evaluator
- wave 3 — E12-S3 built-in factor library + NOTICE
- wave 1 — E13-S1, E13-S3 (Epic 13 Edge Validation)
- wave 2 — E13-S2, E13-S4, E13-S5, E13-S6 (Epic 13 Edge Validation)
- wave 3 — E13-S7 look-ahead-safe backtest engine (Epic 13)
- wave 4 — E13-S8 by-factor attribution + Epic 13 final report
- backtest CLI command + CLAUDE.md test-count fix
- /review:sweep p3 — 2 run-todo template edits + 1 memory (CLI MINORs surfaced)

**Chores** (11 commits)
- /review:specialize — Domdhi.Crypto agents + gate config
- update .claude template v4.47.0 → v4.48.0 (crypto C1–C14 fixes)
- pre-publish hygiene — ignore generated HTML, track onboard scan
- sync .claude/ template to v4.51
- sync .claude/ template v4.51 → v4.53
- sync .claude template to v4.54 — universal run-stamp convention
- sync .claude template to v4.56 — guardrail nudge tier + /evolve
- sync template to v4.60
- sync template to v4.60
- sync template v4.60 → v4.61 from Domdhi.Agents
- sync .claude template to v4.63 (agent-creator/command-creator split + namespace reorg)

**Refactoring** (1 commit)
- rename coins.json → coins.local.json for convention + defense-in-depth

**Merge** (1 commit)
- Epic 12 Signal Substrate (cycle-2 re-plan + factors.py)


---

