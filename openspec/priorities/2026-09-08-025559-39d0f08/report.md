# Proposal Prioritization Report

**Run ID**: 2026-09-08-025559-39d0f08
**Generated**: 2026-09-08T02:55:59Z
**Analyzed Range**: `HEAD~50..HEAD` (50 commits, 186 files touched)
**Proposals Analyzed**: 64 active changes

## Headline

The active backlog is 64 changes, but only **~14 are actually implementable right now**.
The rest split into two piles that `openspec list` renders identically to real work:

| Population | Count | Signal | Action |
|---|---:|---|---|
| **Done, unarchived** | 12 | 100% tasks, or only `Review`/`Done`/`Merge`/`Archive` boxes left, artifact verified on `main` | archive sweep |
| **Genuinely near-complete** | 5 | real remaining tasks, implementation partly landed | finish |
| **Planned & ready** | 15 | real `design.md` + decomposed tasks, 0 started | implement |
| **Roadmap scaffolds** | 31 | boilerplate 10-task template, no design, spec dir == change-id | plan first |
| **Blocked** | 1 | archive gated on an external issue | unblock |

Totals to 64. Two of the fifteen "planned & ready" (`add-dispatch-sandbox-enforcement`,
`add-update-documentation-skill`) carry a `design.md` but **zero tasks** — decompose before dispatch.

**Task counts in `openspec list` are not a readiness signal here.** Readiness in this
report was verified against the filesystem (does the artifact exist on `main`?), not
against checkboxes.

## Priority Order

### Tier 0 — Archive sweep (zero risk, removes 19% of backlog)

These are complete. Their implementations were verified present on `main`; the open
checkboxes are process ceremony or explicitly-labelled out-of-scope follow-ups.

#### 1. Archive the seven `✓ Complete` changes
- **Relevance**: Likely Addressed
- **Readiness**: N/A — 100% tasks complete
- **Conflicts**: None
- **Members**: `extract-gen-eval-package` (43/43), `make-setup-coordinator-script-backed` (41/41),
  `inject-scoped-semantic-context-into-coding-jobs` (40/40), `derive-agent-identity-from-registry` (24/24),
  `add-local-model-provider-tier` (17/17), `rename-descriptor-model-levels` (11/11),
  `extend-coordinator-keys-to-new-harnesses` (6/6)
- **Next Step**: `openspec archive <id>` for each, or one `/cleanup-feature` pass

#### 2. Archive the five "done-pending-ceremony" changes
- **Relevance**: Likely Addressed — no branch survives, artifact is on `main`
- **Readiness**: N/A
- **Conflicts**: None
- **Evidence per change**:

| Change | Count | Open boxes are | Verified on `main` |
|---|---|---|---|
| `fix-autopilot-archetype-and-apply-outcome` | 54/59 | commit+push "left for the orchestrator" + 3 explicit out-of-scope | `write_capable` present in `agent-coordinator/archetypes.yaml` |
| `build-approval-gate-service-interviewer-abstraction` | 33/36 | `Review`, `Done`, `6.4 Review and merge` | `skills/shared/approval_gate.py` (30 KB) |
| `add-trust-posture-contract-file` | 29/33 | `Review`, `Done`, `6.1 Orchestrator review`, `6.2 Merge` | `skills/shared/trust_posture.py` (15 KB) |
| `fix-compact-hook-phase-boundary-detection` | 22/25 | commit+push + 1 out-of-scope | `skills/session-bootstrap/scripts/hooks/check_compact.py` |
| `require-validating-roadmap-scaffolds` | 4/5 | `1.5 Archive after merge` | superseded by archived `2026-09-02-scaffold-validating-roadmap-changes` |

- **Next Step**: verify then `openspec archive <id>`

#### 3. `iterate-traceability-sweep-over-touched-changes` — unblock the archive
- **Relevance**: Likely Addressed (`2725da99 ci(traceability): iterate the pull-request sweep over every touched change` is on `main`)
- **Readiness**: **Blocked** — sole open task `1.4 Archive so the canonical spec merge lands` is
  marked **BLOCKED on an OpenSpec** issue; `8825a298` records the blocker
- **Next Step**: resolve the recorded OpenSpec blocker, then archive

---

### Tier 1 — Finish the genuinely near-complete

#### 4. `factory-missions-architecture-alignment` — 51/53
- **Relevance**: Still Relevant
- **Readiness**: Ready — 2 real tasks left, both verification
  - `8.1` full `validate-feature` end-to-end on the sample frontend
  - `8.3` confirm `harness-engineering-features` rebases cleanly
- **Conflicts**: hub-file only (`skills/install.sh`, `review_dispatcher.py`, `consensus_synthesizer.py`)
- **Recommendation**: Highest-value *implementation* item — 96% done, and task 8.3 is a
  rebase-conflict check that decays as `main` moves
- **Next Step**: `/validate-feature factory-missions-architecture-alignment`

#### 5. `axi-align-coordinator-output` — 16/18
- **Relevance**: Still Relevant — no `toon` support found in `agent-coordinator/src/*.py`
- **Readiness**: Ready — `5.1` pilot `--format=toon` behind a flag + A/B token delta; `5.2` doc refresh
- **Conflicts**: `agent-coordinator/spec.md` with `add-sandboxed-harness-execution`
- **Next Step**: `/implement-feature axi-align-coordinator-output`

#### 6. `build-agent-trajectory-scenario-harness` — 29/34
- **Relevance**: Still Relevant — `packages/agent-scenarios/` **is** on `main` (pyproject, src, scenarios, tests)
- **Readiness**: Partially Ready — remaining tasks are the *operational* half:
  live multi-vendor GX10 execution, the 10-scenario suite + nightly cadence,
  `/improve-harness` wiring, incident auto-seeding
- **Conflicts**: `openspec/schemas/review-findings.schema.json` with `factory-missions` and `ambient-review-ledger`
- **Recommendation**: Real work, needs hardware/keys. Schedule after #4.
- **Next Step**: `/implement-feature build-agent-trajectory-scenario-harness`

#### 7. `add-frontier-model-tier` — 11/13
- **Relevance**: Still Relevant — `frontier` appears 13× in `archetypes.yaml`, so core landed
- **Readiness**: Ready — 2 follow-ups: translate `thinking` to vendor CLI flags; OpenRouter Pareto consult
- **Conflicts**: **Router hub** — `agents_config.py` + `archetypes.yaml` with 4 others
- **Branch**: `origin/openspec/add-frontier-model-tier` still open
- **Next Step**: `/implement-feature add-frontier-model-tier` — but see the router serialization note below

#### 8. `add-adaptive-model-router` — 21/71
- **Relevance**: Needs Verification — 50 tasks open, draft PR #417 stale since ~13d
- **Readiness**: Partially Ready
- **Conflicts**: **Router hub anchor** — conflicts with 7 other changes
- **Branches**: local `openspec/add-adaptive-model-router` + `--cleanup` + remote
- **Recommendation**: This is the keystone of the router cluster. Either drive it or
  explicitly park it — it is blocking 7 downstream changes by owning `agents_config.py`.
- **Next Step**: `/iterate-on-plan add-adaptive-model-router` (rescope 71 tasks) or resume PR #417

---

### Tier 2 — Planned and ready, unstarted (isolated first)

Ranked by conflict isolation, then scope. All have real `design.md` and decomposed tasks.

| # | Change | Tasks | Effort | Conflict profile |
|---|---|---:|---|---|
| 9  | `add-cross-harness-flow-display` | 0/16 | — | **Isolated** — `agentic-flow-display` spec, no overlaps |
| 10 | `add-visual-plan-review` | 0/12 | — | Hub-only (`install.sh`, `skills/shared/`) |
| 11 | `usage-stats-multi-model` | 0/28 | — | `agents.yaml` + `database/migrations/` only |
| 12 | `add-supervisor-candidate-work-digest` | 0/23 | S | `scripts/digest.py` w/ arbitrage; **deps** `ri-02 ri-05 ri-11 ri-16` |
| 13 | `add-product-management-skills` | 0/37 | — | Hub-only (`install.sh`, `docs/skills-catalogue.md`) |
| 14 | `add-harbor-benchmark-routing` | 0/49 | — | Near-isolated; **23 recent commits touch its dir — active** |
| 15 | `add-coordinator-llm-gateway` | 0/19 | — | `coordination_api.py`/`coordination_mcp.py`/migrations |
| 16 | `ambient-review-ledger` | 0/33 | — | `review-findings.schema.json`, `parallel-infrastructure/` |
| 17 | `cross-vendor-arbitrage-instrument` | 0/33 | — | `audit.py`, `review_dispatcher.py` |
| 18 | `add-atomic-harness` | 0/37 | — | **Router hub** — conflicts with 8 changes |
| 19 | `add-sandboxed-harness-execution` | 0/28 | — | **Router hub** — conflicts with 7 changes |
| 20 | `followup-add-prime-agent-harness` | 0/33 | M–L | **Router hub** — conflicts with 7 changes |
| 21 | `clamp-trust-by-isolation-posture` | 0/13 | M | deps `add-isolation-posture-detection` (a scaffold) |
| 22 | `add-dispatch-sandbox-enforcement` | **0 tasks** | M | **Router hub**; needs decomposition first |
| 23 | `add-update-documentation-skill` | **0 tasks** | — | Hub-only; needs decomposition first |

---

### Tier 3 — Roadmap scaffolds (31) — plan before implementing

These carry the literal `plan-roadmap` boilerplate (`Define detailed requirements /
Implement core functionality / Write tests / Update documentation / Review and merge`),
no `design.md`, and a spec directory named identically to the change-id. They are
**Needs Planning**, not **Ready**. Do not dispatch `/implement-feature` at them.

By parent roadmap:

- **`skill-rightsizing`** (20): `add-mutation-score-guardrail`, `add-self-describing-cli-entry-points`,
  `aggregate-process-telemetry-scorecard`, `apply-progressive-disclosure-oversized-skills`,
  `assert-generated-artifacts-validate-in-ci`, `build-task-replay-runner`,
  `calibrate-llm-judge-against-human-labels`, `collapse-mechanical-preamble-session-start`,
  `collect-uncollected-skill-tests`, `convert-failure-record-to-regression-scenarios`,
  `cut-competence-rules-relocate-policy`, `delete-rationalizations-relax-tail-block`,
  `invert-skill-test-suite-to-behavioural`, `measure-validator-recall-seeded-defects`,
  `publish-arm-a-baseline-scorecard`, `record-doctor-context-cost-baseline`,
  `rescope-review-convergence-disagreement-routing`, `rewrite-skill-frontmatter`,
  `run-sealed-holdout-decision`, `seal-archive-benchmark-corpus-split`
- **`repo-improvement`** (7): `add-live-vendor-capability-and-cost-registry`,
  `build-structured-vendor-result-channel`, `gate-drift-with-mirrors-hooks-and-blocking-ci`,
  `harden-the-resume-contract`, `implement-the-task-router-vendor-x-location-x-model`,
  `make-the-orchestrator-obey-the-router`, `reconcile-versions-and-stale-docs-to-one-truth`
- **`codeviz`** (2): `add-map-state-ir` (dep `artifact-header-schema`),
  `add-agent-activity-map-lens` (dep `map-state-ir`, `spa-scaffold-render`, `lens-framework`) —
  both touched in the last 50 commits, so this roadmap is warm
- **`dispatch-governance`** (2): `add-isolation-posture-detection`, `pin-isolation-contract`

The `skill-rightsizing` cluster has an internal dependency spine (`ri-01` → `ri-05` →
`ri-10`/`ri-12`/`ri-13`/`ri-14` → `run-sealed-holdout-decision`) that cannot be
scheduled until those items are planned.

---

## Parallel Workstreams

### Stream A — start immediately (fully independent)
- **Archive sweep** (Tier 0, items 1–2) — touches only `openspec/changes/`, conflicts with nothing
- `factory-missions-architecture-alignment` — validation only
- `add-cross-harness-flow-display` — isolated spec
- `usage-stats-multi-model` — isolated `usage-*` specs

### Stream B — after A (light hub contention on `skills/install.sh`, `skills/shared/`)
- `add-visual-plan-review`
- `add-product-management-skills`
- `add-update-documentation-skill` (decompose first)
- `axi-align-coordinator-output`

### Stream C — independent of A/B, own subsystem
- `add-harbor-benchmark-routing` (already warm)
- `add-coordinator-llm-gateway`
- `build-agent-trajectory-scenario-harness`

### Sequential — the router hub (strictly one at a time)
Nine changes contend over `agent-coordinator/src/agents_config.py` (9 proposals),
`skills/parallel-infrastructure/scripts/review_dispatcher.py` (7),
`agent-coordinator/agents.yaml` (7) and `agent-coordinator/archetypes.yaml` (4).
Recommended order (dependency-respecting):

1. `add-adaptive-model-router` — owns the policy surface; unblocks the rest
2. `add-frontier-model-tier` — small, already 11/13
3. `add-isolation-posture-detection` *(scaffold — plan first)*
4. `clamp-trust-by-isolation-posture` — depends on #3
5. `pin-isolation-contract` *(scaffold — plan first)*
6. `add-dispatch-sandbox-enforcement` — decompose first
7. `add-sandboxed-harness-execution`
8. `add-atomic-harness`
9. `followup-add-prime-agent-harness`

---

## Conflict Matrix — hub files

Files named by 3+ proposals. Two classes, and they need different handling:

| File | Proposals | Class |
|---|---:|---|
| `skills/install.sh` | 12 | **Registration hub** — append-only; low true-conflict risk, but serialize the final edit |
| `agent-coordinator/src/agents_config.py` | 9 | **True hot spot** — semantic contention |
| `skills/parallel-infrastructure/scripts/review_dispatcher.py` | 7 | **True hot spot** |
| `agent-coordinator/agents.yaml` | 7 | **True hot spot** |
| `agent-coordinator/src/coordination_api.py` | 5 | True hot spot |
| `skills/shared/environment_profile.py` | 4 | True hot spot (isolation cluster) |
| `agent-coordinator/archetypes.yaml` | 4 | True hot spot (router cluster) |
| `docs/skills-workflow.md`, `docs/parallel-agentic-development.md`, `docs/lessons-learned.md` | 4 each | Doc hub — mergeable |
| `openspec/schemas/review-findings.schema.json` | 3 | Schema hub — **breaking-change risk**, serialize |
| `openspec/schemas/provider-model-map.schema.json` | 3 | Schema hub — serialize |
| `skills/shared/approval_gate.py` | 3 | Hot spot |
| `agent-coordinator/src/coordination_mcp.py` | 3 | Hot spot |
| `agent-coordinator/database/migrations/` | 3 | **Ordering-sensitive** — serialize migration numbering |

Selected true pairwise conflicts (hub noise removed):

| Pair | Contested files |
|---|---|
| `add-atomic-harness` ↔ `followup-add-prime-agent-harness` | `agents.yaml`, `agents_config.py`, `provider-model-map.schema.json`, `CLAUDE.md`, `README.md` |
| `add-dispatch-sandbox-enforcement` ↔ `add-sandboxed-harness-execution` | `agents_config.py`, `network_policies.py`, `environment_profile.py`, `sandbox_profile.py`, `review_dispatcher.py` |
| `add-trust-posture-contract-file` ↔ `build-approval-gate-service` | `skills/shared/approval_gate.py`, `skills/shared/trust_posture.py` |
| `add-adaptive-model-router` ↔ `add-atomic-harness` | `agents_config.py`, `review_dispatcher.py` |
| `factory-missions` ↔ `add-atomic-harness` | `agents.yaml`, `consensus_synthesizer.py`, `review_dispatcher.py` |
| `add-coordinator-llm-gateway` ↔ `usage-stats-multi-model` | `database/migrations/` |

---

## Proposals Needing Attention

### Likely Addressed — archive (12)
`extract-gen-eval-package`, `make-setup-coordinator-script-backed`,
`inject-scoped-semantic-context-into-coding-jobs`, `derive-agent-identity-from-registry`,
`add-local-model-provider-tier`, `rename-descriptor-model-levels`,
`extend-coordinator-keys-to-new-harnesses`, `fix-autopilot-archetype-and-apply-outcome`,
`build-approval-gate-service-interviewer-abstraction`, `add-trust-posture-contract-file`,
`fix-compact-hook-phase-boundary-detection`, `require-validating-roadmap-scaffolds`

### Blocked (1)
- `iterate-traceability-sweep-over-touched-changes` — archive blocked on a recorded OpenSpec issue (`8825a298`)

### Missing task decomposition (3)
- `add-dispatch-sandbox-enforcement` — 0 tasks, `dg-07`, effort M
- `add-update-documentation-skill` — 0 tasks, has `design.md`
- 31 roadmap scaffolds — boilerplate tasks only (see Tier 3)

### Needs Refinement — scope drift (1)
- `add-adaptive-model-router` — 71 tasks, 21 done, stale draft PR #417, three live branches
  (`openspec/add-adaptive-model-router`, `…--cleanup`, remote). Owns the hottest file in
  the repo while parked. Rescope or resume.

### Process observation
`build-agent-trajectory-scenario-harness` marks `Implementation` and `Testing` as `[x]`
while its `Live multi-vendor execution` and `10-scenario suite` tasks remain open. The
package **is** on `main`, so the count is honest — but the `Status` block and the task
list disagree about what "Implementation complete" means. Worth a convention check if
the archive sweep is to be automated.
