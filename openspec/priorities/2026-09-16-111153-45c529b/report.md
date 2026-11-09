# Proposal Prioritization Report

**Run ID**: 2026-09-16-111153-45c529b
**Generated**: 2026-09-16T11:11:54Z
**Analyzed Range**: `HEAD~50..HEAD` (50 commits, ~282 files touched)
**Proposals Analyzed**: 55 active changes
**Previous report**: `openspec/priorities/2026-09-08-025559-39d0f08/` (64 → 55; archive sweep landed)

## Headline

The active backlog is **55** changes. Only **~16 are implementable without first planning**.
The rest split into populations that `openspec list` renders identically to real work:

| Population | Count | Signal | Action |
|---|---:|---|---|
| **Done, unarchived** | 1 | 100% tasks + validation report on change | archive |
| **Genuinely near-complete** | 3 | real remaining tasks, core already on `main` | finish |
| **XS follow-ups** | 2 | post-archive docs/scoping (3 tasks each) | quick close |
| **Planned & ready** | 11 | real `design.md` + decomposed tasks, 0–partial started | implement |
| **Needs decomposition** | 2 | `design.md` but **zero** tasks | decompose first |
| **Validating roadmap scaffolds** | 33 | acceptance text + boilerplate 10-task template (or change-id-named spec) | `/iterate-on-plan` / plan before implement |
| **Blocked** | 1 | archive gated on an OpenSpec issue | unblock |

**Recent history signal (last 50 commits):** almost entirely the landing of
`add-deterministic-review-preprocessing` (fact-check, line resolver, OCR vendor,
file selection, coverage quorum) plus plan iteration on `add-visual-code-explainer`
and a `skill-rightsizing` roadmap refine. That makes the adjudication gate the
natural *plan-next* item, and the visual explainer the natural *implement-next*
greenfield.

**Soft conflicts:** many proposals only share `skills/install.sh`. Treat that as a
merge-serialization tip, not a hard blocker — parallel streams are still valid.

---

## Priority Order

### Tier 0 — Archive sweep (zero risk)

#### 1. `add-deterministic-review-preprocessing` — Change: add-deterministic-review-preprocessing
- **Relevance**: Likely Addressed — 47/47 tasks; artifacts on `main`
  (`fact_check.py`, `line_resolver.py`, `file_selection.py`, `ocr_adapter.py`);
  validation report records 1115 tests passed
- **Readiness**: N/A
- **Conflicts**: N/A (archiving)
- **Recommendation**: Verify then archive; unlocks cleaner rebase surface for
  `ambient-review-ledger` and related review work
- **Next Step**: `openspec archive add-deterministic-review-preprocessing` (or `/cleanup-feature`)

#### 2. `iterate-traceability-sweep-over-touched-changes` — unblock archive
- **Relevance**: Likely Addressed — CI iterate-over-touched-changes is on `main`
- **Readiness**: **Blocked** — sole open task `1.4 Archive…` marked BLOCKED on an OpenSpec issue
- **Conflicts**: None
- **Recommendation**: Resolve the recorded OpenSpec blocker, then archive
- **Next Step**: inspect the blocker note in `tasks.md`, then `openspec archive …`

---

### Tier 1 — Finish near-complete and XS follow-ups

#### 3. `axi-align-coordinator-output` — AXI-Align Coordinator Agent-Output Contract
- **Relevance**: Still Relevant — envelope/`truncated`/`next_steps` helpers exist; `--format=toon` pilot does not
- **Readiness**: Partially Ready (16/18)
  - Remaining: `5.1` pilot `--format=toon` + A/B token delta; `5.2` doc refresh
- **Conflicts**: Soft — `coordination_api.py` with `add-coordinator-llm-gateway`, `usage-stats-multi-model`, router/sandbox cluster
- **Recommendation**: **Highest-value finish** — 89% done, small scope, decays least if parked briefly but cheap to close now
- **Next Step**: `/implement-feature axi-align-coordinator-output`

#### 4. `followup-fix-compact-hook-phase-boundary-detection` — compact-hook gate docs
- **Relevance**: Still Relevant — conditional lessons-learned entry
- **Readiness**: Ready (0/3) — evaluate recurrence since parent merge; write entry or record negative finding
- **Conflicts**: None meaningful (`docs/lessons-learned.md` only)
- **Recommendation**: XS quick close; can run in parallel with #3
- **Next Step**: `/implement-feature followup-fix-compact-hook-phase-boundary-detection` (or `/quick-task`)

#### 5. `followup-fix-autopilot-archetype-and-apply-outcome` — docs + two scoping decisions
- **Relevance**: Still Relevant
- **Readiness**: Ready (0/3) — update `docs/parallel-agentic-development.md`; decide on loop-state structural enforcement and silent-no-op detection
- **Conflicts**: Soft — mentions `archetypes.yaml` (docs-only in practice)
- **Recommendation**: XS/S; schedule beside #4
- **Next Step**: `/implement-feature followup-fix-autopilot-archetype-and-apply-outcome`

#### 6. `add-frontier-model-tier` — finish dispatch/OpenRouter follow-ups
- **Relevance**: Needs Verification — `frontier` tier present in `archetypes.yaml`; 11/13 tasks done
- **Readiness**: Partially Ready — remaining: translate `thinking` → vendor CLI flags; OpenRouter Pareto consult
- **Conflicts**: **Router hub** — `agents_config.py` + `archetypes.yaml` with adaptive-router, atomic, sandboxed, harbor, prime-agent
- **Branches**: `origin/openspec/add-frontier-model-tier`
- **Recommendation**: Finish only if not colliding with an active router PR; otherwise park behind #3/#7
- **Next Step**: `/implement-feature add-frontier-model-tier`

#### 7. `build-agent-trajectory-scenario-harness` — operational half
- **Relevance**: Needs Verification — `packages/agent-scenarios/` is on `main` (29/34)
- **Readiness**: Partially Ready — remaining are live GX10 multi-vendor runs, nightly cadence, `/improve-harness` wiring, incident auto-seed (plus Review/Done ceremony)
- **Conflicts**: Soft — `review-findings.schema.json` (just churned), `packages/agent-scenarios/` with harbor/prime-agent
- **Recommendation**: Needs hardware/keys; schedule as a dedicated session, not interleaved with greenfield
- **Next Step**: `/implement-feature build-agent-trajectory-scenario-harness` when GX10/keys available

---

### Tier 2 — Planned and ready (prefer isolated)

Ranked by conflict isolation, then momentum/scope. All have real designs and decomposed tasks.

| # | Change | Tasks | Conflict profile | Next step |
|---|---|---:|---|---|
| 8 | `add-visual-code-explainer` | 0/24 | **Near-isolated** — `skills/codebase-atlas/`, new `skills/explain-code/`; only hub touch is `install.sh`. Just planned (remote branch). | `/implement-feature add-visual-code-explainer` |
| 9 | `add-cross-harness-flow-display` | 0/16 | **Isolated-ish** — `apps/kanban-viz/` + `agentic-flow-display` spec | `/implement-feature add-cross-harness-flow-display` |
| 10 | `add-visual-plan-review` | 0/12 | Hub-only (`install.sh`) | `/implement-feature add-visual-plan-review` |
| 11 | `add-product-management-skills` | 0/37 | Hub-only (`install.sh`) | `/implement-feature add-product-management-skills` |
| 12 | `add-harbor-benchmark-routing` | 0/49 | `archetypes.yaml` + `packages/agent-scenarios/` | `/implement-feature add-harbor-benchmark-routing` |
| 13 | `add-coordinator-llm-gateway` | 0/19 | `coordination_api.py` / migrations — serialize after #3 | `/implement-feature add-coordinator-llm-gateway` |
| 14 | `usage-stats-multi-model` | 0/28 | migrations + `agents.yaml` + kanban-viz | `/implement-feature usage-stats-multi-model` |
| 15 | `ambient-review-ledger` | 0/33 | **Review hub** — rebase onto archived preprocessing first | `/implement-feature ambient-review-ledger` after Tier 0 |
| 16 | `cross-vendor-arbitrage-instrument` | 0/33 | Router + review hubs | after router decision |
| 17 | `add-atomic-harness` | 0/37 | **Router hub** (conflicts with ~8) | serialize |
| 18 | `add-sandboxed-harness-execution` | 0/28 | **Router hub** | serialize |
| 19 | `followup-add-prime-agent-harness` | 0/33 | **Router hub** (widest overlap) | serialize |
| 20 | `add-adaptive-model-router` | 21/71 | **Keystone** — PR #417 open; conflicts with ~7 downstream | `/iterate-on-plan` to rescope **or** drive PR #417 |

#### Needs decomposition before dispatch
- `add-dispatch-sandbox-enforcement` — design-ish / no tasks
- `add-update-documentation-skill` — design, **0 tasks**

---

### Tier 3 — Plan-next (high leverage scaffolds)

These are **not** ready for `/implement-feature`. They have validating acceptance text
(or SCAFFOLD designs) but boilerplate tasks.

#### 21. `add-orchestrator-adjudication-review-gate` — **plan this next among scaffolds**
- **Relevance**: Still Relevant — motivated by PR #484 (7 single-vendor criticals slipped through); sits directly atop the just-landed deterministic preprocessing
- **Readiness**: Needs Planning — SCAFFOLD `design.md`, boilerplate 10-task template; proposal acceptance outcomes are real
- **Conflicts**: Will touch `skills/autopilot/` + `skills/merge-pull-requests/` (expect overlap with ambient-review / review hub)
- **Recommendation**: `/iterate-on-plan add-orchestrator-adjudication-review-gate` immediately after Tier 0 archive — highest-leverage plan in the `skill-rightsizing` DAG (`ri-21`, no deps)
- **Next Step**: `/iterate-on-plan add-orchestrator-adjudication-review-gate`

#### 22–23. Codeviz pair (dependency order)
- `add-map-state-ir` (deps: artifact-header-schema) → then `add-agent-activity-map-lens` (deps: map-state-ir, spa-scaffold, lens-framework)
- Both are validating scaffolds under `codeviz` — plan IR first

#### Skill-rightsizing Priority-1 independents (boilerplate; plan via roadmap)
Independent or lightly gated candidates to flesh next (from roadmap phase table):
- `convert-failure-record-to-regression-scenarios` (ri-01)
- `seal-archive-benchmark-corpus-split` (ri-02)
- `assert-generated-artifacts-validate-in-ci` (ri-19)
- `collect-uncollected-skill-tests` (ri-20)
- `aggregate-process-telemetry-scorecard` (ri-03)
- `record-doctor-context-cost-baseline` (ri-04)

Do **not** `/implement-feature` these until `/iterate-on-plan` (or roadmap refine) replaces the boilerplate tasks.

---

## Parallel Workstreams

### Stream A — start immediately (independent)
- `axi-align-coordinator-output` — finish 2 remaining tasks
- `add-visual-code-explainer` — greenfield implement
- `followup-fix-compact-hook-phase-boundary-detection` — XS docs decision

### Stream B — parallel with A (docs / light)
- `followup-fix-autopilot-archetype-and-apply-outcome`
- `/iterate-on-plan add-orchestrator-adjudication-review-gate` (planning only — no code conflict)

### Stream C — after Stream A (or when keys/hardware ready)
- `add-cross-harness-flow-display` **or** `add-visual-plan-review`
- `build-agent-trajectory-scenario-harness` (GX10 session)

### Sequential — router / review hubs
- Wait for adaptive-router decision (drive #417 vs park) before: `add-frontier-model-tier` remaining, `add-atomic-harness`, `add-sandboxed-harness-execution`, `followup-add-prime-agent-harness`, `cross-vendor-arbitrage-instrument`
- Archive preprocessing **before** starting `ambient-review-ledger`

---

## Conflict Matrix (implementable subset)

Hub-only overlaps on `skills/install.sh` omitted when that is the sole shared path.

| | axi | visual-explainer | cross-harness | frontier | trajectory | gateway | usage | ambient | adaptive-router |
|---|---|---|---|---|---|---|---|---|---|
| axi | — | none | none | none | none | `coordination_api.py` | `coordination_api.py` | none | `coordination_api.py` |
| visual-explainer | none | — | none | none | none | none | none | none | none |
| cross-harness | none | none | — | none | none | none | `kanban-viz` | `kanban-viz` | `kanban-viz` |
| frontier | none | none | none | — | none | none | none | `autopilot/` | **agents_config + archetypes** |
| trajectory | none | none | none | none | — | none | none | review-findings schema | none |
| gateway | `coordination_api.py` | none | none | none | none | — | api+migrations | none | `coordination_api.py` |
| usage | `coordination_api.py` | none | `kanban-viz` | none | none | api+migrations | — | `kanban-viz` | agents.yaml+api |
| ambient | none | none | `kanban-viz` | `autopilot/` | schema | none | `kanban-viz` | — | review+autopilot |
| adaptive-router | `coordination_api.py` | none | `kanban-viz` | **hub** | none | `coordination_api.py` | hub | hub | — |

---

## Proposals Needing Attention

### Likely Addressed
- `add-deterministic-review-preprocessing`: implementation + validation on `main`. Archive.
- `iterate-traceability-sweep-over-touched-changes`: code landed; archive blocked on OpenSpec issue.

### Needs Refinement / Planning
- `add-orchestrator-adjudication-review-gate`: rich acceptance, SCAFFOLD design, boilerplate tasks — `/iterate-on-plan`
- `add-map-state-ir`, `add-agent-activity-map-lens`: validating codeviz scaffolds — plan IR before lens
- Entire `skill-rightsizing` scaffold set (20+): use roadmap phase table; do not treat 0/10 as ready
- `add-adaptive-model-router`: 21/71 + stale-ish PR #417 — rescope or explicitly park; it blocks the router cluster by owning `agents_config.py`
- `add-dispatch-sandbox-enforcement`, `add-update-documentation-skill`: missing task decomposition

### Needs Verification
- `add-frontier-model-tier`, `build-agent-trajectory-scenario-harness`: core on `main`, operational tails remain
- Review-hub proposals (`ambient-review-ledger`, etc.): rebase assumptions after preprocessing merge

---

## Suggested operator move (next 24h)

1. Archive `add-deterministic-review-preprocessing`
2. Parallel: `/implement-feature axi-align-coordinator-output` + `/implement-feature add-visual-code-explainer`
3. Parallel (planning): `/iterate-on-plan add-orchestrator-adjudication-review-gate`
4. Decide fate of PR #417 (`add-adaptive-model-router`) — drive, rescope, or park — before touching any other router-hub change
