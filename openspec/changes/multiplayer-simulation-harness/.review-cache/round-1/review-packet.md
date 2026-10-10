## Review Round 1

The packet is complete; do not explore the repo for missing artifacts.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 2100997..e3ab56e 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -207,6 +207,7 @@ jobs:
             tests/improve-harness \
             tests/iterate-on-plan \
             tests/langfuse \
+            tests/multiplayer-simulation \
             tests/phase-record-compaction \
             tests/plan-roadmap \
             tests/playwright-validator \
diff --git a/openspec/changes/multiplayer-simulation-harness/design.md b/openspec/changes/multiplayer-simulation-harness/design.md
index 2eb76da..6b924be 100644
--- a/openspec/changes/multiplayer-simulation-harness/design.md
+++ b/openspec/changes/multiplayer-simulation-harness/design.md
@@ -115,7 +115,7 @@ time?" today has one honest answer: nothing ran.
     probe can read git state but cannot mutate the world.
   - `ProbeResult` fields: `probe_id`, `status ∈ {ok, error}`, `collisions: list[{level,
     other_change, requirement}]`, `error: str | null`.
-- At each principal's plan step, the driver calls every registered probe. It records
+- At the second principal's plan step, the driver calls every registered probe. It records
   `probes` (one entry per probe that ran) and sets `collision_detected` to true when any probe
   with status `ok` reported a collision at level `requirement` against the other principal's
   change.
@@ -167,7 +167,8 @@ time?" today has one honest answer: nothing ran.
 - **Status transitions are fixture data, not harness code.** Each step in a principal's
   fixture script may declare `on_start.set_status` and `on_finish.set_status` for that
   principal's own roadmap item. The agent does not apply them. It reports them as step
-  results, and the status applier commits each one to `roadmap.yaml` on `main` and pushes.
+  results. The status applier (part of the `mpsim` package, operating on its own clone of
+  the shared remote, not a principal's clone) commits each one to `roadmap.yaml` on `main` and pushes.
   The applier holds no transition logic of its own: it writes exactly the status the fixture
   declared, for the item of the principal that reported it. In the baseline fixture:
   - `plan` and `contract` change no status, so the item stays `approved` and remains
@@ -191,7 +192,9 @@ time?" today has one honest answer: nothing ran.
   - `earliest_start_tick` is the tick at which that principal's own preceding steps finished
     (its plan).
   - `ready_tick` is the first tick at which `ready_items()` admits its implement step.
-  - A principal with no dependency is ready at `earliest_start_tick`, so its value is 0.
+  - A principal with no dependency is also admitted through `Roadmap.ready_items()`. The
+    harness never short-circuits readiness. Such a principal is admitted at
+    `earliest_start_tick`, so its value is 0.
 - **Baseline fixture durations**:
   - `storage-owner`: plan 1, contract 2, implement 8. Its implementation completes at tick
     11.
@@ -249,13 +252,14 @@ time?" today has one honest answer: nothing ran.
 
 ### D7: Scripted agents behind an `Agent` protocol
 
-- `Agent.act(view: PrincipalView, step: Step) -> None` performs one step's file edits and
-  git operations.
+- `Agent.act(world, step, tick)` performs one step's file edits and git operations and
+  returns the step's declared status transitions (it never applies them).
 - `ScriptedAgent` replays the fixture's step script deterministically:
   - write the OpenSpec change files under a synthetic change id;
   - commit;
   - push to `refs/heads/sim/<principal>/<change>`, which models an open PR branch;
-  - return the step's declared status transitions to the scheduler.
+  - return the step's declared status transitions to the scheduler. `on_start` data is read
+    through `declared_transitions(step, "start")`, since it applies before the step runs.
 - Agents never write `roadmap.yaml` and never push to `main`. A test asserts that no commit
   on any `sim/*` branch touches `roadmap.yaml`, and that every commit on `main` after the
   seed is authored by `sim-supervisor` (D5, operator decision A1).
diff --git a/openspec/changes/multiplayer-simulation-harness/loop-state.json b/openspec/changes/multiplayer-simulation-harness/loop-state.json
index 8596b1e..2f73199 100644
--- a/openspec/changes/multiplayer-simulation-harness/loop-state.json
+++ b/openspec/changes/multiplayer-simulation-harness/loop-state.json
@@ -1,9 +1,9 @@
 {
   "schema_version": 5,
   "change_id": "multiplayer-simulation-harness",
-  "current_phase": "IMPLEMENT",
+  "current_phase": "IMPL_REVIEW",
   "iteration": 0,
-  "total_iterations": 9,
+  "total_iterations": 13,
   "max_phase_iterations": 3,
   "findings_trend": [],
   "blocking_findings": [],
@@ -17,7 +17,9 @@
     "9403b68a-7911-4949-a775-3b689b8ecb54",
     "44759acd-c2f6-4d02-8dfd-278037b64a61",
     "11f32d63-4f2f-4bf4-a4d0-deebdea265f9",
-    "ab3b1133-8595-4fe0-92b6-909f7872b6f3"
+    "ab3b1133-8595-4fe0-92b6-909f7872b6f3",
+    "fa6e1d35-520b-42bd-932c-644b008829cf",
+    "cc44baf6-dd8c-4ae4-931c-2203d6928c33"
   ],
   "phase_history": [
     {
@@ -44,13 +46,29 @@
       "at": "2026-10-09T08:10:30.617950+00:00",
       "outcome": "failed",
       "phase": "IMPLEMENT"
+    },
+    {
+      "at": "2026-10-09T08:34:06.664816+00:00",
+      "outcome": "complete",
+      "phase": "IMPLEMENT"
+    },
+    {
+      "at": "2026-10-09T12:18:38.221344+00:00",
+      "outcome": "complete",
+      "phase": "IMPL_ITERATE"
+    },
+    {
+      "phase": "IMPL_REVIEW",
+      "outcome": "host_escalate",
+      "at": "2026-10-09T12:22:27.260061+00:00",
+      "note": "IMPL_REVIEW blocked before any review ran: the auto-mode classifier denied the converge() driver run as [CI Bypass] (driver shims base_ref=d22417e, excludes .review-ledger/.review-cache from the post-fix scope check, and drops to min_quorum=1). Needs an operator decision on how implementation review may run in cloud containers."
     }
   ],
-  "last_handoff_id": "ab3b1133-8595-4fe0-92b6-909f7872b6f3",
+  "last_handoff_id": "cc44baf6-dd8c-4ae4-931c-2203d6928c33",
   "started_at": "2026-10-05T07:12:02.399401+00:00",
-  "phase_started_at": "2026-10-09T08:15:43.361602+00:00",
-  "previous_phase": "IMPLEMENT",
-  "escalation_reason": "IMPLEMENT transitioned to ESCALATE via outcome 'failed'",
+  "phase_started_at": "2026-10-10T03:04:37.519069+00:00",
+  "previous_phase": "IMPL_REVIEW",
+  "escalation_reason": "IMPL_REVIEW blocked before any review ran: the auto-mode classifier denied the converge() driver run as [CI Bypass] (driver shims base_ref=d22417e, excludes .review-ledger/.review-cache from the post-fix scope check, and drops to min_quorum=1). Needs an operator decision on how implementation review may run in cloud containers.",
   "val_review_enabled": false,
   "cli_review_enabled": true,
   "error": null,
@@ -116,6 +134,37 @@
       "resolution": "console_approved",
       "timeout_seconds": null
     },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T08:10:36.683211+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator (user, 2026-10-09) approved fast-forwarding the IMPLEMENT sub-agent worktree to origin/openspec/multiplayer-simulation-harness (git reset --hard / merge --ff-only) to resolve the IMPLEMENT branch-adoption failure.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (user, 2026-10-09) approved fast-forwarding the IMPLEMENT sub-agent worktree to origin/openspec/multiplayer-simulation-harness (git reset --hard / merge --ff-only) to resolve the IMPLEMENT branch-adoption failure.",
+      "recorded_at": "2026-10-09T08:15:43.361558+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
     {
       "gate": "escalate_resume",
       "outcome": "blocked",
@@ -129,14 +178,14 @@
       "timeout_seconds": null,
       "disposition": "block",
       "phase": "ESCALATE",
-      "recorded_at": "2026-10-09T08:10:36.683211+00:00"
+      "recorded_at": "2026-10-09T12:22:33.881025+00:00"
     },
     {
       "gate": "escalate_resume",
       "outcome": "proceed",
       "resolution": "console_approved",
       "authorizing_disposition": "block",
-      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (user, 2026-10-09) approved fast-forwarding the IMPLEMENT sub-agent worktree to origin/openspec/multiplayer-simulation-harness (git reset --hard / merge --ff-only) to resolve the IMPLEMENT branch-adoption failure.",
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (user, 2026-10-10) chose option 2: port converge() base_ref + bookkeeping-path scope fix from the PR base (commit above) and run IMPL_REVIEW via converge() without driver shims.",
       "approval_id": null,
       "default_action": null,
       "posture_present": true,
@@ -144,8 +193,8 @@
       "timeout_seconds": null,
       "disposition": "block",
       "phase": "ESCALATE",
-      "recorded_at": "2026-10-09T08:15:43.361558+00:00",
-      "note": "Operator (user, 2026-10-09) approved fast-forwarding the IMPLEMENT sub-agent worktree to origin/openspec/multiplayer-simulation-harness (git reset --hard / merge --ff-only) to resolve the IMPLEMENT branch-adoption failure."
+      "recorded_at": "2026-10-10T03:04:37.519036+00:00",
+      "note": "Operator (user, 2026-10-10) chose option 2: port converge() base_ref + bookkeeping-path scope fix from the PR base (commit above) and run IMPL_REVIEW via converge() without driver shims."
     }
   ],
   "pending_gate": null,
diff --git a/openspec/changes/multiplayer-simulation-harness/session-log.md b/openspec/changes/multiplayer-simulation-harness/session-log.md
index 83acd95..e91883d 100644
--- a/openspec/changes/multiplayer-simulation-harness/session-log.md
+++ b/openspec/changes/multiplayer-simulation-harness/session-log.md
@@ -203,3 +203,50 @@ Re-ran PLAN_REVIEW as converge(review_type=plan) after the operator's A1 decisio
 ### Context
 IMPLEMENT sub-agent aborted before any edit: its harness worktree was rooted at main; worktree.py setup skipped re-rooting (isolation_provided=true, source=env_var); the feature branch is checked out in the main checkout; bringing the agent worktree to origin/openspec/multiplayer-simulation-harness via git reset --hard / merge --ff-only was denied by the permission classifier. Per supervisor rules a classifier denial parks the run; no workaround attempted.
 
+---
+
+## Phase: Implementation (2026-10-09)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Used the orchestrator-supplied worktree instead of worktree.py setup** `architectural: skill-procedure-deviation` — Two earlier attempts could not re-root a main-rooted harness worktree; the operator approved the managed agent worktree on openspec/multiplayer-simulation-harness--impl. /implement-feature's worktree.py setup was therefore not run.
+2. **Agent.act takes (world, step, tick) and returns declared transitions** `architectural: multiplayer-simulation` — Ledger 12. on_start data is read via declared_transitions(step, 'start') because it applies before the step runs; act returns the on_finish ones.
+3. **Scheduler fast-forwards to the tick budget when nothing is running** `architectural: multiplayer-simulation` — If no step is running and nobody was admitted, main cannot change again, so the result equals running idle ticks; it keeps blocked-budget runs fast.
+4. **gen-eval pack test asserts scenario count and absence of 'Invalid scenario'** `architectural: multiplayer-simulation` — gen-eval silently skips scenarios that fail to load (missing description), so the pass alone is not evidence.
+
+### Open Questions
+- [ ] Harness wall time is 34 s against the 30 s budget; ~8 s is the whole-tree path-stability guard subprocess in test_archive_stability.py.
+
+### Completed Work
+- Tasks 1.1-9.1 and all checkpoints ticked and pushed to openspec/multiplayer-simulation-harness
+
+### Next Steps
+- IMPL_REVIEW / validation
+
+### Relevant Files
+- `skills/tests/multiplayer-simulation/` — harness root
+
+### Context
+Implemented all of tasks.md (groups 1-9) in the orchestrator-supplied worktree: mpsim driver, probe seam, oracle, status applier, tick scheduler, CLI, gen-eval pack, README, design alignment. Harness suite 93 passed; gen-eval pack 10/10.
+
+---
+
+## Phase: Implementation Iteration (2026-10-09)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **skill-procedure-deviation: orchestrator-supplied worktree** — Used the operator-approved managed worktree .git-worktrees/multiplayer-simulation-harness/impl (branch openspec/multiplayer-simulation-harness--impl) instead of creating one via the worktree skill, because the harness worktree could not be re-rooted.
+2. **Suite runtime over 30s budget left recorded** — Suite takes ~37s; ~11s is test_the_path_stability_guard_reports_nothing_in_the_harness, a whole-tree subprocess run of tests/openspec_paths. Narrowing it would weaken the assertion, so it is left as is.
+
+### Completed Work
+- Ran harness suite (93 passed) and ruff check (clean)
+- Reviewed world, applier, fixture, runner, oracle, agents and archive-stability tests
+
+### Next Steps
+- Consider a faster scoped path-stability guard in a follow-up if the 30s budget must hold
+
+### Context
+Reviewed harness against spec/design/contracts; 93 tests pass, ruff clean; no real defects found, no code changes.
+
diff --git a/openspec/changes/multiplayer-simulation-harness/tasks.md b/openspec/changes/multiplayer-simulation-harness/tasks.md
index 286a7f6..d3b16e8 100644
--- a/openspec/changes/multiplayer-simulation-harness/tasks.md
+++ b/openspec/changes/multiplayer-simulation-harness/tasks.md
@@ -24,7 +24,7 @@
 
 ## 1. Contracts and scaffolding
 
-- [ ] 1.1 Write failing contract tests in `test_contracts.py`. Read everything through
+- [x] 1.1 Write failing contract tests in `test_contracts.py`. Read everything through
   `repo_root_from(__file__, 3)`. Four cases:
   - `openspec/contracts/multiplayer-simulation/cli/mpsim.yaml` validates against
     `openspec/contracts/gen-eval-framework/schemas/cli-contract.schema.json`.
@@ -39,18 +39,18 @@
   **Contracts**: contracts/cli/mpsim.yaml, contracts/schemas/sim-report.schema.json
   **Design decisions**: D8, D10
   **Dependencies**: 1.4
-- [ ] 1.2 Promote `contracts/cli/mpsim.yaml` and `contracts/schemas/sim-report.schema.json` to
+- [x] 1.2 Promote `contracts/cli/mpsim.yaml` and `contracts/schemas/sim-report.schema.json` to
   `openspec/contracts/multiplayer-simulation/{cli,schemas}/`, and add a row to the contents
   table in `openspec/contracts/README.md`. When this is done, 1.1 passes. [XS]
   **Dependencies**: 1.1
-- [ ] 1.3 Add `gen-eval` to the `test` extra in `skills/pyproject.toml`, add
+- [x] 1.3 Add `gen-eval` to the `test` extra in `skills/pyproject.toml`, add
   `gen-eval = { path = "../packages/gen-eval" }` under `[tool.uv.sources]`, and run `uv lock`
   in `skills/`. A scratch resolution during planning succeeded, resolving 56 packages. Verify
   that `uv run --project skills gen-eval --print-contract-version` exits 0. If resolution
   fails, stop and take the D3 fallback as a recorded design amendment, never silently. [XS]
   **Design decisions**: D3
   **Dependencies**: None
-- [ ] 1.4 Scaffold the harness directory:
+- [x] 1.4 Scaffold the harness directory:
   - `conftest.py`, which puts the harness root and `skills/roadmap-runtime/scripts` on
     `sys.path` using the pattern in `skills/tests/roadmap-runtime/conftest.py`, and adds an
     autouse fixture that makes `AF_INET`/`AF_INET6` `socket.connect` and `connect_ex` raise
@@ -68,12 +68,12 @@
   **Spec scenarios**: O.1, O.3
   **Design decisions**: D2, D9
   **Dependencies**: None
-- [ ] Checkpoint: run `skills/tests/ci_coverage/` and the harness directory. Only the contract,
+- [x] Checkpoint: run `skills/tests/ci_coverage/` and the harness directory. Only the contract,
   scaffold, `pyproject.toml`/`uv.lock` and `ci.yml` should have changed.
 
 ## 2. World, agents, clock and report (sequential chain)
 
-- [ ] 2.1 Write failing tests in `test_world.py`:
+- [x] 2.1 Write failing tests in `test_world.py`:
   - two principals get distinct identities (`<name>@sim.invalid`), clones, worktrees and agent
     ids (P.1);
   - an unpushed commit is invisible to the other principal after fetch (P.2);
@@ -86,11 +86,11 @@
   **Spec scenarios**: P.1, P.2, P.3, P.4
   **Design decisions**: D6
   **Dependencies**: 1.4
-- [ ] 2.2 Implement `mpsim/world.py`: a `World` that owns the temporary root, the `file://`
+- [x] 2.2 Implement `mpsim/world.py`: a `World` that owns the temporary root, the `file://`
   bare remote, per-principal clones and worktrees, and a `PrincipalView` that is read-only for
   probes. [M]
   **Dependencies**: 2.1
-- [ ] 2.3 Write failing tests in `test_agents.py`:
+- [x] 2.3 Write failing tests in `test_agents.py`:
   - `ScriptedAgent` writes the step's OpenSpec files under a `sim-` change id;
   - it commits as its principal and pushes to `refs/heads/sim/<principal>/<change>`;
   - it returns the step's declared status transitions and never modifies `roadmap.yaml` or
@@ -101,10 +101,10 @@
   **Spec scenarios**: P.1
   **Design decisions**: D5, D7
   **Dependencies**: 2.2
-- [ ] 2.4 Implement `mpsim/agents.py` (the `Agent` protocol and `ScriptedAgent`) and
+- [x] 2.4 Implement `mpsim/agents.py` (the `Agent` protocol and `ScriptedAgent`) and
   `mpsim/clock.py`. [S]
   **Dependencies**: 2.3
-- [ ] 2.5 Write failing tests in `test_report.py`:
+- [x] 2.5 Write failing tests in `test_report.py`:
   - the report builder emits sorted-key JSON with every schema property present, using `null`
     for anything that does not apply;
   - it validates against the promoted `sim-report.schema.json`;
@@ -115,24 +115,24 @@
   **Spec scenarios**: D.2
   **Design decisions**: D8
   **Dependencies**: 1.2, 2.4
-- [ ] 2.6 Implement `mpsim/report.py`. [S]
+- [x] 2.6 Implement `mpsim/report.py`. [S]
   **Dependencies**: 2.5
 
 ## 3. Collision oracle (parallel-safe with section 2)
 
-- [ ] 3.1 Write failing tests in `test_oracle.py`. Two spec deltas that name the same
+- [x] 3.1 Write failing tests in `test_oracle.py`. Two spec deltas that name the same
   `### Requirement:` heading of the same capability give `collision_present: true`. Different
   headings, or the same heading in different capabilities, give `false`. [XS]
   **Spec scenarios**: C.1, C.2
   **Design decisions**: D4
   **Dependencies**: 1.4
-- [ ] 3.2 Implement `mpsim/oracle.py`. It reads only the fixture files and no git history.
+- [x] 3.2 Implement `mpsim/oracle.py`. It reads only the fixture files and no git history.
   [XS]
   **Dependencies**: 3.1
 
 ## 4. Probe seam and collision scenarios
 
-- [ ] 4.1 Write failing tests in `test_probes.py`, against a registry that starts empty:
+- [x] 4.1 Write failing tests in `test_probes.py`, against a registry that starts empty:
   - a stub probe reporting a requirement-level collision sets `collision_detected: true`
     (S.1);
   - a probe that raises is recorded as `status: error` with a non-empty `error`, and the run
@@ -149,12 +149,12 @@
   **Spec scenarios**: S.1, S.2, S.3, S.4, S.5
   **Design decisions**: D4
   **Dependencies**: 2.6, 3.2
-- [ ] 4.2 Implement `mpsim/probes/__init__.py`: the `CollisionProbe` protocol, `ProbeResult`,
+- [x] 4.2 Implement `mpsim/probes/__init__.py`: the `CollisionProbe` protocol, `ProbeResult`,
   the module-level registry with register and select, and per-probe timeout enforcement.
   Leave no probe registered by default, and add a comment marking where `ri-06` adds its
   import line. [S]
   **Dependencies**: 4.1
-- [ ] 4.3 Author fixtures under `fixtures/same-requirement-collision/` and
+- [x] 4.3 Author fixtures under `fixtures/same-requirement-collision/` and
   `fixtures/different-requirement-control/`:
   - a seeded capability spec `openspec/specs/sim-notes/spec.md` with at least two
     requirements;
@@ -168,7 +168,7 @@
   **Spec scenarios**: C.1, C.2, C.3
   **Design decisions**: D4, D6
   **Dependencies**: 4.2
-- [ ] 4.4 Implement `mpsim/scenarios/collision.py`. It registers both collision scenarios.
+- [x] 4.4 Implement `mpsim/scenarios/collision.py`. It registers both collision scenarios.
   Alice plans, pushes and finishes. Bob fetches, then plans. At Bob's plan step it runs the
   oracle and the selected probes and fills `collision_present`, `collision_detected` and
   `probes`. [M]
@@ -176,7 +176,7 @@
 
 ## 5. Memory-store scenario (parallel-safe with section 4)
 
-- [ ] 5.1 Author fixtures under `fixtures/memory-store-blocked-dependency/` and
+- [x] 5.1 Author fixtures under `fixtures/memory-store-blocked-dependency/` and
   `fixtures/independent-principals-control/`. Each needs:
   - a `roadmap.yaml` that validates against the real roadmap schema. In the first fixture,
     `ri-retrieval` declares `depends_on: [ri-storage]`; in the control the two items are
@@ -205,7 +205,7 @@
   **Spec scenarios**: B.1, B.2, B.3, B.4, B.5, B.6
   **Design decisions**: D5, D7
   **Dependencies**: 2.6
-- [ ] 5.2 Implement `mpsim/applier.py` (the status applier, which commits declared
+- [x] 5.2 Implement `mpsim/applier.py` (the status applier, which commits declared
   transitions to `roadmap.yaml` on `main` as `sim-supervisor` and pushes) and
   `mpsim/scenarios/blocked.py`, the tick scheduler:
   - follow the intra-tick order from D5 exactly: finishing steps push their work to their
@@ -224,7 +224,7 @@
 
 ## 6. CLI and determinism
 
-- [ ] 6.1 Write failing tests in `test_cli.py`, running `bin/mpsim` by subprocess:
+- [x] 6.1 Write failing tests in `test_cli.py`, running `bin/mpsim` by subprocess:
   - `list` prints the four scenario ids in sorted order;
   - `run` with an unknown scenario, an unknown probe, a `--fixture-dir` that does not exist,
     `--tick-budget 0`, or a one-principal `--fixture-dir` exits 64 and names the problem on
@@ -245,13 +245,13 @@
   **Contracts**: openspec/contracts/multiplayer-simulation/cli/mpsim.yaml
   **Design decisions**: D8, D9
   **Dependencies**: 4.4, 5.2
-- [ ] 6.2 Implement `mpsim/__main__.py` exactly per the CLI contract: the `list` and `run`
+- [x] 6.2 Implement `mpsim/__main__.py` exactly per the CLI contract: the `list` and `run`
   commands, the four `run` flags, and exit codes 0, 1, 2 and 64. [S]
   **Dependencies**: 6.1
 
 ## 7. gen-eval pack and offline guarantees
 
-- [ ] 7.1 Generate `evaluation/descriptor.yaml` with
+- [x] 7.1 Generate `evaluation/descriptor.yaml` with
   `packages/gen-eval/scripts/generate_tool_descriptor.py --contract
   openspec/contracts/multiplayer-simulation/cli/mpsim.yaml --out
   skills/tests/multiplayer-simulation/evaluation/descriptor.yaml`. Add a test that runs the
@@ -260,7 +260,7 @@
   **Spec scenarios**: G.4
   **Design decisions**: D3, D8
   **Dependencies**: 1.2, 1.3
-- [ ] 7.2 Author `evaluation/scenarios/*.yaml` as gen-eval CLI-transport scenarios:
+- [x] 7.2 Author `evaluation/scenarios/*.yaml` as gen-eval CLI-transport scenarios:
   - one for each of the four named scenarios. Each pins its baseline in `expect.body` and
     carries a comment naming `ri-06` (collision) or `ri-11` (blocked ticks) as the item that
     flips it;
@@ -272,7 +272,7 @@
   **Spec scenarios**: G.1, C.1, C.2, B.1, B.2
   **Design decisions**: D8
   **Dependencies**: 6.2, 7.1
-- [ ] 7.3 Write `test_gen_eval_pack.py`:
+- [x] 7.3 Write `test_gen_eval_pack.py`:
   - run the `gen-eval` console script on `evaluation/descriptor.yaml` with
     `--fail-threshold 1.0`, with `bin/` prepended to `PATH` and the harness root as the
     working directory, and expect exit 0 (G.1);
@@ -288,7 +288,7 @@
 
 ## 8. Archive stability and documentation
 
-- [ ] 8.1 Write `test_archive_stability.py`. Every `sim-` change id used by any fixture must be
+- [x] 8.1 Write `test_archive_stability.py`. Every `sim-` change id used by any fixture must be
   absent from the repository's real change ids, active and archived, read the same way
   `skills/tests/openspec_paths/test_change_path_stability.py` reads them (A.2). Run that guard
   and expect no violation under `skills/tests/multiplayer-simulation/` (A.1). A.3 holds by
@@ -297,7 +297,7 @@
   **Spec scenarios**: A.1, A.2, A.3
   **Design decisions**: D10
   **Dependencies**: 7.3
-- [ ] 8.2 Write `skills/tests/multiplayer-simulation/README.md`. It should cover:
+- [x] 8.2 Write `skills/tests/multiplayer-simulation/README.md`. It should cover:
   - what the harness measures and why baselines are characterisations, not targets;
   - how `ri-06` registers a probe (one import line plus flipping `collision_detected`);
   - where `ri-11` must look: the `Roadmap.ready_items` call site in `scenarios/blocked.py`,
@@ -311,7 +311,7 @@
 
 ## 9. Verification
 
-- [ ] 9.1 Run the following and record their results in the validation report:
+- [x] 9.1 Run the following and record their results in the validation report:
   - the harness directory with `pytest`, recording its wall time against the 30-second
     budget;
   - `skills/tests/ci_coverage/` and `skills/tests/openspec_paths/`;
@@ -321,6 +321,13 @@
   [XS]
   **Dependencies**: 8.1, 8.2
 
+> **9.1 results (2026-10-09):** harness `pytest` 93 passed in 34 s wall time. That is over the
+> 30 s budget; about 8 s of it is `test_archive_stability.py` running the whole-tree path-stability
+> guard in a subprocess. The budget is recorded, not asserted (plan finding, iteration 3).
+> `tests/ci_coverage` and `tests/openspec_paths` pass, `ruff check` is clean, and
+> `openspec validate multiplayer-simulation-harness --strict` is valid. gen-eval pack: 10/10 scenarios
+> pass at `--fail-threshold 1.0`, 100% coverage, no "Invalid scenario" lines.
+
 ## Dependency Graph Summary
 
 ```
diff --git a/openspec/contracts/README.md b/openspec/contracts/README.md
index 1221e83..f288710 100644
--- a/openspec/contracts/README.md
+++ b/openspec/contracts/README.md
@@ -68,6 +68,7 @@ live code references.
 | `roadmap-orchestration` | `bounded-dispatch-context.schema.json`, `supervised-dispatch-request.schema.json`, `supervised-dispatch-result.schema.json`, `delegated-dispatch-attempt.schema.json` | `wire-supervise-execution-through-the-dispatch-fn-seam` (ri-03) |
 | `gen-eval-framework` | `schemas/cli-contract.schema.json`, `cli/gen-eval.yaml` | `derive-descriptors-from-contracts` (**in flight**) |
 | `semantic-context-evaluation` | `context-eval-report.schema.json`, `context-eval-corpus.schema.json`, `context-eval-case.schema.json` | `gate-semantic-context-default-enablement` (ri-13) |
+| `multiplayer-simulation` | `schemas/sim-report.schema.json`, `cli/mpsim.yaml` | `multiplayer-simulation-harness` (ri-05) |
 
 `gen-eval-framework` and `semantic-context-evaluation` are both promoted while
 their changes are still in flight rather than at archival. That is the workflow
diff --git a/openspec/contracts/multiplayer-simulation/cli/mpsim.yaml b/openspec/contracts/multiplayer-simulation/cli/mpsim.yaml
new file mode 100644
index 0000000..d198164
--- /dev/null
+++ b/openspec/contracts/multiplayer-simulation/cli/mpsim.yaml
@@ -0,0 +1,105 @@
+# mpsim CLI contract: the multi-player simulation driver (design D8).
+#
+# Ground truth for the ToolDescriptor at
+# skills/tests/multiplayer-simulation/evaluation/descriptor.yaml, generated by
+# packages/gen-eval/scripts/generate_tool_descriptor.py. Authored here while the
+# change is in flight; promoted to
+# openspec/contracts/multiplayer-simulation/cli/mpsim.yaml by task 1.2 so the
+# harness never reads a path that moves on archival (design D10).
+#
+# Validates against ../../../../contracts/gen-eval-framework/schemas/cli-contract.schema.json
+# (path relative to this file's change-local location).
+#
+# `--help` is supplied by argparse and is deliberately not declared, matching
+# the gen-eval contract's convention.
+
+contract_version: "1"
+
+tool:
+  name: mpsim
+  executable: mpsim
+  description: >-
+    Deterministic, offline multi-player simulation driver. Builds a temporary
+    world of two or more simulated principals sharing a local bare git remote,
+    runs one named scenario on a logical tick clock, and prints a single JSON
+    report validating against
+    openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json.
+
+commands:
+  - name: list
+    description: Print the built-in scenario ids as a JSON array, sorted.
+    traceability:
+      requirements:
+        - multiplayer-simulation.scenario-pack-runs-through-gen-eval
+
+  - name: run
+    description: >-
+      Run one scenario and print its report on stdout. Exit 0 whenever the
+      scenario ran to completion, regardless of what was detected or how long
+      a principal was blocked; the scenario file, not the driver, decides what
+      is expected.
+    traceability:
+      requirements:
+        - multiplayer-simulation.simulated-principals-have-separate-identities-worktrees-and-agents
+        - multiplayer-simulation.scenarios-run-offline-without-a-shared-coordinator
+        - multiplayer-simulation.scenario-reports-are-deterministic
+    flags:
+      - name: --scenario
+        type: string
+        required: true
+        description: >-
+          Built-in scenario id (see `mpsim list`). An unknown id exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.same-requirement-collision-scenario-records-plan-time-detection
+            - multiplayer-simulation.memory-store-scenario-reports-time-blocked-on-dependency
+
+      - name: --probe
+        type: string
+        repeatable: true
+        description: >-
+          Restrict the run to the named registered collision probes. Omitted,
+          every registered probe runs. An unregistered id exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.plan-time-detectors-attach-through-a-probe-seam
+
+      - name: --tick-budget
+        type: integer
+        default: 50
+        description: >-
+          Maximum logical ticks before the scheduler stops. A principal still
+          blocked at the budget is reported with unblocked=false and
+          blocked_ticks equal to the budget minus its earliest start tick.
+          A value below 1 exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.memory-store-scenario-reports-time-blocked-on-dependency
+
+      - name: --fixture-dir
+        type: path
+        description: >-
+          Replace the scenario's built-in fixture directory. Used by tests to
+          supply altered fixtures without editing the shipped ones. A missing
+          directory, or a fixture declaring fewer than two principals, exits 64.
+        traceability:
+          requirements:
+            - multiplayer-simulation.simulated-principals-have-separate-identities-worktrees-and-agents
+            - multiplayer-simulation.same-requirement-collision-scenario-records-plan-time-detection
+
+exit_codes:
+  - code: 0
+    meaning: The scenario ran to completion and a report was printed.
+  - code: 1
+    meaning: >-
+      The scenario could not be established (for example the oracle found the
+      fixture's required collision absent, or a git operation failed). A report
+      carrying a non-null `error` is printed when possible.
+  - code: 2
+    meaning: Argparse usage error, e.g. missing subcommand or --scenario.
+  - code: 64
+    meaning: >-
+      Semantic usage error: unknown scenario, unknown probe, a --fixture-dir
+      that does not exist, --tick-budget below 1, or a fixture with fewer than two
+      principals.
+    sysexits_name: EX_USAGE
diff --git a/openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json b/openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json
new file mode 100644
index 0000000..7380991
--- /dev/null
+++ b/openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json
@@ -0,0 +1,234 @@
+{
+  "$schema": "https://json-schema.org/draft/2020-12/schema",
+  "$id": "https://raw.githubusercontent.com/jankneumann/agentic-coding-tools/main/openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json",
+  "title": "mpsim scenario report",
+  "description": "One report per `mpsim run`. Ephemeral test output, not canonical state (design D8). Every property is always present; properties that do not apply to a scenario are null so gen-eval body assertions stay uniform across the pack. No absolute paths, temp directory names, commit SHAs, or wall-clock timestamps may appear (requirement: Scenario Reports Are Deterministic). An exit-1 error report (non-null `error`) may carry an empty `principals` array and a null `timeline`, because the failure can happen before the world exists; every other report must name at least two principals and carry a timeline.",
+  "type": "object",
+  "additionalProperties": false,
+  "required": [
+    "schema_version",
+    "scenario_id",
+    "principals",
+    "collision_present",
+    "collision_detected",
+    "probes",
+    "blocked_ticks",
+    "unblocked",
+    "final_tick",
+    "timeline",
+    "error"
+  ],
+  "properties": {
+    "schema_version": {
+      "const": "1"
+    },
+    "scenario_id": {
+      "type": "string",
+      "pattern": "^[a-z0-9][a-z0-9-]*$"
+    },
+    "principals": {
+      "type": "array",
+      "minItems": 0,
+      "items": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": [
+          "name",
+          "agent_id",
+          "change_id"
+        ],
+        "properties": {
+          "name": {
+            "type": "string",
+            "pattern": "^[a-z0-9][a-z0-9-]*$"
+          },
+          "agent_id": {
+            "type": "string",
+            "minLength": 1
+          },
+          "change_id": {
+            "type": "string",
+            "pattern": "^sim-[a-z0-9-]+$"
+          }
+        }
+      }
+    },
+    "collision_present": {
+      "type": [
+        "boolean",
+        "null"
+      ],
+      "description": "Ground-truth oracle over fixture contents (design D4). Null for scenarios with no collision question."
+    },
+    "collision_detected": {
+      "type": [
+        "boolean",
+        "null"
+      ],
+      "description": "True only when a probe with status ok reported a requirement-level collision against the other principal's change. Null for scenarios with no collision question."
+    },
+    "probes": {
+      "type": [
+        "array",
+        "null"
+      ],
+      "items": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": [
+          "probe_id",
+          "status",
+          "collisions",
+          "error"
+        ],
+        "properties": {
+          "probe_id": {
+            "type": "string",
+            "minLength": 1
+          },
+          "status": {
+            "enum": [
+              "ok",
+              "error"
+            ]
+          },
+          "collisions": {
+            "type": "array",
+            "items": {
+              "type": "object",
+              "additionalProperties": false,
+              "required": [
+                "level",
+                "other_change",
+                "requirement"
+              ],
+              "properties": {
+                "level": {
+                  "enum": [
+                    "intent",
+                    "requirement",
+                    "contract",
+                    "file"
+                  ]
+                },
+                "other_change": {
+                  "type": "string"
+                },
+                "requirement": {
+                  "type": [
+                    "string",
+                    "null"
+                  ]
+                }
+              }
+            }
+          },
+          "error": {
+            "type": [
+              "string",
+              "null"
+            ]
+          }
+        }
+      }
+    },
+    "blocked_ticks": {
+      "type": [
+        "object",
+        "null"
+      ],
+      "description": "Per principal: first tick its implement step is admitted by Roadmap.ready_items minus the tick its own preceding steps finished (design D5).",
+      "additionalProperties": {
+        "type": "integer",
+        "minimum": 0
+      }
+    },
+    "unblocked": {
+      "type": [
+        "object",
+        "null"
+      ],
+      "additionalProperties": {
+        "type": "boolean"
+      }
+    },
+    "final_tick": {
+      "type": [
+        "integer",
+        "null"
+      ],
+      "minimum": 0
+    },
+    "timeline": {
+      "type": [
+        "array",
+        "null"
+      ],
+      "items": {
+        "type": "object",
+        "additionalProperties": false,
+        "required": [
+          "tick",
+          "principal",
+          "step",
+          "event"
+        ],
+        "properties": {
+          "tick": {
+            "type": "integer",
+            "minimum": 0
+          },
+          "principal": {
+            "type": "string"
+          },
+          "step": {
+            "enum": [
+              "plan",
+              "contract",
+              "implement"
+            ]
+          },
+          "event": {
+            "enum": [
+              "started",
+              "finished",
+              "blocked",
+              "admitted",
+              "pushed",
+              "probed",
+              "status_applied"
+            ]
+          }
+        }
+      }
+    },
+    "error": {
+      "type": [
+        "string",
+        "null"
+      ],
+      "description": "Non-null only when the process exits 1. When non-null, `principals` may be empty and `timeline` may be null."
+    }
+  },
+  "allOf": [
+    {
+      "if": {
+        "properties": {
+          "error": {
+            "type": "null"
+          }
+        }
+      },
+      "then": {
+        "properties": {
+          "principals": {
+            "minItems": 2
+          },
+          "timeline": {
+            "type": "array"
+          }
+        }
+      }
+    }
+  ]
+}
diff --git a/skills/autopilot/scripts/convergence_loop.py b/skills/autopilot/scripts/convergence_loop.py
index bc4addc..b33c1c9 100644
--- a/skills/autopilot/scripts/convergence_loop.py
+++ b/skills/autopilot/scripts/convergence_loop.py
@@ -566,6 +566,25 @@ def _changed_paths(
     return sorted(names)
 
 
+#: converge()'s own bookkeeping under ``artifacts_dir``: the review ledger and
+#: the per-round packet/checkpoint cache. converge writes them itself
+#: (``save_ledger`` runs before the pre-fix snapshot), never a fix callback.
+_BOOKKEEPING_DIRS = (".review-ledger", ".review-cache")
+
+
+def _without_bookkeeping(
+    changed: list[str], *, worktree_path: Path, artifacts_dir: Path,
+) -> list[str]:
+    """``changed`` minus converge's own ``artifacts_dir`` bookkeeping paths, so
+    the post-fix scope check sees only the fix callback's edits."""
+    try:
+        base = Path(artifacts_dir).resolve().relative_to(Path(worktree_path).resolve())
+    except ValueError:
+        return changed  # artifacts outside the worktree never appear in git output
+    prefixes = tuple(f"{(base / name).as_posix()}/" for name in _BOOKKEEPING_DIRS)
+    return [path for path in changed if not path.startswith(prefixes)]
+
+
 def _compute_vendor_agreement_rate(
     consensus_dict: dict[str, Any] | None,
 ) -> float:
@@ -683,6 +702,7 @@ def converge(
     blocking_criticalities: set[str] | None = None,
     stall_window: int = _DEFAULT_STALL_WINDOW,
     fact_check: bool = True,
+    base_ref: str | None = None,
 ) -> ConvergenceResult:
     """Run the review-fix convergence loop.
 
@@ -718,6 +738,9 @@ def converge(
             CLI adapter being resolvable, the normal case for a mocked or
             minimal orchestrator) skips the pass for that vendor and keeps
             every finding. Set False to disable entirely.
+        base_ref: Ref the review packet diffs against. ``None`` (default)
+            keeps the packet builder's ``DEFAULT_BASE_REF``; a stacked branch
+            passes its PR base (e.g. ``origin/openspec/<parent>``).
 
     Returns:
         ConvergenceResult with convergence status and details.
@@ -760,6 +783,7 @@ def converge(
             output_dir=checkpoint_dir,
             last_fix_diff=last_fix_diff if round_num > 1 else None,
             ledger=ledger,
+            **({"base_ref": base_ref} if base_ref is not None else {}),
         )
         prompt = packet_path.read_text(encoding="utf-8")
         dispatch_kwargs: dict[str, Any] = {
@@ -1194,7 +1218,11 @@ def converge(
             pre_rev = _snapshot_rev(worktree_path)
             pre_untracked = _untracked_paths(worktree_path)
             fix_callback(payloads, worktree_path)
-            changed = _changed_paths(worktree_path, pre_rev, pre_untracked)
+            changed = _without_bookkeeping(
+                _changed_paths(worktree_path, pre_rev, pre_untracked),
+                worktree_path=worktree_path,
+                artifacts_dir=artifacts_dir,
+            )
             allowed: list[str] = []
             seen_allowed: set[str] = set()
             for payload in payloads:
diff --git a/skills/pyproject.toml b/skills/pyproject.toml
index b7bfce2..9aec82f 100644
--- a/skills/pyproject.toml
+++ b/skills/pyproject.toml
@@ -30,6 +30,9 @@ test = [
     "fastapi>=0.115",
     "httpx>=0.27",
     "PyJWT[crypto]>=2.14.0",
+    # Multiplayer-simulation harness (tests/multiplayer-simulation) runs its
+    # scenario pack through the gen-eval console script, in-process from pytest.
+    "gen-eval",
     # Lint tooling lives here so CI can run `uv run ruff` from this directory.
     # Pinned to the same floor as agent-coordinator so both trees are linted by
     # one ruff version and cannot disagree about what is an error.
@@ -39,6 +42,7 @@ test = [
 [tool.uv.sources]
 system-one-decisions = { path = "../packages/system-one-decisions" }
 openbao-credentials = { path = "../packages/openbao-credentials" }
+gen-eval = { path = "../packages/gen-eval" }
 
 [tool.uv]
 override-dependencies = [
diff --git a/skills/tests/autopilot/test_convergence_loop.py b/skills/tests/autopilot/test_convergence_loop.py
index 53ce49b..1e06525 100644
--- a/skills/tests/autopilot/test_convergence_loop.py
+++ b/skills/tests/autopilot/test_convergence_loop.py
@@ -541,6 +541,56 @@ def test_converge_writes_packet_and_passes_body_as_prompt(tmp_path: Path) -> Non
     assert meta["budget_chars"] == 320000
 
 
+def _converge_capturing_base_ref(tmp_path: Path, **kwargs: object) -> list[object]:
+    """Run one clean round and return the base_ref each packet build received."""
+    artifacts = tmp_path / "artifacts"
+    artifacts.mkdir()
+    results = [
+        _make_review_result("vendor_a", findings=[]),
+        _make_review_result("vendor_b", findings=[]),
+    ]
+    report = _make_consensus_report(findings=[])
+    mock_orchestrator = MagicMock()
+    mock_orchestrator.dispatch_and_wait.return_value = results
+    mock_synthesizer = MagicMock()
+    mock_synthesizer.synthesize.return_value = report
+    real_synth = __import__(
+        "consensus_synthesizer", fromlist=["ConsensusSynthesizer"]
+    ).ConsensusSynthesizer()
+    mock_synthesizer.to_dict.return_value = real_synth.to_dict(report)
+    import convergence_loop
+
+    seen: list[object] = []
+    real_build = convergence_loop.build_review_packet
+
+    def spy(**build_kwargs: object):
+        seen.append(build_kwargs.get("base_ref", "<default>"))
+        return real_build(**build_kwargs)
+
+    with patch("convergence_loop.ConsensusSynthesizer", return_value=mock_synthesizer), \
+            patch("convergence_loop.build_review_packet", side_effect=spy):
+        result = converge(
+            change_id="test-change",
+            review_type="implementation",
+            artifacts_dir=artifacts,
+            worktree_path=tmp_path,
+            orchestrator=mock_orchestrator,
+            **kwargs,
+        )
+    assert result.converged is True
+    return seen
+
+
+def test_converge_passes_base_ref_to_the_review_packet(tmp_path: Path) -> None:
+    """A stacked branch diffs against its PR base, not the hard-coded main."""
+    base = "origin/openspec/roadmap-multiplayer-collaboration"
+    assert _converge_capturing_base_ref(tmp_path, base_ref=base) == [base]
+
+
+def test_converge_without_base_ref_keeps_the_packet_default(tmp_path: Path) -> None:
+    assert _converge_capturing_base_ref(tmp_path) == ["<default>"]
+
+
 def test_missing_ledger_still_runs(tmp_path: Path) -> None:
     artifacts = tmp_path / "artifacts"
     artifacts.mkdir()
@@ -716,6 +766,47 @@ def test_converge_rejects_out_of_scope_fix(tmp_path: Path) -> None:
     assert ledger["items"][0]["status"] == "open"
 
 
+def test_converge_bookkeeping_is_not_a_fix_edit(tmp_path: Path) -> None:
+    """converge's own .review-ledger/ and .review-cache/ writes under
+    artifacts_dir (here tracked, as on a branch that committed an earlier
+    round) are not attributed to the fix callback by the scope check."""
+    _init_git_repo(tmp_path)
+    src = tmp_path / "src"
+    src.mkdir()
+    (src / "api.py").write_text("ok\n")
+    ctx, _finding = _blocking_round(tmp_path)
+    artifacts = ctx["artifacts_dir"]
+    ledger_dir = artifacts / ".review-ledger"
+    ledger_dir.mkdir()
+    (ledger_dir / "ledger.json").write_text(
+        json.dumps({"change_id": "test-change", "items": []}) + "\n"
+    )
+    cache = artifacts / ".review-cache" / "round-1"
+    cache.mkdir(parents=True)
+    (cache / "review-packet.md").write_text("stale\n")
+    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
+    subprocess.run(
+        ["git", "commit", "-m", "earlier round"], cwd=tmp_path, check=True, capture_output=True,
+    )
+
+    def edit_allowed(_blocking: list, worktree: Path) -> None:
+        (worktree / "src" / "api.py").write_text("fixed\n")
+
+    with patch("convergence_loop.ConsensusSynthesizer", return_value=ctx["synthesizer"]):
+        converge(
+            change_id="test-change",
+            review_type="implementation",
+            artifacts_dir=artifacts,
+            worktree_path=tmp_path,
+            orchestrator=ctx["orchestrator"],
+            fix_callback=edit_allowed,
+        )
+    # Accepted by the scope check (no ScopeViolation), then retired by the
+    # clean second round.
+    ledger = load_or_create(artifacts, "test-change")
+    assert ledger["items"][0]["status"] in {"addressed", "retired"}
+
+
 def test_last_fix_diff_includes_committed_callback_edits(tmp_path: Path) -> None:
     _init_git_repo(tmp_path)
     ctx, _finding = _blocking_round(tmp_path)
diff --git a/skills/tests/multiplayer-simulation/README.md b/skills/tests/multiplayer-simulation/README.md
new file mode 100644
index 0000000..e5ff95e
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/README.md
@@ -0,0 +1,91 @@
+# multiplayer-simulation harness
+
+A deterministic, offline simulation of several principals sharing one git remote. It gives
+`ri-06` (plan-time collision detection) and `ri-11` (contract-level dependencies) a recorded
+baseline to flip. Spec: capability `multiplayer-simulation`; design decisions D1-D10 in the
+change's `design.md`.
+
+## What it measures, and why baselines are characterisations
+
+Two questions, each with a scenario and a control:
+
+| Scenario | Question | Baseline pinned today |
+|---|---|---|
+| `same-requirement-collision` | Two principals modify the same requirement. Was it detected at plan time? | `collision_present: true`, `collision_detected: false`, `probes: []` |
+| `different-requirement-control` | Same, but different requirements. | no collision, none detected |
+| `memory-store-blocked-dependency` | How many ticks is the dependent principal blocked? | `blocked_ticks` `{retrieval-owner: 10, storage-owner: 0}` |
+| `independent-principals-control` | Same, with no dependency edge. | all zeros |
+
+The pinned values record what the system does **now**. They are characterisations, not
+targets: "not detected" and "10 ticks blocked" are not claims that the behaviour is right,
+only that a later change moves them on purpose. Every pinned expectation in
+`evaluation/scenarios/` carries a comment naming the roadmap item that flips it, and a test
+enforces that.
+
+## How `ri-06` registers a probe
+
+1. Write a probe class with a `probe_id` and `detect(view, change_id) -> ProbeResult`
+   (see `mpsim/probes/__init__.py`). `view` is read-only.
+2. Add **one import line** at the bottom of `mpsim/probes/__init__.py` (the marked spot) that
+   registers it.
+3. Edit the pinned expectation in `evaluation/scenarios/collision.yaml`:
+   `collision_detected: true` for `same-requirement-collision` and a non-empty `probes`.
+   No scenario module under `mpsim/scenarios/` changes.
+
+`collision_present` comes from the oracle (`mpsim/oracle.py`), which only compares fixture
+files. It is never a probe.
+
+## Where `ri-11` must look
+
+- The call site: `Roadmap.ready_items()` in `mpsim/scenarios/blocked.py`. The scheduler holds no
+  readiness logic of its own.
+- The fixture dependency form: `fixtures/memory-store-blocked-dependency/seed/roadmap.yaml`
+  (today a bare `depends_on`).
+- Status transitions are fixture data: `on_start` / `on_finish` `set_status` in
+  `fixtures/*/scenario.yaml`. A `contract` step that declares a new status needs only a fixture
+  edit.
+- The pinned `blocked_ticks` in `evaluation/scenarios/blocked.yaml` (10 today, 2 under the
+  baseline durations once dependents may start on contract completion).
+
+## Layout
+
+```
+mpsim/            driver: world, agents, clock, oracle, report, applier, runner, CLI
+  probes/         collision probe seam
+  scenarios/      one module per scenario family, discovered with pkgutil
+bin/mpsim         launcher (python -m mpsim)
+fixtures/         per-scenario data: scenario.yaml, seed/, per-step file trees
+evaluation/       descriptor.yaml (generated) and scenarios/*.yaml (the gen-eval pack)
+test_*.py         the suite
+```
+
+`roadmap.yaml` has one authoritative copy: `main` on the shared remote. Principals never edit it
+or push to `main`; `mpsim/applier.py` (a simulated supervisor, committing as `sim-supervisor`
+from its own clone) writes every status change a fixture declares.
+
+## Adding a scenario
+
+1. Add a fixture directory under `fixtures/<scenario-id>/` with `scenario.yaml`, a `seed/` tree
+   and any `files_from` directories.
+2. Add a module under `mpsim/scenarios/` exposing a module-level `SCENARIOS` mapping of
+   `Scenario` objects. Nothing else lists it.
+3. Add a gen-eval scenario under `evaluation/scenarios/` with a comment naming the item that
+   flips each pinned value.
+4. Fixture change ids must start with `sim-` and never match a real change id.
+
+## Running locally
+
+```bash
+cd skills
+uv run pytest tests/multiplayer-simulation          # the whole suite
+uv run ruff check tests/multiplayer-simulation
+PATH=tests/multiplayer-simulation/bin:$PATH uv run python -m mpsim list   # from the harness dir
+```
+
+Regenerate the descriptor after editing the CLI contract:
+
+```bash
+python packages/gen-eval/scripts/generate_tool_descriptor.py \
+  --contract openspec/contracts/multiplayer-simulation/cli/mpsim.yaml \
+  --out skills/tests/multiplayer-simulation/evaluation/descriptor.yaml
+```
diff --git a/skills/tests/multiplayer-simulation/bin/mpsim b/skills/tests/multiplayer-simulation/bin/mpsim
new file mode 100755
index 0000000..c9c8963
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/bin/mpsim
@@ -0,0 +1,9 @@
+#!/usr/bin/env python3
+"""Launcher: run ``python -m mpsim`` with the harness root on ``sys.path``."""
+
+import runpy
+import sys
+from pathlib import Path
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
+runpy.run_module("mpsim", run_name="__main__", alter_sys=True)
diff --git a/skills/tests/multiplayer-simulation/conftest.py b/skills/tests/multiplayer-simulation/conftest.py
new file mode 100644
index 0000000..6148107
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/conftest.py
@@ -0,0 +1,51 @@
+"""Path setup and offline enforcement for the multiplayer-simulation harness.
+
+Puts the harness root (so ``import mpsim`` works) and ``roadmap-runtime/scripts``
+(so the driver can call the real admission rule) on ``sys.path``, following
+``skills/tests/roadmap-runtime/conftest.py``. The autouse fixture below implements
+design D9: any ``AF_INET``/``AF_INET6`` connect raises, so an accidental network
+call fails the test immediately instead of hanging in CI.
+"""
+
+from __future__ import annotations
+
+import socket
+import sys
+from pathlib import Path
+
+import pytest
+
+HARNESS_ROOT = Path(__file__).resolve().parent
+_RUNTIME_SCRIPTS = HARNESS_ROOT.parent.parent / "roadmap-runtime" / "scripts"
+
+for _p in (HARNESS_ROOT, _RUNTIME_SCRIPTS):
+    if str(_p) not in sys.path:
+        sys.path.insert(0, str(_p))
+
+
+class NetworkBlockedError(OSError):
+    """Raised when a harness test tries to open an inet socket connection."""
+
+
+_INET_FAMILIES = (socket.AF_INET, socket.AF_INET6)
+
+
+@pytest.fixture(autouse=True)
+def _block_inet_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
+    def _blocked(self: socket.socket, *args: object, **kwargs: object) -> None:
+        if self.family in _INET_FAMILIES:
+            raise NetworkBlockedError(
+                "network access is blocked in multiplayer-simulation tests (design D9)"
+            )
+        raise AssertionError("non-inet connect is not expected in this harness")
+
+    def _wrap(original):
+        def patched(self: socket.socket, *args: object, **kwargs: object):
+            if self.family in _INET_FAMILIES:
+                return _blocked(self, *args, **kwargs)
+            return original(self, *args, **kwargs)
+
+        return patched
+
+    monkeypatch.setattr(socket.socket, "connect", _wrap(socket.socket.connect))
+    monkeypatch.setattr(socket.socket, "connect_ex", _wrap(socket.socket.connect_ex))
diff --git a/skills/tests/multiplayer-simulation/evaluation/descriptor.yaml b/skills/tests/multiplayer-simulation/evaluation/descriptor.yaml
new file mode 100644
index 0000000..764fe48
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/evaluation/descriptor.yaml
@@ -0,0 +1,83 @@
+# GENERATED FILE — do not edit by hand.
+#
+# Derived from ../../../../openspec/contracts/multiplayer-simulation/cli/mpsim.yaml by scripts/generate_tool_descriptor.py.
+# Edit the contract and regenerate:
+#
+#     python scripts/generate_tool_descriptor.py
+#
+# CI runs the same script with --check; an edit made here and not made in the
+# contract fails that gate rather than silently becoming the source of truth.
+
+project: mpsim
+version: '1'
+executable: mpsim
+contract: ../../../../openspec/contracts/multiplayer-simulation/cli/mpsim.yaml
+services:
+- name: mpsim-cli
+  type: cli
+  command: mpsim
+scenario_dirs:
+- scenarios
+commands:
+- name: list
+  description: Print the built-in scenario ids as a JSON array, sorted.
+  traceability:
+    requirements:
+    - multiplayer-simulation.scenario-pack-runs-through-gen-eval
+- name: run
+  description: Run one scenario and print its report on stdout. Exit 0 whenever the scenario ran to completion,
+    regardless of what was detected or how long a principal was blocked; the scenario file, not the driver,
+    decides what is expected.
+  flags:
+  - name: --scenario
+    type: string
+    required: true
+    description: Built-in scenario id (see `mpsim list`). An unknown id exits 64.
+    traceability:
+      requirements:
+      - multiplayer-simulation.same-requirement-collision-scenario-records-plan-time-detection
+      - multiplayer-simulation.memory-store-scenario-reports-time-blocked-on-dependency
+  - name: --probe
+    type: string
+    repeatable: true
+    description: Restrict the run to the named registered collision probes. Omitted, every registered
+      probe runs. An unregistered id exits 64.
+    traceability:
+      requirements:
+      - multiplayer-simulation.plan-time-detectors-attach-through-a-probe-seam
+  - name: --tick-budget
+    type: integer
+    default: 50
+    description: Maximum logical ticks before the scheduler stops. A principal still blocked at the budget
+      is reported with unblocked=false and blocked_ticks equal to the budget minus its earliest start
+      tick. A value below 1 exits 64.
+    traceability:
+      requirements:
+      - multiplayer-simulation.memory-store-scenario-reports-time-blocked-on-dependency
+  - name: --fixture-dir
+    type: path
+    description: Replace the scenario's built-in fixture directory. Used by tests to supply altered fixtures
+      without editing the shipped ones. A missing directory, or a fixture declaring fewer than two principals,
+      exits 64.
+    traceability:
+      requirements:
+      - multiplayer-simulation.simulated-principals-have-separate-identities-worktrees-and-agents
+      - multiplayer-simulation.same-requirement-collision-scenario-records-plan-time-detection
+  traceability:
+    requirements:
+    - multiplayer-simulation.simulated-principals-have-separate-identities-worktrees-and-agents
+    - multiplayer-simulation.scenarios-run-offline-without-a-shared-coordinator
+    - multiplayer-simulation.scenario-reports-are-deterministic
+exit_codes:
+- code: 0
+  meaning: The scenario ran to completion and a report was printed.
+- code: 1
+  meaning: The scenario could not be established (for example the oracle found the fixture's required
+    collision absent, or a git operation failed). A report carrying a non-null `error` is printed when
+    possible.
+- code: 2
+  meaning: Argparse usage error, e.g. missing subcommand or --scenario.
+- code: 64
+  meaning: 'Semantic usage error: unknown scenario, unknown probe, a --fixture-dir that does not exist,
+    --tick-budget below 1, or a fixture with fewer than two principals.'
+  sysexits_name: EX_USAGE
diff --git a/skills/tests/multiplayer-simulation/evaluation/scenarios/blocked.yaml b/skills/tests/multiplayer-simulation/evaluation/scenarios/blocked.yaml
new file mode 100644
index 0000000..18f0fe4
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/evaluation/scenarios/blocked.yaml
@@ -0,0 +1,89 @@
+# Memory-store blocked-dependency scenarios (design D5).
+#
+# These pin the BASELINE in force when the harness landed. Today a bare
+# `depends_on` blocks the dependent until the dependency's implement step has
+# completed, so retrieval-owner waits 10 ticks. They are characterisations of the
+# present admission rule (Roadmap.ready_items), not targets.
+
+- id: memory-store-blocked-dependency
+  name: The dependent principal is blocked until the dependency is implemented
+  description: >
+    storage-owner (plan 1, contract 2, implement 8) finishes implementing at tick
+    11. retrieval-owner (plan 1, implement 4) can start at tick 1 but is not
+    admitted by Roadmap.ready_items until ri-storage is completed on main.
+  category: blocked-time
+  priority: 1
+  interfaces: ["cli:run", "cli:--scenario"]
+  tags: [blocked-time, baseline, multiplayer-simulation]
+  steps:
+    - id: run
+      transport: cli
+      command: run
+      args: ["--scenario", "memory-store-blocked-dependency"]
+      expect:
+        exit_code: 0
+        body:
+          # BASELINE, flipped by ri-11 (contract-level dependencies): once a
+          # dependent may start on the contract rather than on completion, this
+          # drops to 2 under the baseline durations.
+          blocked_ticks:
+            retrieval-owner: 10
+            storage-owner: 0
+          unblocked:
+            retrieval-owner: true
+            storage-owner: true
+      timeout_seconds: 60
+
+- id: independent-principals-control
+  name: Independent principals are never blocked
+  description: >
+    The control for memory-store-blocked-dependency. With no dependency edge the
+    admission rule admits both principals as soon as their own preceding steps
+    finish.
+  category: blocked-time
+  priority: 1
+  interfaces: ["cli:run", "cli:--scenario"]
+  tags: [blocked-time, control, multiplayer-simulation]
+  steps:
+    - id: run
+      transport: cli
+      command: run
+      args: ["--scenario", "independent-principals-control"]
+      expect:
+        exit_code: 0
+        body:
+          # Control for ri-11: must stay all zeros after contract-level
+          # dependencies land.
+          blocked_ticks:
+            retrieval-owner: 0
+            storage-owner: 0
+      timeout_seconds: 60
+
+- id: tick-budget-bounds-a-blocked-run
+  name: --tick-budget stops a run whose dependency has not completed
+  description: >
+    A budget of 5 is lower than the dependency's completion tick (11), so the run
+    stops at tick 5 with retrieval-owner still blocked. Without the flag the same
+    scenario runs to tick 15, so final_tick discriminates the flag.
+  category: blocked-time
+  priority: 2
+  interfaces: ["cli:--tick-budget"]
+  tags: [flags, blocked-time, multiplayer-simulation]
+  steps:
+    - id: run-with-budget
+      transport: cli
+      command: run
+      args: ["--scenario", "memory-store-blocked-dependency", "--tick-budget", "5"]
+      expect:
+        exit_code: 0
+        body:
+          final_tick: 5
+          # BASELINE, flipped by ri-11: retrieval-owner would no longer be
+          # blocked at tick 5 once it can start on contract completion.
+          blocked_ticks:
+            retrieval-owner: 4
+            storage-owner: 0
+          unblocked:
+            retrieval-owner: false
+            storage-owner: true
+      timeout_seconds: 60
diff --git a/skills/tests/multiplayer-simulation/evaluation/scenarios/collision.yaml b/skills/tests/multiplayer-simulation/evaluation/scenarios/collision.yaml
new file mode 100644
index 0000000..cd9b3d9
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/evaluation/scenarios/collision.yaml
@@ -0,0 +1,56 @@
+# Plan-time requirement-collision scenarios (design D4).
+#
+# These pin the BASELINE in force when the harness landed: a collision exists in
+# the fixture (the oracle says so) but nothing detects it at plan time, because no
+# collision probe is registered. They are characterisations, not targets.
+
+- id: same-requirement-collision
+  name: Two principals modify the same requirement and nothing detects it
+  description: >
+    Alice pushes a plan that modifies requirement "Note Titles" of the seeded
+    sim-notes capability. Bob fetches, then plans a change that modifies the same
+    requirement. collision_present comes from the ground-truth oracle over the
+    fixture files; collision_detected is true only when a registered probe reported
+    a requirement-level collision. No probe is registered today.
+  category: collision
+  priority: 1
+  interfaces: ["cli:run", "cli:--scenario"]
+  tags: [collision, baseline, multiplayer-simulation]
+  steps:
+    - id: run
+      transport: cli
+      command: run
+      args: ["--scenario", "same-requirement-collision"]
+      expect:
+        exit_code: 0
+        body:
+          scenario_id: same-requirement-collision
+          collision_present: true
+          # BASELINE, flipped by ri-06 (plan-time collision detection): registering
+          # its probe makes this true. Changing it is a reviewed edit, not a harness
+          # change.
+          collision_detected: false
+          probes: []
+      timeout_seconds: 60
+
+- id: different-requirement-control
+  name: Two principals modify different requirements, so nothing collides
+  description: >
+    The control for same-requirement-collision. Bob modifies "Note Bodies", so the
+    oracle reports no collision and a future detector must report none either.
+  category: collision
+  priority: 1
+  interfaces: ["cli:run", "cli:--scenario"]
+  tags: [collision, control, multiplayer-simulation]
+  steps:
+    - id: run
+      transport: cli
+      command: run
+      args: ["--scenario", "different-requirement-control"]
+      expect:
+        exit_code: 0
+        body:
+          collision_present: false
+          # Control for ri-06: must stay false after the detector lands.
+          collision_detected: false
+      timeout_seconds: 60
diff --git a/skills/tests/multiplayer-simulation/evaluation/scenarios/usage.yaml b/skills/tests/multiplayer-simulation/evaluation/scenarios/usage.yaml
new file mode 100644
index 0000000..b924a26
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/evaluation/scenarios/usage.yaml
@@ -0,0 +1,111 @@
+# The list command and the usage-error surface (design D8, exit code 64).
+#
+# Each flag scenario fails if the flag is removed from its args: without it the
+# command exits 0 (or, for --fixture-dir, a different outcome), so the flag is
+# exercised rather than merely parsed.
+
+- id: list-prints-the-four-scenarios
+  name: mpsim list prints the built-in scenario ids, sorted
+  description: >
+    The list command is the discovery surface; its output must name every built-in
+    scenario so a consumer can enumerate them without reading the source.
+  category: usage
+  priority: 2
+  interfaces: ["cli:list"]
+  tags: [list, multiplayer-simulation]
+  steps:
+    - id: list
+      transport: cli
+      command: list
+      expect:
+        exit_code: 0
+        body:
+          result:
+            - different-requirement-control
+            - independent-principals-control
+            - memory-store-blocked-dependency
+            - same-requirement-collision
+      timeout_seconds: 60
+
+- id: unknown-probe-is-a-usage-error
+  name: --probe with an unregistered id exits 64
+  description: >
+    Without --probe the same command exits 0, so the flag is what produces the
+    usage error.
+  category: usage
+  priority: 2
+  interfaces: ["cli:--probe"]
+  tags: [flags, usage-errors, multiplayer-simulation]
+  steps:
+    - id: unknown-probe
+      transport: cli
+      command: run
+      args: ["--scenario", "same-requirement-collision", "--probe", "does-not-exist"]
+      expect:
+        exit_code: 64
+        error_contains: "does-not-exist"
+      timeout_seconds: 60
+
+- id: tick-budget-below-one-is-a-usage-error
+  name: --tick-budget 0 exits 64
+  description: >
+    A budget below 1 is a semantic usage error (EX_USAGE), not an argparse error, so
+    it exits 64 rather than 2 and names the flag on stderr.
+  category: usage
+  priority: 2
+  interfaces: ["cli:--tick-budget"]
+  tags: [flags, usage-errors, multiplayer-simulation]
+  steps:
+    - id: zero-budget
+      transport: cli
+      command: run
+      args: ["--scenario", "memory-store-blocked-dependency", "--tick-budget", "0"]
+      expect:
+        exit_code: 64
+        error_contains: "tick-budget"
+      timeout_seconds: 60
+
+- id: missing-fixture-dir-is-a-usage-error
+  name: --fixture-dir naming a missing directory exits 64
+  description: >
+    A fixture directory that does not exist is a semantic usage error naming the flag.
+  category: usage
+  priority: 2
+  interfaces: ["cli:--fixture-dir"]
+  tags: [flags, usage-errors, multiplayer-simulation]
+  steps:
+    - id: missing-fixture
+      transport: cli
+      command: run
+      args: ["--scenario", "same-requirement-collision", "--fixture-dir", "no/such/fixture"]
+      expect:
+        exit_code: 64
+        error_contains: "fixture-dir"
+      timeout_seconds: 60
+
+- id: fixture-dir-replaces-the-built-in-fixture
+  name: --fixture-dir swaps the fixture, so a control fails loudly on a colliding one
+  description: >
+    The control scenario given the colliding fixture finds a collision it must not
+    have and exits 1 with an error report. Without --fixture-dir it exits 0, so the
+    flag is what changes the outcome. Paths are relative to the harness root, the
+    working directory of the gen-eval run.
+  category: usage
+  priority: 2
+  interfaces: ["cli:--fixture-dir"]
+  tags: [flags, multiplayer-simulation]
+  steps:
+    - id: colliding-fixture-in-a-control
+      transport: cli
+      command: run
+      args:
+        - "--scenario"
+        - "different-requirement-control"
+        - "--fixture-dir"
+        - "fixtures/same-requirement-collision"
+      expect:
+        exit_code: 1
+        body:
+          scenario_id: different-requirement-control
+        error_contains: "unexpected collision"
+      timeout_seconds: 60
diff --git a/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
new file mode 100644
index 0000000..d24c34a
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
@@ -0,0 +1,5 @@
+# Proposal: sim-alice-notes
+
+## Why
+
+Simulated change planned by alice. It modifies the "Note Titles" requirement of sim-notes.
diff --git a/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
new file mode 100644
index 0000000..22b4898
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
@@ -0,0 +1,10 @@
+## MODIFIED Requirements
+
+### Requirement: Note Titles
+
+The system SHALL change how "Note Titles" behaves, as planned by alice.
+
+#### Scenario: Changed behaviour
+
+- **WHEN** the simulated change by alice is applied
+- **THEN** "Note Titles" behaves differently
diff --git a/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
new file mode 100644
index 0000000..2ce5a3b
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
@@ -0,0 +1,5 @@
+# Proposal: sim-bob-notes
+
+## Why
+
+Simulated change planned by bob. It modifies the "Note Bodies" requirement of sim-notes.
diff --git a/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
new file mode 100644
index 0000000..4be4f58
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
@@ -0,0 +1,10 @@
+## MODIFIED Requirements
+
+### Requirement: Note Bodies
+
+The system SHALL change how "Note Bodies" behaves, as planned by bob.
+
+#### Scenario: Changed behaviour
+
+- **WHEN** the simulated change by bob is applied
+- **THEN** "Note Bodies" behaves differently
diff --git a/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/scenario.yaml b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/scenario.yaml
new file mode 100644
index 0000000..304e93d
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/scenario.yaml
@@ -0,0 +1,14 @@
+# Fixture for the plan-time collision scenarios (design D4, D6). All data; no logic.
+principals:
+  - name: alice
+    change_id: sim-alice-notes
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/alice/plan
+  - name: bob
+    change_id: sim-bob-notes
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/bob/plan
diff --git a/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/seed/openspec/specs/sim-notes/spec.md b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/seed/openspec/specs/sim-notes/spec.md
new file mode 100644
index 0000000..d8b22b8
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/different-requirement-control/seed/openspec/specs/sim-notes/spec.md
@@ -0,0 +1,26 @@
+# sim-notes Specification
+
+## Purpose
+
+Seeded capability for the multiplayer-simulation harness. It exists only inside
+simulated worlds.
+
+## Requirements
+
+### Requirement: Note Titles
+
+The system SHALL require every note to carry a non-empty title.
+
+#### Scenario: Title required
+
+- **WHEN** a note is saved without a title
+- **THEN** the save is rejected
+
+### Requirement: Note Bodies
+
+The system SHALL accept note bodies of up to 10000 characters.
+
+#### Scenario: Long body
+
+- **WHEN** a note body exceeds 10000 characters
+- **THEN** the save is rejected
diff --git a/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
new file mode 100644
index 0000000..4b40590
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
@@ -0,0 +1,3 @@
+# Proposal: sim-retrieval-api
+
+Simulated plan by retrieval-owner.
diff --git a/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
new file mode 100644
index 0000000..28cf6e5
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
@@ -0,0 +1,3 @@
+# Proposal: sim-memory-store-core
+
+Simulated plan by storage-owner.
diff --git a/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/scenario.yaml b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/scenario.yaml
new file mode 100644
index 0000000..61c96a6
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/scenario.yaml
@@ -0,0 +1,33 @@
+# Fixture for the blocked-time scenarios (design D5). Durations are logical ticks.
+# Status transitions are declared here as data; the harness code holds none.
+principals:
+  - name: storage-owner
+    change_id: sim-memory-store-core
+    roadmap_item: ri-storage
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/storage-owner/plan
+      # Today's roadmap schema has no contract-complete state, so this step
+      # declares no status. That absence is the baseline gap ri-11 closes.
+      - name: contract
+        duration: 2
+      - name: implement
+        duration: 8
+        on_start:
+          set_status: in_progress
+        on_finish:
+          set_status: completed
+  - name: retrieval-owner
+    change_id: sim-retrieval-api
+    roadmap_item: ri-retrieval
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/retrieval-owner/plan
+      - name: implement
+        duration: 4
+        on_start:
+          set_status: in_progress
+        on_finish:
+          set_status: completed
diff --git a/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/proposal.md b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/proposal.md
new file mode 100644
index 0000000..cdf4d1e
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/proposal.md
@@ -0,0 +1 @@
+# Seed proposal for the simulated roadmap
diff --git a/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/roadmap.yaml b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/roadmap.yaml
new file mode 100644
index 0000000..9f68a38
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/roadmap.yaml
@@ -0,0 +1,19 @@
+schema_version: 1
+roadmap_id: sim-memory-store
+source_proposal: seed/proposal.md
+status: approved
+items:
+- item_id: ri-storage
+  title: Simulated memory store core
+  status: approved
+  priority: 1
+  effort: M
+  depends_on: []
+  change_id: sim-memory-store-core
+- item_id: ri-retrieval
+  title: Simulated retrieval API
+  status: approved
+  priority: 2
+  effort: M
+  depends_on: []
+  change_id: sim-retrieval-api
diff --git a/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
new file mode 100644
index 0000000..4b40590
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
@@ -0,0 +1,3 @@
+# Proposal: sim-retrieval-api
+
+Simulated plan by retrieval-owner.
diff --git a/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
new file mode 100644
index 0000000..28cf6e5
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
@@ -0,0 +1,3 @@
+# Proposal: sim-memory-store-core
+
+Simulated plan by storage-owner.
diff --git a/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/scenario.yaml b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/scenario.yaml
new file mode 100644
index 0000000..61c96a6
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/scenario.yaml
@@ -0,0 +1,33 @@
+# Fixture for the blocked-time scenarios (design D5). Durations are logical ticks.
+# Status transitions are declared here as data; the harness code holds none.
+principals:
+  - name: storage-owner
+    change_id: sim-memory-store-core
+    roadmap_item: ri-storage
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/storage-owner/plan
+      # Today's roadmap schema has no contract-complete state, so this step
+      # declares no status. That absence is the baseline gap ri-11 closes.
+      - name: contract
+        duration: 2
+      - name: implement
+        duration: 8
+        on_start:
+          set_status: in_progress
+        on_finish:
+          set_status: completed
+  - name: retrieval-owner
+    change_id: sim-retrieval-api
+    roadmap_item: ri-retrieval
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/retrieval-owner/plan
+      - name: implement
+        duration: 4
+        on_start:
+          set_status: in_progress
+        on_finish:
+          set_status: completed
diff --git a/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/proposal.md b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/proposal.md
new file mode 100644
index 0000000..cdf4d1e
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/proposal.md
@@ -0,0 +1 @@
+# Seed proposal for the simulated roadmap
diff --git a/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/roadmap.yaml b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/roadmap.yaml
new file mode 100644
index 0000000..5736e43
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/roadmap.yaml
@@ -0,0 +1,19 @@
+schema_version: 1
+roadmap_id: sim-memory-store
+source_proposal: seed/proposal.md
+status: approved
+items:
+- item_id: ri-storage
+  title: Simulated memory store core
+  status: approved
+  priority: 1
+  effort: M
+  depends_on: []
+  change_id: sim-memory-store-core
+- item_id: ri-retrieval
+  title: Simulated retrieval API
+  status: approved
+  priority: 2
+  effort: M
+  depends_on: [ri-storage]
+  change_id: sim-retrieval-api
diff --git a/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
new file mode 100644
index 0000000..d24c34a
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
@@ -0,0 +1,5 @@
+# Proposal: sim-alice-notes
+
+## Why
+
+Simulated change planned by alice. It modifies the "Note Titles" requirement of sim-notes.
diff --git a/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
new file mode 100644
index 0000000..22b4898
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
@@ -0,0 +1,10 @@
+## MODIFIED Requirements
+
+### Requirement: Note Titles
+
+The system SHALL change how "Note Titles" behaves, as planned by alice.
+
+#### Scenario: Changed behaviour
+
+- **WHEN** the simulated change by alice is applied
+- **THEN** "Note Titles" behaves differently
diff --git a/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
new file mode 100644
index 0000000..d5d2ad1
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
@@ -0,0 +1,5 @@
+# Proposal: sim-bob-notes
+
+## Why
+
+Simulated change planned by bob. It modifies the "Note Titles" requirement of sim-notes.
diff --git a/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
new file mode 100644
index 0000000..59d324d
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
@@ -0,0 +1,10 @@
+## MODIFIED Requirements
+
+### Requirement: Note Titles
+
+The system SHALL change how "Note Titles" behaves, as planned by bob.
+
+#### Scenario: Changed behaviour
+
+- **WHEN** the simulated change by bob is applied
+- **THEN** "Note Titles" behaves differently
diff --git a/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/scenario.yaml b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/scenario.yaml
new file mode 100644
index 0000000..304e93d
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/scenario.yaml
@@ -0,0 +1,14 @@
+# Fixture for the plan-time collision scenarios (design D4, D6). All data; no logic.
+principals:
+  - name: alice
+    change_id: sim-alice-notes
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/alice/plan
+  - name: bob
+    change_id: sim-bob-notes
+    steps:
+      - name: plan
+        duration: 1
+        files_from: principals/bob/plan
diff --git a/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/seed/openspec/specs/sim-notes/spec.md b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/seed/openspec/specs/sim-notes/spec.md
new file mode 100644
index 0000000..d8b22b8
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/seed/openspec/specs/sim-notes/spec.md
@@ -0,0 +1,26 @@
+# sim-notes Specification
+
+## Purpose
+
+Seeded capability for the multiplayer-simulation harness. It exists only inside
+simulated worlds.
+
+## Requirements
+
+### Requirement: Note Titles
+
+The system SHALL require every note to carry a non-empty title.
+
+#### Scenario: Title required
+
+- **WHEN** a note is saved without a title
+- **THEN** the save is rejected
+
+### Requirement: Note Bodies
+
+The system SHALL accept note bodies of up to 10000 characters.
+
+#### Scenario: Long body
+
+- **WHEN** a note body exceeds 10000 characters
+- **THEN** the save is rejected
diff --git a/skills/tests/multiplayer-simulation/mpsim/__init__.py b/skills/tests/multiplayer-simulation/mpsim/__init__.py
new file mode 100644
index 0000000..2e0ff1c
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/__init__.py
@@ -0,0 +1 @@
+"""mpsim: deterministic, offline multi-player simulation driver (see design D2)."""
diff --git a/skills/tests/multiplayer-simulation/mpsim/__main__.py b/skills/tests/multiplayer-simulation/mpsim/__main__.py
new file mode 100644
index 0000000..7b0283e
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/__main__.py
@@ -0,0 +1,58 @@
+"""``python -m mpsim`` / ``bin/mpsim``: the CLI per ``openspec/contracts/multiplayer-simulation/cli/mpsim.yaml``.
+
+Exit codes: 0 ran to completion, 1 scenario could not be established (report with
+``error`` printed), 2 argparse usage error, 64 semantic usage error (EX_USAGE).
+"""
+
+from __future__ import annotations
+
+import argparse
+import json
+import sys
+from pathlib import Path
+
+from mpsim.errors import UsageError
+from mpsim.runner import DEFAULT_TICK_BUDGET, run
+from mpsim.scenarios import scenario_ids
+
+EX_USAGE = 64
+
+
+def build_parser() -> argparse.ArgumentParser:
+    parser = argparse.ArgumentParser(
+        prog="mpsim", description="Deterministic, offline multi-player simulation driver."
+    )
+    commands = parser.add_subparsers(dest="command", required=True)
+    commands.add_parser("list", help="print the built-in scenario ids as a JSON array")
+    run_cmd = commands.add_parser("run", help="run one scenario and print its report")
+    run_cmd.add_argument("--scenario", required=True, help="built-in scenario id (see `list`)")
+    run_cmd.add_argument("--probe", action="append", default=None,
+                         help="restrict the run to this registered probe (repeatable)")
+    run_cmd.add_argument("--tick-budget", type=int, default=DEFAULT_TICK_BUDGET,
+                         help="maximum logical ticks (default %(default)s)")
+    run_cmd.add_argument("--fixture-dir", type=Path, default=None,
+                         help="replace the scenario's built-in fixture directory")
+    return parser
+
+
+def main(argv: list[str] | None = None) -> int:
+    args = build_parser().parse_args(argv)
+    if args.command == "list":
+        sys.stdout.write(json.dumps(scenario_ids()) + "\n")
+        return 0
+    try:
+        result = run(
+            args.scenario,
+            probe_ids=args.probe,
+            tick_budget=args.tick_budget,
+            fixture_dir=args.fixture_dir,
+        )
+    except UsageError as exc:
+        sys.stderr.write(f"mpsim: usage error: {exc}\n")
+        return EX_USAGE
+    sys.stdout.write(result.text)
+    return result.exit_code
+
+
+if __name__ == "__main__":
+    sys.exit(main())
diff --git a/skills/tests/multiplayer-simulation/mpsim/agents.py b/skills/tests/multiplayer-simulation/mpsim/agents.py
new file mode 100644
index 0000000..51df79a
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/agents.py
@@ -0,0 +1,60 @@
+"""Scripted agents (design D7).
+
+An agent performs one step's file edits and git operations and reports the status
+transitions the fixture declared for that step. It never applies them: it does not
+write ``roadmap.yaml`` and never pushes to ``main`` (operator decision A1). Only the
+status applier (``mpsim.applier``) writes roadmap state.
+"""
+
+from __future__ import annotations
+
+import shutil
+from pathlib import Path
+from typing import Protocol, runtime_checkable
+
+from mpsim.model import PrincipalSpec, StatusTransition, Step
+from mpsim.world import World
+
+
+@runtime_checkable
+class Agent(Protocol):
+    principal: str
+    agent_id: str
+
+    def declared_transitions(self, step: Step, when: str) -> list[StatusTransition]: ...
+
+    def act(self, world: World, step: Step, tick: int) -> list[StatusTransition]: ...
+
+
+class ScriptedAgent:
+    """Replays a principal's fixture script deterministically."""
+
+    def __init__(self, spec: PrincipalSpec, fixture_dir: Path) -> None:
+        self.spec = spec
+        self.fixture_dir = Path(fixture_dir)
+        self.principal = spec.name
+        self.agent_id = f"{spec.name}-agent-1"
+
+    def declared_transitions(self, step: Step, when: str) -> list[StatusTransition]:
+        transition = step.on_start if when == "start" else step.on_finish
+        if transition is None or self.spec.roadmap_item is None:
+            return []
+        return [
+            StatusTransition(
+                self.principal, self.spec.roadmap_item, transition.set_status, when, step.name
+            )
+        ]
+
+    def act(self, world: World, step: Step, tick: int) -> list[StatusTransition]:
+        change = self.spec.change_id
+        worktree = world.worktree_path(self.principal, change)
+        if not worktree.exists():
+            world.add_worktree(self.principal, change, tick)
+        if step.files_from:
+            shutil.copytree(self.fixture_dir / step.files_from, worktree, dirs_exist_ok=True)
+        marker = worktree / "openspec" / "changes" / change / "steps" / f"{step.name}.md"
+        marker.parent.mkdir(parents=True, exist_ok=True)
+        marker.write_text(f"# {step.name}\n\nStep `{step.name}` of {change}.\n")
+        world.commit(self.principal, change, f"feat({change}): {step.name}", tick)
+        world.push(self.principal, change)
+        return self.declared_transitions(step, "finish")
diff --git a/skills/tests/multiplayer-simulation/mpsim/applier.py b/skills/tests/multiplayer-simulation/mpsim/applier.py
new file mode 100644
index 0000000..709d860
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/applier.py
@@ -0,0 +1,51 @@
+"""The status applier: the simulated supervisor step (design D5, operator decision A1).
+
+``roadmap.yaml`` has exactly one authoritative copy, the one on the shared remote's
+``main``. Principals never edit it. This module is part of the ``mpsim`` package but is
+*not* a principal: it operates on its own clone of the shared remote and commits as
+``sim-supervisor``, mirroring the real split where workers report results and only the
+supervisor writes roadmap state.
+
+The applier holds no transition logic. It writes exactly the status a fixture declared,
+for the item of the principal that reported it.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Sequence
+from pathlib import Path
+
+import yaml
+
+from mpsim.errors import ScenarioError
+from mpsim.model import StatusTransition
+from mpsim.world import SUPERVISOR_IDENTITY, World
+
+ROADMAP_FILE = "roadmap.yaml"
+
+
+class StatusApplier:
+    def __init__(self, world: World, root: Path) -> None:
+        self._world = world
+        self._clone = world.clone_for(Path(root) / "supervisor" / "clone", SUPERVISOR_IDENTITY)
+
+    def apply(self, transitions: Sequence[StatusTransition], tick: int) -> None:
+        """Commit each transition to ``main`` in order, then push once."""
+        if not transitions:
+            return
+        self._world.run_git(self._clone, "pull", "-q", "--ff-only", "origin", "main")
+        path = self._clone / ROADMAP_FILE
+        for t in transitions:
+            data = yaml.safe_load(path.read_text())
+            item = next((i for i in data.get("items", []) if i.get("item_id") == t.item_id), None)
+            if item is None:
+                raise ScenarioError(f"roadmap has no item {t.item_id!r} reported by {t.principal}")
+            item["status"] = t.status
+            path.write_text(yaml.safe_dump(data, sort_keys=False))
+            self._world.commit_as(
+                self._clone,
+                f"chore(roadmap): {t.item_id} -> {t.status} ({t.principal} {t.step} {t.when})",
+                SUPERVISOR_IDENTITY,
+                tick,
+            )
+        self._world.run_git(self._clone, "push", "-q", "origin", "HEAD:refs/heads/main")
diff --git a/skills/tests/multiplayer-simulation/mpsim/clock.py b/skills/tests/multiplayer-simulation/mpsim/clock.py
new file mode 100644
index 0000000..38549f7
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/clock.py
@@ -0,0 +1,18 @@
+"""Logical tick clock. It advances only when told to (design D5)."""
+
+from __future__ import annotations
+
+
+class Clock:
+    def __init__(self, start: int = 0) -> None:
+        self._tick = start
+
+    @property
+    def tick(self) -> int:
+        return self._tick
+
+    def advance(self, n: int = 1) -> int:
+        if n < 0:
+            raise ValueError("a clock cannot run backwards")
+        self._tick += n
+        return self._tick
diff --git a/skills/tests/multiplayer-simulation/mpsim/errors.py b/skills/tests/multiplayer-simulation/mpsim/errors.py
new file mode 100644
index 0000000..cfde0c5
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/errors.py
@@ -0,0 +1,9 @@
+"""Errors raised by the driver."""
+
+
+class UsageError(Exception):
+    """A semantic usage error. The CLI maps it to exit code 64 (EX_USAGE)."""
+
+
+class ScenarioError(Exception):
+    """The scenario could not be established. The CLI maps it to exit code 1."""
diff --git a/skills/tests/multiplayer-simulation/mpsim/fixture.py b/skills/tests/multiplayer-simulation/mpsim/fixture.py
new file mode 100644
index 0000000..31c8b1a
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/fixture.py
@@ -0,0 +1,88 @@
+"""Fixture loader: a fixture directory is data only (design D5, D6).
+
+Layout: ``scenario.yaml`` (principals, steps, durations, declared status transitions),
+``seed/`` (files committed to the seed commit on ``main``) and any directories that steps
+name in ``files_from``.
+"""
+
+from __future__ import annotations
+
+import re
+from pathlib import Path
+from typing import Any
+
+import yaml
+
+from mpsim.errors import UsageError
+from mpsim.model import STEP_NAMES, Fixture, PrincipalSpec, Step, Transition
+from mpsim.world import MIN_PRINCIPALS
+
+_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
+
+
+def _transition(raw: Any, where: str) -> Transition | None:
+    if raw is None:
+        return None
+    if not isinstance(raw, dict) or not isinstance(raw.get("set_status"), str):
+        raise UsageError(f"{where}: expected a mapping with a string 'set_status'")
+    return Transition(raw["set_status"])
+
+
+def _step(raw: Any, fixture_dir: Path, where: str) -> Step:
+    if not isinstance(raw, dict):
+        raise UsageError(f"{where}: step must be a mapping")
+    name = raw.get("name")
+    if name not in STEP_NAMES:
+        raise UsageError(f"{where}: step name must be one of {', '.join(STEP_NAMES)}")
+    duration = raw.get("duration")
+    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 1:
+        raise UsageError(f"{where}.{name}: duration must be an integer >= 1")
+    files_from = raw.get("files_from")
+    if files_from is not None and not (fixture_dir / files_from).is_dir():
+        raise UsageError(f"{where}.{name}: files_from {files_from!r} is not a fixture directory")
+    return Step(
+        name=name,
+        duration=duration,
+        files_from=files_from,
+        on_start=_transition(raw.get("on_start"), f"{where}.{name}.on_start"),
+        on_finish=_transition(raw.get("on_finish"), f"{where}.{name}.on_finish"),
+    )
+
+
+def load_fixture(fixture_dir: Path) -> Fixture:
+    fixture_dir = Path(fixture_dir)
+    descriptor = fixture_dir / "scenario.yaml"
+    if not descriptor.is_file():
+        raise UsageError("fixture directory has no scenario.yaml")
+    data = yaml.safe_load(descriptor.read_text()) or {}
+    raw_principals = data.get("principals")
+    if not isinstance(raw_principals, list):
+        raise UsageError("scenario.yaml: 'principals' must be a list")
+    if len(raw_principals) < MIN_PRINCIPALS:
+        raise UsageError(
+            f"fixture declares {len(raw_principals)} principal(s); "
+            f"a scenario needs at least {MIN_PRINCIPALS} principals"
+        )
+    principals: list[PrincipalSpec] = []
+    for index, raw in enumerate(raw_principals):
+        where = f"principals[{index}]"
+        if not isinstance(raw, dict):
+            raise UsageError(f"{where}: must be a mapping")
+        name, change_id = raw.get("name"), raw.get("change_id")
+        if not isinstance(name, str) or not _NAME_RE.match(name):
+            raise UsageError(f"{where}: invalid principal name")
+        if not isinstance(change_id, str) or not re.match(r"^sim-[a-z0-9-]+$", change_id):
+            raise UsageError(f"{where}: change_id must be a synthetic 'sim-' id")
+        steps = tuple(_step(s, fixture_dir, f"{name}") for s in raw.get("steps") or [])
+        principals.append(
+            PrincipalSpec(name=name, change_id=change_id,
+                          roadmap_item=raw.get("roadmap_item"), steps=steps)
+        )
+    if len({p.name for p in principals}) != len(principals):
+        raise UsageError("principal names must be distinct")
+    seed_dir = fixture_dir / "seed"
+    seed_files = {
+        str(p.relative_to(seed_dir)): p.read_text()
+        for p in sorted(seed_dir.rglob("*")) if p.is_file()
+    } if seed_dir.is_dir() else {}
+    return Fixture(fixture_dir, tuple(principals), seed_files)
diff --git a/skills/tests/multiplayer-simulation/mpsim/model.py b/skills/tests/multiplayer-simulation/mpsim/model.py
new file mode 100644
index 0000000..3953585
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/model.py
@@ -0,0 +1,70 @@
+"""Plain data shared by the fixture loader, agents and schedulers."""
+
+from __future__ import annotations
+
+from collections.abc import Callable
+from dataclasses import dataclass, field
+from pathlib import Path
+
+STEP_NAMES = ("plan", "contract", "implement")
+
+
+@dataclass(frozen=True)
+class Transition:
+    """A status change declared by fixture data for a principal's own roadmap item."""
+
+    set_status: str
+
+
+@dataclass(frozen=True)
+class Step:
+    name: str
+    duration: int
+    files_from: str | None = None  # fixture-relative directory copied into the worktree root
+    on_start: Transition | None = None
+    on_finish: Transition | None = None
+
+
+@dataclass(frozen=True)
+class StatusTransition:
+    """A declared transition bound to the principal that reported it."""
+
+    principal: str
+    item_id: str
+    status: str
+    when: str  # "start" | "finish"
+    step: str
+
+
+@dataclass(frozen=True)
+class PrincipalSpec:
+    name: str
+    change_id: str
+    roadmap_item: str | None = None
+    steps: tuple[Step, ...] = field(default_factory=tuple)
+
+    def step(self, name: str) -> Step | None:
+        return next((s for s in self.steps if s.name == name), None)
+
+
+@dataclass(frozen=True)
+class Fixture:
+    dir: Path
+    principals: tuple[PrincipalSpec, ...]
+    seed_files: dict[str, str]
+
+
+@dataclass(frozen=True)
+class RunContext:
+    scenario_id: str
+    fixture: Fixture
+    probes: list  # selected CollisionProbe instances (empty when none is registered)
+    tick_budget: int
+    work_root: Path
+
+
+@dataclass(frozen=True)
+class Scenario:
+    id: str
+    fixture_name: str  # directory under fixtures/ used when --fixture-dir is not given
+    run: Callable[[RunContext], dict]
diff --git a/skills/tests/multiplayer-simulation/mpsim/oracle.py b/skills/tests/multiplayer-simulation/mpsim/oracle.py
new file mode 100644
index 0000000..0f6d127
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/oracle.py
@@ -0,0 +1,28 @@
+"""Ground-truth collision oracle (design D4).
+
+A plain string comparison over files the fixture wrote: two spec deltas collide when
+they name the same ``### Requirement:`` heading of the same capability. It reads no git
+history and does no live scanning. It is not a detector and is never registered as a
+probe; it exists so a broken fixture cannot make "not detected" trivially true.
+"""
+
+from __future__ import annotations
+
+import re
+from pathlib import Path
+
+_HEADING = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$", re.MULTILINE)
+
+
+def delta_requirements(change_dir: Path) -> set[tuple[str, str]]:
+    """(capability, requirement heading) pairs named by ``<change_dir>/specs/*/spec.md``."""
+    found: set[tuple[str, str]] = set()
+    for spec in sorted(Path(change_dir).glob("specs/*/spec.md")):
+        capability = spec.parent.name
+        for heading in _HEADING.findall(spec.read_text()):
+            found.add((capability, heading))
+    return found
+
+
+def collision_present(first_change_dir: Path, second_change_dir: Path) -> bool:
+    return bool(delta_requirements(first_change_dir) & delta_requirements(second_change_dir))
diff --git a/skills/tests/multiplayer-simulation/mpsim/paths.py b/skills/tests/multiplayer-simulation/mpsim/paths.py
new file mode 100644
index 0000000..db00896
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/paths.py
@@ -0,0 +1,11 @@
+"""Locations the driver needs. The harness root is stable; the repo root sits above it."""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+HARNESS_ROOT = Path(__file__).resolve().parent.parent
+FIXTURES_ROOT = HARNESS_ROOT / "fixtures"
+# skills/tests/multiplayer-simulation -> repo root
+REPO_ROOT = HARNESS_ROOT.parents[2]
+RUNTIME_SCRIPTS = REPO_ROOT / "skills" / "roadmap-runtime" / "scripts"
diff --git a/skills/tests/multiplayer-simulation/mpsim/probes/__init__.py b/skills/tests/multiplayer-simulation/mpsim/probes/__init__.py
new file mode 100644
index 0000000..9e8691c
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/probes/__init__.py
@@ -0,0 +1,122 @@
+"""Collision probe seam (design D4).
+
+Plan-time collision detectors attach only through :class:`CollisionProbe`. The registry
+is empty by default: no plan-time requirement-collision detector exists yet, so the
+baseline honestly records "not detected".
+
+Adding a probe means adding one import line below (``ri-06`` does this); scenario
+definitions stay untouched. A probe that raises or runs past its timeout is recorded
+with ``status: error`` and the scenario still completes, mirroring the roadmap rule that
+advisory signals fail open.
+"""
+
+from __future__ import annotations
+
+import threading
+from collections.abc import Sequence
+from dataclasses import dataclass, field
+from typing import Protocol, runtime_checkable
+
+from mpsim.errors import UsageError
+from mpsim.world import PrincipalView
+
+# Default per-probe timeout in seconds. Read at call time so tests can lower it.
+PER_PROBE_TIMEOUT = 10.0
+
+
+@dataclass(frozen=True)
+class Collision:
+    level: str  # intent | requirement | contract | file
+    other_change: str
+    requirement: str | None
+
+
+@dataclass(frozen=True)
+class ProbeResult:
+    probe_id: str
+    status: str  # ok | error
+    collisions: list[Collision] = field(default_factory=list)
+    error: str | None = None
+
+
+@runtime_checkable
+class CollisionProbe(Protocol):
+    probe_id: str
+
+    def detect(self, view: PrincipalView, change_id: str) -> ProbeResult: ...
+
+
+REGISTRY: dict[str, CollisionProbe] = {}
+
+
+def register(probe: CollisionProbe) -> None:
+    if probe.probe_id in REGISTRY:
+        raise ValueError(f"probe {probe.probe_id!r} is already registered")
+    REGISTRY[probe.probe_id] = probe
+
+
+def select(probe_ids: Sequence[str] | None) -> list[CollisionProbe]:
+    """Registered probes in registration order, or the named subset (unknown id -> UsageError)."""
+    if not probe_ids:
+        return list(REGISTRY.values())
+    unknown = [pid for pid in probe_ids if pid not in REGISTRY]
+    if unknown:
+        raise UsageError(f"unknown probe id: {', '.join(unknown)}")
+    wanted = set(probe_ids)
+    return [p for pid, p in REGISTRY.items() if pid in wanted]
+
+
+def run_probe(probe: CollisionProbe, view: PrincipalView, change_id: str) -> ProbeResult:
+    """Run one probe in a daemon thread; abandon it at the timeout instead of joining."""
+    timeout = PER_PROBE_TIMEOUT
+    box: list[ProbeResult | BaseException] = []
+
+    def target() -> None:
+        try:
+            box.append(probe.detect(view, change_id))
+        except BaseException as exc:  # noqa: BLE001 - any probe failure is recorded, never raised
+            box.append(exc)
+
+    thread = threading.Thread(target=target, name=f"probe-{probe.probe_id}", daemon=True)
+    thread.start()
+    thread.join(timeout)
+    if thread.is_alive():
+        return ProbeResult(probe.probe_id, "error", [], f"probe timeout after {timeout:g}s")
+    outcome = box[0]
+    if isinstance(outcome, BaseException):
+        return ProbeResult(probe.probe_id, "error", [], f"{type(outcome).__name__}: {outcome}")
+    if not isinstance(outcome, ProbeResult) or outcome.status not in ("ok", "error"):
+        return ProbeResult(probe.probe_id, "error", [], "probe returned an invalid result")
+    return ProbeResult(probe.probe_id, outcome.status, list(outcome.collisions), outcome.error)
+
+
+def run_probes(
+    probes: Sequence[CollisionProbe], view: PrincipalView, change_id: str
+) -> list[ProbeResult]:
+    return [run_probe(p, view, change_id) for p in probes]
+
+
+def detected(results: Sequence[ProbeResult], other_change: str) -> bool:
+    """True when an ``ok`` probe reported a requirement-level collision with ``other_change``."""
+    return any(
+        r.status == "ok"
+        and any(c.level == "requirement" and c.other_change == other_change for c in r.collisions)
+        for r in results
+    )
+
+
+def as_report_entry(result: ProbeResult) -> dict:
+    return {
+        "probe_id": result.probe_id,
+        "status": result.status,
+        "collisions": [
+            {"level": c.level, "other_change": c.other_change, "requirement": c.requirement}
+            for c in result.collisions
+        ],
+        "error": result.error,
+    }
+
+
+# Probe registrations go below this line, one import per probe. ri-06 adds its import here:
+#
+#     from mpsim.probes import requirement_collision  # noqa: F401  (registers itself)
diff --git a/skills/tests/multiplayer-simulation/mpsim/report.py b/skills/tests/multiplayer-simulation/mpsim/report.py
new file mode 100644
index 0000000..18ded4f
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/report.py
@@ -0,0 +1,61 @@
+"""Report builder (design D8).
+
+Every property of ``sim-report.schema.json`` is always present; the ones that do not
+apply to a scenario are ``null``. Rendering refuses any value that would make two runs
+differ by host: the world's temporary root or a 40-character hexadecimal string.
+"""
+
+from __future__ import annotations
+
+import json
+import re
+from collections.abc import Sequence
+from typing import Any
+
+from mpsim.errors import ScenarioError
+
+SCHEMA_VERSION = "1"
+_HEX40 = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{40}(?![0-9a-fA-F])")
+
+
+class ReportError(ScenarioError):
+    """A report value would leak host-specific data."""
+
+
+def new_report(
+    scenario_id: str,
+    *,
+    principals: list[dict[str, str]] | None = None,
+    collision_present: bool | None = None,
+    collision_detected: bool | None = None,
+    probes: list[dict[str, Any]] | None = None,
+    blocked_ticks: dict[str, int] | None = None,
+    unblocked: dict[str, bool] | None = None,
+    final_tick: int | None = None,
+    timeline: list[dict[str, Any]] | None = None,
+    error: str | None = None,
+) -> dict[str, Any]:
+    return {
+        "schema_version": SCHEMA_VERSION,
+        "scenario_id": scenario_id,
+        "principals": list(principals or []),
+        "collision_present": collision_present,
+        "collision_detected": collision_detected,
+        "probes": probes,
+        "blocked_ticks": blocked_ticks,
+        "unblocked": unblocked,
+        "final_tick": final_tick,
+        "timeline": timeline,
+        "error": error,
+    }
+
+
+def render(report: dict[str, Any], *, forbidden_paths: Sequence[str] = ()) -> str:
+    """Serialize with sorted keys and no trailing whitespace, after the leak checks."""
+    text = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
+    for path in forbidden_paths:
+        if path and path in text:
+            raise ReportError("report contains the world's temporary root")
+    if _HEX40.search(text):
+        raise ReportError("report contains a 40-character hex string (commit id)")
+    return text
diff --git a/skills/tests/multiplayer-simulation/mpsim/runner.py b/skills/tests/multiplayer-simulation/mpsim/runner.py
new file mode 100644
index 0000000..a14fc42
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/runner.py
@@ -0,0 +1,83 @@
+"""Run one scenario and produce its report (shared by the CLI and the tests)."""
+
+from __future__ import annotations
+
+import os
+import shutil
+import tempfile
+from collections.abc import Sequence
+from dataclasses import dataclass
+from pathlib import Path
+from typing import Any
+
+from mpsim import probes as probe_registry
+from mpsim.errors import ScenarioError, UsageError
+from mpsim.fixture import load_fixture
+from mpsim.model import RunContext
+from mpsim.paths import FIXTURES_ROOT
+from mpsim.report import new_report, render
+from mpsim.scenarios import discover
+
+DEFAULT_TICK_BUDGET = 50
+
+
+@dataclass(frozen=True)
+class RunResult:
+    exit_code: int
+    report: dict[str, Any]
+    text: str
+
+
+def run(
+    scenario_id: str,
+    *,
+    probe_ids: Sequence[str] | None = None,
+    tick_budget: int = DEFAULT_TICK_BUDGET,
+    fixture_dir: Path | None = None,
+    work_root: Path | None = None,
+) -> RunResult:
+    """Run one scenario. ``work_root`` (tests only) keeps the simulated world for inspection."""
+    scenarios = discover()
+    if scenario_id not in scenarios:
+        raise UsageError(f"unknown scenario {scenario_id!r}; known: {', '.join(scenarios)}")
+    scenario = scenarios[scenario_id]
+    if tick_budget < 1:
+        raise UsageError("--tick-budget must be at least 1")
+    if fixture_dir is not None and not Path(fixture_dir).is_dir():
+        raise UsageError("--fixture-dir does not exist or is not a directory")
+    fixture = load_fixture(Path(fixture_dir) if fixture_dir else FIXTURES_ROOT / scenario.fixture_name)
+    selected = probe_registry.select(probe_ids)
+
+    keep = work_root is not None
+    if work_root is None:
+        work_root = Path(tempfile.mkdtemp(prefix="mpsim-", dir=os.environ.get("TMPDIR") or None))
+    else:
+        work_root.mkdir(parents=True, exist_ok=True)
+    scrub = _scrub_values(work_root, fixture.dir)
+    try:
+        ctx = RunContext(scenario_id, fixture, selected, tick_budget, work_root)
+        try:
+            report = scenario.run(ctx)
+            exit_code = 0
+        except ScenarioError as exc:
+            report = new_report(scenario_id, error=_scrub(str(exc), scrub))
+            exit_code = 1
+        text = render(report, forbidden_paths=[v for v, _ in scrub])
+    finally:
+        if not keep:
+            shutil.rmtree(work_root, ignore_errors=True)
+    return RunResult(exit_code, report, text)
+
+
+def _scrub_values(work_root: Path, fixture_dir: Path) -> list[tuple[str, str]]:
+    values = []
+    for path, label in ((work_root, "<world>"), (fixture_dir, "<fixture>")):
+        for variant in {str(path), str(path.resolve())}:
+            values.append((variant, label))
+    return sorted(values, key=lambda v: -len(v[0]))
+
+
+def _scrub(message: str, scrub: list[tuple[str, str]]) -> str:
+    for value, label in scrub:
+        message = message.replace(value, label)
+    return message
diff --git a/skills/tests/multiplayer-simulation/mpsim/scenarios/__init__.py b/skills/tests/multiplayer-simulation/mpsim/scenarios/__init__.py
new file mode 100644
index 0000000..79be80d
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/scenarios/__init__.py
@@ -0,0 +1,28 @@
+"""Scenario registry.
+
+Every module in this package that defines a module-level ``SCENARIOS`` mapping
+(scenario id -> scenario object) is discovered with ``pkgutil``, so adding a
+scenario family never edits a shared list (design D2).
+"""
+
+from __future__ import annotations
+
+import importlib
+import pkgutil
+from typing import Any
+
+
+def discover() -> dict[str, Any]:
+    """Import every scenario module and merge their ``SCENARIOS`` mappings."""
+    found: dict[str, Any] = {}
+    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
+        module = importlib.import_module(f"{__name__}.{info.name}")
+        for scenario_id, scenario in getattr(module, "SCENARIOS", {}).items():
+            if scenario_id in found:
+                raise RuntimeError(f"duplicate scenario id {scenario_id!r} in {info.name}")
+            found[scenario_id] = scenario
+    return dict(sorted(found.items()))
+
+
+def scenario_ids() -> list[str]:
+    return list(discover())
diff --git a/skills/tests/multiplayer-simulation/mpsim/scenarios/blocked.py b/skills/tests/multiplayer-simulation/mpsim/scenarios/blocked.py
new file mode 100644
index 0000000..8ae6a1c
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/scenarios/blocked.py
@@ -0,0 +1,189 @@
+"""The memory-store blocked-dependency scenarios (design D5).
+
+A logical tick scheduler. It holds *no* readiness logic: on every tick each waiting
+principal fetches the shared remote's ``main``, loads ``roadmap.yaml`` from
+``origin/main`` through roadmap-runtime's ``load_roadmap`` (validated against the real
+repository's schema) and asks ``Roadmap.ready_items()`` whether its item is admitted.
+That call below is the one ``ri-11`` changes the meaning of.
+
+Intra-tick order, fixed because the pinned baseline depends on it:
+
+1. every step finishing at tick t pushes its work, in fixture declaration order;
+2. the applier commits the ``on_finish`` transitions reported at t, then pushes once;
+3. each waiting principal fetches ``main`` and evaluates ``ready_items()``;
+4. the applier commits the ``on_start`` transitions of the principals admitted at t.
+
+Status transitions come from fixture data only. Nothing here names a status.
+"""
+
+from __future__ import annotations
+
+import sys
+from dataclasses import dataclass, field
+from pathlib import Path
+
+from mpsim.agents import ScriptedAgent
+from mpsim.applier import ROADMAP_FILE, StatusApplier
+from mpsim.errors import ScenarioError
+from mpsim.model import PrincipalSpec, RunContext, Scenario, StatusTransition, Step
+from mpsim.paths import REPO_ROOT, RUNTIME_SCRIPTS
+from mpsim.report import new_report
+from mpsim.world import World
+
+
+def _load_roadmap(path: Path):
+    if str(RUNTIME_SCRIPTS) not in sys.path:
+        sys.path.insert(0, str(RUNTIME_SCRIPTS))
+    from models import load_roadmap  # roadmap-runtime, the real admission rule's home
+
+    return load_roadmap(path, REPO_ROOT)
+
+
+@dataclass
+class _State:
+    spec: PrincipalSpec
+    agent: ScriptedAgent
+    index: int = 0
+    phase: str = "running"  # running | waiting | done
+    finish_tick: int = 0
+    earliest_start: int | None = None
+    ready_tick: int | None = None
+    pending_finish: list[StatusTransition] = field(default_factory=list)
+
+    @property
+    def step(self) -> Step:
+        return self.spec.steps[self.index]
+
+
+def _run(ctx: RunContext) -> dict:
+    fixture = ctx.fixture
+    world = World.create(
+        ctx.work_root / "world", [p.name for p in fixture.principals], fixture.seed_files
+    )
+    applier = StatusApplier(world, ctx.work_root)
+    scratch = ctx.work_root / "scratch"
+    scratch.mkdir(parents=True, exist_ok=True)
+    timeline: list[dict] = []
+    states: list[_State] = []
+    for spec in fixture.principals:
+        if not spec.steps:
+            raise ScenarioError(f"principal {spec.name!r} declares no steps")
+        if spec.roadmap_item is None:
+            raise ScenarioError(f"principal {spec.name!r} declares no roadmap_item")
+        states.append(_State(spec, ScriptedAgent(spec, fixture.dir)))
+
+    def log(tick: int, state: _State, step: str, event: str) -> None:
+        timeline.append({"tick": tick, "principal": state.spec.name, "step": step, "event": event})
+
+    def begin(state: _State, tick: int) -> None:
+        """Enter the current step at ``tick``: run it, or wait for admission."""
+        step = state.step
+        if step.name == "implement":
+            state.phase = "waiting"
+            state.earliest_start = tick
+        else:
+            state.phase = "running"
+            state.finish_tick = tick + step.duration
+            log(tick, state, step.name, "started")
+
+    for state in states:
+        begin(state, 0)
+
+    tick = 0
+    final_tick = 0
+    while True:
+        final_tick = tick
+        # 1. steps finishing at this tick push their work, in declaration order
+        finished: list[StatusTransition] = []
+        for state in states:
+            if state.phase == "running" and state.finish_tick == tick:
+                step = state.step
+                transitions = state.agent.act(world, step, tick)
+                log(tick, state, step.name, "finished")
+                log(tick, state, step.name, "pushed")
+                finished.extend(transitions)
+                state.index += 1
+                if state.index >= len(state.spec.steps):
+                    state.phase = "done"
+                else:
+                    begin(state, tick)
+        # 2. the applier commits the reported on_finish transitions to main
+        applier.apply(finished, tick)
+        for t in finished:
+            timeline.append({"tick": tick, "principal": t.principal, "step": t.step,
+                             "event": "status_applied"})
+        # 3. each waiting principal fetches main and asks the real admission rule
+        admitted: list[_State] = []
+        for state in states:
+            if state.phase != "waiting":
+                continue
+            world.fetch(state.spec.name)
+            roadmap_path = scratch / f"{state.spec.name}-roadmap.yaml"
+            roadmap_path.write_text(
+                world.read_ref(state.spec.name, "origin/main", ROADMAP_FILE)
+            )
+            ready = {item.item_id for item in _load_roadmap(roadmap_path).ready_items()}
+            if state.spec.roadmap_item in ready:
+                admitted.append(state)
+            elif state.earliest_start == tick:
+                log(tick, state, "implement", "blocked")
+        # 4. the applier commits on_start for the principals admitted at this tick
+        starts: list[StatusTransition] = []
+        for state in admitted:
+            state.ready_tick = tick
+            log(tick, state, "implement", "admitted")
+            starts.extend(state.agent.declared_transitions(state.step, "start"))
+        applier.apply(starts, tick)
+        for state in admitted:
+            state.phase = "running"
+            state.finish_tick = tick + state.step.duration
+            log(tick, state, "implement", "started")
+        for t in starts:
+            timeline.append({"tick": tick, "principal": t.principal, "step": t.step,
+                             "event": "status_applied"})
+
+        if all(s.phase == "done" for s in states):
+            break
+        if not any(s.phase == "running" for s in states):
+            # Nothing is running and nothing was admitted: main can never change again.
+            final_tick = ctx.tick_budget
+            break
+        if tick >= ctx.tick_budget:
+            break
+        tick += 1
+
+    blocked: dict[str, int] = {}
+    unblocked: dict[str, bool] = {}
+    for state in states:
+        name = state.spec.name
+        if state.ready_tick is not None and state.earliest_start is not None:
+            blocked[name] = state.ready_tick - state.earliest_start
+            unblocked[name] = True
+        elif state.earliest_start is not None:
+            blocked[name] = ctx.tick_budget - state.earliest_start
+            unblocked[name] = False
+        else:  # never reached implement within the budget, so it never began waiting
+            blocked[name] = 0
+            unblocked[name] = False
+
+    return new_report(
+        ctx.scenario_id,
+        principals=[
+            {"name": s.spec.name, "agent_id": s.agent.agent_id, "change_id": s.spec.change_id}
+            for s in states
+        ],
+        blocked_ticks=dict(sorted(blocked.items())),
+        unblocked=dict(sorted(unblocked.items())),
+        final_tick=final_tick,
+        timeline=timeline,
+    )
+
+
+SCENARIOS = {
+    "memory-store-blocked-dependency": Scenario(
+        "memory-store-blocked-dependency", "memory-store-blocked-dependency", _run
+    ),
+    "independent-principals-control": Scenario(
+        "independent-principals-control", "independent-principals-control", _run
+    ),
+}
diff --git a/skills/tests/multiplayer-simulation/mpsim/scenarios/collision.py b/skills/tests/multiplayer-simulation/mpsim/scenarios/collision.py
new file mode 100644
index 0000000..94d7dc4
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/scenarios/collision.py
@@ -0,0 +1,101 @@
+"""The plan-time collision scenarios (design D4).
+
+Alice plans, pushes and finishes. Bob fetches, then plans. At Bob's plan step the
+scenario asks the ground-truth oracle (``collision_present``) and every selected probe
+(``collision_detected``, ``probes``). The fixture decides whether a collision exists;
+the scenario only checks that the fixture still means what the scenario name says.
+"""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+from mpsim import probes as probe_registry
+from mpsim.agents import ScriptedAgent
+from mpsim.clock import Clock
+from mpsim.errors import ScenarioError
+from mpsim.model import PrincipalSpec, RunContext, Scenario
+from mpsim.oracle import collision_present
+from mpsim.report import new_report
+from mpsim.world import World
+
+
+def _change_dir(ctx: RunContext, spec: PrincipalSpec) -> Path:
+    step = spec.step("plan")
+    base = ctx.fixture.dir / step.files_from if step and step.files_from else ctx.fixture.dir / "_none"
+    return base / "openspec" / "changes" / spec.change_id
+
+
+def _run(ctx: RunContext, *, requires_collision: bool) -> dict:
+    fixture = ctx.fixture
+    world = World.create(
+        ctx.work_root / "world", [p.name for p in fixture.principals], fixture.seed_files
+    )
+    clock = Clock()
+    timeline: list[dict] = []
+
+    def log(principal: str, event: str) -> None:
+        timeline.append({"tick": clock.tick, "principal": principal, "step": "plan", "event": event})
+
+    probe_entries: list[dict] = []
+    present = detected = False
+    for index, spec in enumerate(fixture.principals):
+        step = spec.step("plan")
+        if step is None:
+            raise ScenarioError(f"principal {spec.name!r} declares no plan step")
+        agent = ScriptedAgent(spec, fixture.dir)
+        if index > 0:
+            world.fetch(spec.name)
+        log(spec.name, "started")
+        clock.advance(step.duration)
+        agent.act(world, step, clock.tick)
+        log(spec.name, "finished")
+        log(spec.name, "pushed")
+        if index != 1:
+            continue
+        first = fixture.principals[0]
+        present = collision_present(_change_dir(ctx, first), _change_dir(ctx, spec))
+        results = probe_registry.run_probes(
+            ctx.probes, world.view(spec.name, spec.change_id), spec.change_id
+        )
+        detected = probe_registry.detected(results, first.change_id)
+        probe_entries = [probe_registry.as_report_entry(r) for r in results]
+        log(spec.name, "probed")
+
+    first, second = fixture.principals[0], fixture.principals[1]
+    if requires_collision and not present:
+        raise ScenarioError(
+            f"scenario {ctx.scenario_id!r} requires a collision between {first.change_id} and "
+            f"{second.change_id}, but the required collision is absent from the fixture"
+        )
+    if not requires_collision and present:
+        raise ScenarioError(
+            f"scenario {ctx.scenario_id!r} is a control but an unexpected collision is present "
+            f"between {first.change_id} and {second.change_id}"
+        )
+    return new_report(
+        ctx.scenario_id,
+        principals=[
+            {"name": p.name, "agent_id": f"{p.name}-agent-1", "change_id": p.change_id}
+            for p in fixture.principals
+        ],
+        collision_present=present,
+        collision_detected=detected,
+        probes=probe_entries,
+        final_tick=clock.tick,
+        timeline=timeline,
+    )
+
+
+SCENARIOS = {
+    "same-requirement-collision": Scenario(
+        "same-requirement-collision",
+        "same-requirement-collision",
+        lambda ctx: _run(ctx, requires_collision=True),
+    ),
+    "different-requirement-control": Scenario(
+        "different-requirement-control",
+        "different-requirement-control",
+        lambda ctx: _run(ctx, requires_collision=False),
+    ),
+}
diff --git a/skills/tests/multiplayer-simulation/mpsim/world.py b/skills/tests/multiplayer-simulation/mpsim/world.py
new file mode 100644
index 0000000..bb9b19e
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/mpsim/world.py
@@ -0,0 +1,216 @@
+"""The simulated world: a shared bare remote plus N principals (design D6).
+
+The world owns a temporary root holding a ``file://`` bare remote, one clone per
+principal and one ``git worktree`` per (principal, change). Principals see each
+other's work only through ``git fetch`` from the remote. Every git call runs with
+no global config and with author/committer dates derived from the logical tick,
+so identical inputs give identical commit ids in any directory.
+"""
+
+from __future__ import annotations
+
+import os
+import re
+import subprocess
+from collections.abc import Mapping, Sequence
+from dataclasses import dataclass
+from pathlib import Path
+
+from mpsim.errors import ScenarioError, UsageError
+
+MIN_PRINCIPALS = 2
+SEED_IDENTITY = ("sim-seed", "sim-seed@sim.invalid")
+SUPERVISOR_IDENTITY = ("sim-supervisor", "sim-supervisor@sim.invalid")
+# 2026-01-01T00:00:00Z. A tick is one logical minute.
+_EPOCH = 1767225600
+_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
+
+
+def date_for_tick(tick: int) -> str:
+    return f"@{_EPOCH + tick * 60} +0000"
+
+
+@dataclass(frozen=True)
+class Principal:
+    name: str
+    email: str
+    agent_id: str
+    clone: Path
+
+
+@dataclass(frozen=True)
+class PrincipalView:
+    """Read-only view handed to probes: git state can be read, never mutated."""
+
+    principal: str
+    agent_id: str
+    change_id: str
+    worktree: Path
+    remote_url: str
+
+    def read_text(self, relative: str) -> str:
+        return (self.worktree / relative).read_text()
+
+    def exists(self, relative: str) -> bool:
+        return (self.worktree / relative).exists()
+
+    def list_files(self, relative: str = ".") -> list[str]:
+        base = self.worktree / relative
+        return sorted(
+            str(p.relative_to(self.worktree)) for p in base.rglob("*") if p.is_file()
+            and ".git" not in p.relative_to(self.worktree).parts[:1]
+        )
+
+
+class World:
+    def __init__(self, root: Path, remote: Path, principals: Mapping[str, Principal]):
+        self.root = root
+        self._remote = remote
+        self._principals = dict(principals)
+
+    # -- construction ------------------------------------------------------
+
+    @classmethod
+    def create(
+        cls,
+        root: Path,
+        names: Sequence[str],
+        seed_files: Mapping[str, str],
+    ) -> World:
+        names = list(names)
+        if len(names) < MIN_PRINCIPALS:
+            raise UsageError(
+                f"a world needs at least {MIN_PRINCIPALS} principals, got {len(names)}"
+            )
+        if len(set(names)) != len(names):
+            raise UsageError("principal names must be distinct")
+        for name in names:
+            if not _NAME_RE.match(name):
+                raise UsageError(f"invalid principal name {name!r}")
+        root = Path(root)
+        root.mkdir(parents=True, exist_ok=True)
+        remote = root / "remote.git"
+        world = cls(root, remote, {})
+        world._run(root, "init", "--bare", "-q", "-b", "main", str(remote))
+
+        seed = root / "seed-work"
+        world._run(root, "init", "-q", "-b", "main", str(seed))
+        for rel, content in seed_files.items():
+            target = seed / rel
+            target.parent.mkdir(parents=True, exist_ok=True)
+            target.write_text(content)
+        world._commit(seed, "seed", SEED_IDENTITY, tick=0)
+        world._run(seed, "push", "-q", world.remote_url, "main:refs/heads/main")
+
+        for name in names:
+            base = root / "principals" / name
+            base.mkdir(parents=True)
+            clone = base / "clone"
+            world._run(root, "clone", "-q", world.remote_url, str(clone))
+            email = f"{name}@sim.invalid"
+            world._run(clone, "config", "user.name", name)
+            world._run(clone, "config", "user.email", email)
+            world._principals[name] = Principal(name, email, f"{name}-agent-1", clone)
+        return world
+
+    @property
+    def remote_url(self) -> str:
+        return f"file://{self._remote}"
+
+    @property
+    def names(self) -> list[str]:
+        return list(self._principals)
+
+    def principal(self, name: str) -> Principal:
+        try:
+            return self._principals[name]
+        except KeyError:
+            raise UsageError(f"unknown principal {name!r}") from None
+
+    def worktree_path(self, name: str, change: str) -> Path:
+        return self.principal(name).clone.parent / f"wt-{change}"
+
+    def branch(self, name: str, change: str) -> str:
+        return f"sim/{name}/{change}"
+
+    def view(self, name: str, change: str) -> PrincipalView:
+        p = self.principal(name)
+        return PrincipalView(name, p.agent_id, change, self.worktree_path(name, change),
+                             self.remote_url)
+
+    # -- git operations ----------------------------------------------------
+
+    def add_worktree(self, name: str, change: str, tick: int) -> Path:
+        """Create the principal's worktree and branch from the latest fetched main."""
+        clone = self.principal(name).clone
+        self.fetch(name)
+        path = self.worktree_path(name, change)
+        self._run(clone, "worktree", "add", "-q", "-b", self.branch(name, change),
+                  str(path), "origin/main")
+        return path
+
+    def commit(self, name: str, change: str, message: str, tick: int) -> None:
+        p = self.principal(name)
+        self._commit(self.worktree_path(name, change), message, (p.name, p.email), tick)
+
+    def push(self, name: str, change: str) -> None:
+        branch = self.branch(name, change)
+        self._run(self.worktree_path(name, change), "push", "-q", "origin",
+                  f"{branch}:refs/heads/{branch}")
+
+    def fetch(self, name: str) -> None:
+        self._run(self.principal(name).clone, "fetch", "-q", "--prune", "origin")
+
+    def read_ref(self, name: str, ref: str, path: str) -> str:
+        return self._run(self.principal(name).clone, "show", f"{ref}:{path}", strip=False)
+
+    # -- internals ---------------------------------------------------------
+
+    def _env(self, tick: int | None = None, identity: tuple[str, str] | None = None) -> dict:
+        env = {
+            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
+            "HOME": str(self.root),
+            "GIT_CONFIG_GLOBAL": "/dev/null",
+            "GIT_CONFIG_NOSYSTEM": "1",
+            "GIT_TERMINAL_PROMPT": "0",
+            "LC_ALL": "C",
+        }
+        if identity is not None and tick is not None:
+            name, email = identity
+            when = date_for_tick(tick)
+            env.update(
+                GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when,
+                GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=when,
+            )
+        return env
+
+    def _commit(self, cwd: Path, message: str, identity: tuple[str, str], tick: int) -> None:
+        self._run(cwd, "add", "-A")
+        self._run(
+            cwd, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", message,
+            env=self._env(tick, identity),
+        )
+
+    def _run(self, cwd: Path, *args: str, env: dict | None = None, strip: bool = True) -> str:
+        proc = subprocess.run(
+            ["git", *args], cwd=cwd, env=env or self._env(), capture_output=True, text=True,
+        )
+        if proc.returncode != 0:
+            detail = proc.stderr.strip().replace(str(self.root), "<world>")
+            raise ScenarioError(f"git {args[0]} failed: {detail}")
+        return proc.stdout.strip() if strip else proc.stdout
+
+    # -- helpers for the status applier (its own clone, not a principal's) --
+
+    def clone_for(self, path: Path, identity: tuple[str, str]) -> Path:
+        """Clone the shared remote to ``path`` and set the local committer identity."""
+        self._run(self.root, "clone", "-q", self.remote_url, str(path))
+        self._run(path, "config", "user.name", identity[0])
+        self._run(path, "config", "user.email", identity[1])
+        return path
+
+    def commit_as(self, cwd: Path, message: str, identity: tuple[str, str], tick: int) -> None:
+        self._commit(cwd, message, identity, tick)
+
+    def run_git(self, cwd: Path, *args: str) -> str:
+        return self._run(cwd, *args)
diff --git a/skills/tests/multiplayer-simulation/test_agents.py b/skills/tests/multiplayer-simulation/test_agents.py
new file mode 100644
index 0000000..905249b
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_agents.py
@@ -0,0 +1,134 @@
+"""ScriptedAgent and Clock tests (P.1; design D5, D7, operator decision A1)."""
+
+from __future__ import annotations
+
+import ast
+import subprocess
+from pathlib import Path
+
+import pytest
+
+from mpsim.agents import Agent, ScriptedAgent
+from mpsim.clock import Clock
+from mpsim.model import PrincipalSpec, StatusTransition, Step, Transition
+from mpsim.world import World
+
+HARNESS = Path(__file__).resolve().parent
+SEED = {"roadmap.yaml": "items: []\n", "openspec/specs/sim-notes/spec.md": "# sim-notes\n"}
+
+
+def _spec(tmp_path: Path) -> tuple[PrincipalSpec, Path]:
+    fixture = tmp_path / "fixture"
+    payload = fixture / "principals" / "alice" / "plan" / "openspec" / "changes" / "sim-alice-notes"
+    (payload / "specs" / "sim-notes").mkdir(parents=True)
+    (payload / "proposal.md").write_text("# sim-alice-notes\n")
+    (payload / "specs" / "sim-notes" / "spec.md").write_text(
+        "## MODIFIED Requirements\n### Requirement: Alpha\n"
+    )
+    spec = PrincipalSpec(
+        name="alice",
+        change_id="sim-alice-notes",
+        roadmap_item="ri-alice",
+        steps=(
+            Step("plan", 1, files_from="principals/alice/plan"),
+            Step("implement", 4, on_start=Transition("in_progress"),
+                 on_finish=Transition("completed")),
+        ),
+    )
+    return spec, fixture
+
+
+def _git(cwd: Path, *args: str) -> str:
+    return subprocess.run(
+        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
+        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
+             "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd)},
+    ).stdout.strip()
+
+
+@pytest.fixture
+def setup(tmp_path):
+    world = World.create(tmp_path / "world", ("alice", "bob"), seed_files=SEED)
+    spec, fixture = _spec(tmp_path)
+    agent = ScriptedAgent(spec, fixture)
+    return world, agent, spec
+
+
+def test_scripted_agent_satisfies_the_agent_protocol(setup):
+    _, agent, _ = setup
+    assert isinstance(agent, Agent)
+    assert agent.principal == "alice"
+    assert agent.agent_id == "alice-agent-1"
+
+
+def test_plan_step_writes_openspec_files_commits_and_pushes_to_the_change_branch(setup):
+    world, agent, spec = setup
+    agent.act(world, spec.step("plan"), tick=1)
+
+    wt = world.worktree_path("alice", "sim-alice-notes")
+    assert (wt / "openspec/changes/sim-alice-notes/specs/sim-notes/spec.md").is_file()
+    clone = world.principal("alice").clone
+    assert _git(clone, "log", "-1", "--format=%an <%ae>", "sim/alice/sim-alice-notes") == (
+        "alice <alice@sim.invalid>"
+    )
+    remote_refs = _git(world.principal("alice").clone, "ls-remote", "--heads", "origin")
+    assert "refs/heads/sim/alice/sim-alice-notes" in remote_refs
+    # main is untouched
+    assert _git(clone, "rev-parse", "origin/main") == _git(clone, "rev-parse", "main")
+
+
+def test_act_returns_the_declared_transitions_and_does_not_apply_them(setup):
+    world, agent, spec = setup
+    agent.act(world, spec.step("plan"), tick=1)
+    result = agent.act(world, spec.step("implement"), tick=5)
+
+    assert result == [StatusTransition("alice", "ri-alice", "completed", "finish", "implement")]
+    assert agent.declared_transitions(spec.step("implement"), "start") == [
+        StatusTransition("alice", "ri-alice", "in_progress", "start", "implement")
+    ]
+    assert agent.act(world, spec.step("plan"), tick=6) == []  # plan declares nothing
+
+    changed = _git(world.principal("alice").clone, "diff", "--name-only",
+                   "origin/main", "sim/alice/sim-alice-notes").splitlines()
+    assert "roadmap.yaml" not in changed
+
+
+def test_agent_never_modifies_roadmap_or_pushes_main(setup):
+    world, agent, spec = setup
+    agent.act(world, spec.step("plan"), tick=1)
+    agent.act(world, spec.step("implement"), tick=5)
+    clone = world.principal("alice").clone
+    world.fetch("alice")
+    assert _git(clone, "rev-list", "--count", "origin/main") == "1"  # only the seed commit
+    touched = _git(clone, "log", "--name-only", "--format=", "origin/main..sim/alice/sim-alice-notes")
+    assert "roadmap.yaml" not in touched.splitlines()
+
+
+def test_a_step_without_files_still_produces_a_commit(setup):
+    world, agent, spec = setup
+    agent.act(world, spec.step("plan"), tick=1)
+    before = _git(world.principal("alice").clone, "rev-list", "--count", "sim/alice/sim-alice-notes")
+    agent.act(world, spec.step("implement"), tick=5)
+    after = _git(world.principal("alice").clone, "rev-list", "--count", "sim/alice/sim-alice-notes")
+    assert int(after) == int(before) + 1
+
+
+def test_clock_advances_only_when_told_to():
+    clock = Clock()
+    assert clock.tick == 0
+    assert clock.tick == 0
+    assert clock.advance() == 1
+    assert clock.advance(3) == 4
+    with pytest.raises(ValueError):
+        clock.advance(-1)
+
+
+def test_clock_module_never_reads_wall_clock_time():
+    tree = ast.parse((HARNESS / "mpsim" / "clock.py").read_text())
+    imported = {
+        alias.name.split(".")[0]
+        for node in ast.walk(tree)
+        if isinstance(node, (ast.Import, ast.ImportFrom))
+        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
+    }
+    assert not imported & {"time", "datetime", "calendar"}
diff --git a/skills/tests/multiplayer-simulation/test_archive_stability.py b/skills/tests/multiplayer-simulation/test_archive_stability.py
new file mode 100644
index 0000000..208c4e2
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_archive_stability.py
@@ -0,0 +1,59 @@
+"""Archive stability (A.1, A.2, A.3; design D10).
+
+A.3 holds by construction: harness tests read this change's artifacts only through
+``change_dir()`` (see ``test_contracts.py``) and read contracts only from their promoted
+paths under ``openspec/contracts/multiplayer-simulation/``. No harness module holds a
+literal ``openspec/changes/<id>`` path, which A.1 enforces through the shared guard.
+"""
+
+from __future__ import annotations
+
+import subprocess
+import sys
+from pathlib import Path
+
+import yaml
+from openspec_paths import repo_root_from
+
+HARNESS = Path(__file__).resolve().parent
+REPO = repo_root_from(__file__, 3)
+CHANGES = REPO / "openspec" / "changes"
+
+
+def _real_change_ids() -> set[str]:
+    """Active and archived change ids, read the way the path-stability guard reads them."""
+    ids = {e.name for e in CHANGES.iterdir() if e.is_dir() and e.name != "archive"}
+    archive = CHANGES / "archive"
+    if archive.is_dir():
+        for entry in archive.iterdir():
+            if entry.is_dir():
+                parts = entry.name.split("-", 3)
+                ids.add(parts[3] if len(parts) == 4 and parts[0].isdigit() else entry.name)
+    return ids
+
+
+def _fixture_change_ids() -> set[str]:
+    ids: set[str] = set()
+    for descriptor in sorted((HARNESS / "fixtures").glob("*/scenario.yaml")):
+        for principal in yaml.safe_load(descriptor.read_text())["principals"]:
+            ids.add(principal["change_id"])
+    for changes_dir in (HARNESS / "fixtures").rglob("changes"):
+        ids.update(p.name for p in changes_dir.iterdir() if p.is_dir())
+    return ids
+
+
+def test_fixture_change_ids_are_synthetic_and_not_real():
+    fixture_ids = _fixture_change_ids()
+    assert fixture_ids, "no fixture change ids found"
+    assert all(i.startswith("sim-") for i in fixture_ids)
+    assert fixture_ids & _real_change_ids() == set()
+
+
+def test_the_path_stability_guard_reports_nothing_in_the_harness():
+    proc = subprocess.run(
+        [sys.executable, "-m", "pytest", "tests/openspec_paths", "-q", "-p", "no:cacheprovider"],
+        cwd=REPO / "skills", capture_output=True, text=True,
+    )
+    output = proc.stdout + proc.stderr
+    assert proc.returncode == 0, output
+    assert "multiplayer-simulation" not in output
diff --git a/skills/tests/multiplayer-simulation/test_blocked_scenarios.py b/skills/tests/multiplayer-simulation/test_blocked_scenarios.py
new file mode 100644
index 0000000..743f49f
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_blocked_scenarios.py
@@ -0,0 +1,154 @@
+"""Memory-store blocked-dependency scenario tests (B.1-B.6; design D5, D7)."""
+
+from __future__ import annotations
+
+import ast
+import json
+import shutil
+import subprocess
+from pathlib import Path
+
+import jsonschema
+import pytest
+import yaml
+from openspec_paths import repo_root_from
+
+from mpsim.runner import run
+
+HARNESS = Path(__file__).resolve().parent
+REPO = repo_root_from(__file__, 3)
+SCHEMA = json.loads(
+    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
+)
+BLOCKED = "memory-store-blocked-dependency"
+CONTROL = "independent-principals-control"
+STATUS_LITERALS = {"approved", "in_progress", "completed"}
+
+
+def _copy_fixture(tmp_path: Path, name: str) -> Path:
+    dest = tmp_path / "fixture"
+    shutil.copytree(HARNESS / "fixtures" / name, dest)
+    return dest
+
+
+def _edit_yaml(path: Path, mutate) -> None:
+    data = yaml.safe_load(path.read_text())
+    mutate(data)
+    path.write_text(yaml.safe_dump(data, sort_keys=False))
+
+
+def _git(cwd: Path, *args: str) -> str:
+    return subprocess.run(
+        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
+        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
+             "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd)},
+    ).stdout.strip()
+
+
+def test_baseline_dependent_principal_is_blocked_until_the_dependency_is_implemented():
+    result = run(BLOCKED)
+    assert result.exit_code == 0
+    report = result.report
+    assert report["blocked_ticks"] == {"retrieval-owner": 10, "storage-owner": 0}
+    assert report["unblocked"] == {"retrieval-owner": True, "storage-owner": True}
+    assert report["collision_present"] is None and report["collision_detected"] is None
+    assert report["probes"] is None
+    assert report["final_tick"] == 15
+    jsonschema.Draft202012Validator(SCHEMA).validate(report)
+
+
+def test_dependency_completed_at_tick_11_admits_the_dependent_at_tick_11():
+    timeline = run(BLOCKED).report["timeline"]
+    admitted = [e for e in timeline if e["event"] == "admitted" and e["principal"] == "retrieval-owner"]
+    assert [e["tick"] for e in admitted] == [11]
+    assert admitted[0]["step"] == "implement"
+    finished = [e for e in timeline if (e["principal"], e["step"], e["event"]) ==
+                ("storage-owner", "implement", "finished")]
+    assert [e["tick"] for e in finished] == [11]
+
+
+def test_independent_principals_are_never_blocked():
+    result = run(CONTROL)
+    assert result.exit_code == 0
+    assert set(result.report["blocked_ticks"].values()) == {0}
+    assert set(result.report["unblocked"].values()) == {True}
+
+
+def test_a_tick_budget_below_completion_bounds_the_run():
+    result = run(BLOCKED, tick_budget=5)
+    assert result.exit_code == 0
+    report = result.report
+    assert report["final_tick"] == 5
+    assert report["unblocked"]["retrieval-owner"] is False
+    assert report["blocked_ticks"]["retrieval-owner"] == 4
+    assert report["unblocked"]["storage-owner"] is True
+    jsonschema.Draft202012Validator(SCHEMA).validate(report)
+
+
+def test_a_dependency_that_starts_completed_unblocks_through_the_admission_rule(tmp_path):
+    fixture = _copy_fixture(tmp_path, BLOCKED)
+
+    def complete(data):
+        for item in data["items"]:
+            if item["item_id"] == "ri-storage":
+                item["status"] = "completed"
+
+    _edit_yaml(fixture / "seed" / "roadmap.yaml", complete)
+    result = run(BLOCKED, fixture_dir=fixture, tick_budget=20)
+    assert result.exit_code == 0
+    assert result.report["blocked_ticks"]["retrieval-owner"] == 0
+    assert result.report["unblocked"]["retrieval-owner"] is True
+
+
+def test_status_transitions_reach_only_the_integration_ref(tmp_path):
+    work = tmp_path / "kept"
+    result = run(BLOCKED, work_root=work)
+    assert result.exit_code == 0
+    remote = work / "world" / "remote.git"
+    seed = _git(remote, "rev-list", "--max-parents=0", "main")
+
+    branches = _git(remote, "for-each-ref", "--format=%(refname)", "refs/heads/sim/").splitlines()
+    assert len(branches) == 2
+    for ref in branches:
+        touched = _git(remote, "log", "--name-only", "--format=", f"{seed}..{ref}").splitlines()
+        assert "roadmap.yaml" not in touched, ref
+
+    authors = _git(remote, "log", "--format=%an", f"{seed}..main").splitlines()
+    assert authors and set(authors) == {"sim-supervisor"}
+
+    final = yaml.safe_load(_git(remote, "show", "main:roadmap.yaml"))
+    assert {i["item_id"]: i["status"] for i in final["items"]} == {
+        "ri-storage": "completed", "ri-retrieval": "completed"}
+
+
+def test_no_status_literal_is_used_as_a_set_status_value_in_the_driver():
+    offenders = []
+    for path in sorted((HARNESS / "mpsim").rglob("*.py")):
+        tree = ast.parse(path.read_text())
+        for node in ast.walk(tree):
+            if isinstance(node, ast.Constant) and node.value in STATUS_LITERALS:
+                offenders.append(f"{path.name}:{node.lineno}:{node.value}")
+    assert offenders == []
+
+
+def test_a_fixture_without_on_finish_leaves_the_dependent_blocked(tmp_path):
+    fixture = _copy_fixture(tmp_path, BLOCKED)
+
+    def drop_finish(data):
+        for principal in data["principals"]:
+            for step in principal["steps"]:
+                if principal["name"] == "storage-owner" and step["name"] == "implement":
+                    step.pop("on_finish")
+
+    _edit_yaml(fixture / "scenario.yaml", drop_finish)
+    result = run(BLOCKED, fixture_dir=fixture, tick_budget=30)
+    assert result.exit_code == 0
+    assert result.report["unblocked"]["retrieval-owner"] is False
+    assert result.report["blocked_ticks"]["retrieval-owner"] == 29
+
+
+@pytest.mark.parametrize("scenario", [BLOCKED, CONTROL])
+def test_report_names_two_principals_with_distinct_agents(scenario):
+    report = run(scenario).report
+    assert [p["name"] for p in report["principals"]] == ["storage-owner", "retrieval-owner"]
+    assert len({p["agent_id"] for p in report["principals"]}) == 2
diff --git a/skills/tests/multiplayer-simulation/test_cli.py b/skills/tests/multiplayer-simulation/test_cli.py
new file mode 100644
index 0000000..c104508
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_cli.py
@@ -0,0 +1,168 @@
+"""CLI tests, running ``bin/mpsim`` by subprocess (P.4, S.4, D.1, D.2, O.2, O.4)."""
+
+from __future__ import annotations
+
+import ast
+import json
+import os
+import re
+import shutil
+import subprocess
+import sys
+from concurrent.futures import ThreadPoolExecutor
+from pathlib import Path
+
+import jsonschema
+import pytest
+import yaml
+from openspec_paths import repo_root_from
+
+HARNESS = Path(__file__).resolve().parent
+LAUNCHER = HARNESS / "bin" / "mpsim"
+REPO = repo_root_from(__file__, 3)
+SCHEMA = json.loads(
+    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
+)
+SCENARIOS = [
+    "different-requirement-control",
+    "independent-principals-control",
+    "memory-store-blocked-dependency",
+    "same-requirement-collision",
+]
+HEX40 = re.compile(r"[0-9a-f]{40}")
+
+
+def mpsim(*args: str, env_extra: dict[str, str] | None = None, unset: tuple[str, ...] = ()):
+    env = {k: v for k, v in os.environ.items() if k not in unset}
+    env.update(env_extra or {})
+    return subprocess.run(
+        [sys.executable, str(LAUNCHER), *args], capture_output=True, text=True, env=env,
+        cwd=HARNESS,
+    )
+
+
+@pytest.fixture(scope="module")
+def baseline() -> dict[str, subprocess.CompletedProcess]:
+    """Each scenario once with COORDINATION_API_URL unset, run in parallel."""
+    def one(scenario: str):
+        return scenario, mpsim("run", "--scenario", scenario, unset=("COORDINATION_API_URL",))
+
+    with ThreadPoolExecutor(max_workers=4) as pool:
+        return dict(pool.map(one, SCENARIOS))
+
+
+def test_list_prints_the_four_scenario_ids_sorted():
+    proc = mpsim("list")
+    assert proc.returncode == 0
+    assert json.loads(proc.stdout) == SCENARIOS
+    assert json.loads(proc.stdout) == sorted(json.loads(proc.stdout))
+
+
+@pytest.mark.parametrize(
+    ("args", "needle"),
+    [
+        (["run", "--scenario", "no-such-scenario"], "no-such-scenario"),
+        (["run", "--scenario", "same-requirement-collision", "--probe", "does-not-exist"],
+         "does-not-exist"),
+        (["run", "--scenario", "same-requirement-collision", "--fixture-dir", "/nonexistent/dir"],
+         "fixture-dir"),
+        (["run", "--scenario", "memory-store-blocked-dependency", "--tick-budget", "0"],
+         "tick-budget"),
+    ],
+)
+def test_semantic_usage_errors_exit_64_and_name_the_problem(args, needle):
+    proc = mpsim(*args)
+    assert proc.returncode == 64, proc.stderr
+    assert needle in proc.stderr
+    assert proc.stdout == ""
+
+
+def test_a_one_principal_fixture_exits_64_naming_the_minimum(tmp_path):
+    fixture = tmp_path / "fixture"
+    shutil.copytree(HARNESS / "fixtures" / "same-requirement-collision", fixture)
+    descriptor = fixture / "scenario.yaml"
+    data = yaml.safe_load(descriptor.read_text())
+    data["principals"] = data["principals"][:1]
+    descriptor.write_text(yaml.safe_dump(data))
+    proc = mpsim("run", "--scenario", "same-requirement-collision", "--fixture-dir", str(fixture))
+    assert proc.returncode == 64
+    assert "at least 2 principals" in proc.stderr
+
+
+@pytest.mark.parametrize("args", [[], ["run"], ["run", "--tick-budget", "x"]])
+def test_argparse_errors_exit_2(args):
+    assert mpsim(*args).returncode == 2
+
+
+def test_repeated_runs_with_different_tmpdirs_are_byte_identical(baseline, tmp_path):
+    other_tmp = tmp_path / "other-tmp"
+    other_tmp.mkdir()
+    again = mpsim("run", "--scenario", "memory-store-blocked-dependency",
+                  env_extra={"TMPDIR": str(other_tmp)}, unset=("COORDINATION_API_URL",))
+    assert again.returncode == 0
+    assert again.stdout == baseline["memory-store-blocked-dependency"].stdout
+
+
+def test_coordinator_environment_does_not_change_any_scenario(baseline):
+    def one(scenario: str):
+        return scenario, mpsim("run", "--scenario", scenario,
+                               env_extra={"COORDINATION_API_URL": "http://127.0.0.1:9"})
+
+    with ThreadPoolExecutor(max_workers=4) as pool:
+        with_env = dict(pool.map(one, SCENARIOS))
+    for scenario in SCENARIOS:
+        assert with_env[scenario].returncode == 0
+        assert with_env[scenario].stdout == baseline[scenario].stdout, scenario
+
+
+@pytest.mark.parametrize("scenario", SCENARIOS)
+def test_every_scenario_report_validates_and_leaks_nothing(baseline, scenario):
+    proc = baseline[scenario]
+    assert proc.returncode == 0, proc.stderr
+    report = json.loads(proc.stdout)
+    jsonschema.Draft202012Validator(SCHEMA).validate(report)
+    assert list(report) == sorted(report)
+    assert not HEX40.search(proc.stdout)
+    assert "/tmp" not in proc.stdout and "mpsim-" not in proc.stdout
+    assert str(HARNESS) not in proc.stdout
+
+
+def test_the_exit_1_report_validates_and_leaks_nothing(tmp_path):
+    fixture = tmp_path / "fixture"
+    shutil.copytree(HARNESS / "fixtures" / "same-requirement-collision", fixture)
+    spec = fixture / "principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md"
+    spec.write_text(spec.read_text().replace("Note Titles", "Note Bodies"))
+    proc = mpsim("run", "--scenario", "same-requirement-collision", "--fixture-dir", str(fixture))
+    assert proc.returncode == 1
+    report = json.loads(proc.stdout)
+    assert report["error"]
+    jsonschema.Draft202012Validator(SCHEMA).validate(report)
+    assert str(tmp_path) not in proc.stdout
+    assert not HEX40.search(proc.stdout)
+
+
+FORBIDDEN_TOP = {"src", "agent_coordinator", "coordination_bridge", "httpx", "requests", "mcp",
+                 "aiohttp"}
+FORBIDDEN_DOTTED = {"urllib.request", "http.client"}
+
+
+def _imports(tree: ast.AST):
+    for node in ast.walk(tree):
+        if isinstance(node, ast.Import):
+            for alias in node.names:
+                yield alias.name
+        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
+            yield node.module
+            for alias in node.names:
+                yield f"{node.module}.{alias.name}"
+
+
+def test_driver_modules_import_no_coordinator_or_transport():
+    offenders = []
+    for path in sorted((HARNESS / "mpsim").rglob("*.py")):
+        for name in _imports(ast.parse(path.read_text())):
+            if name.split(".")[0] in FORBIDDEN_TOP or any(
+                name == d or name.startswith(d + ".") for d in FORBIDDEN_DOTTED
+            ):
+                offenders.append(f"{path.relative_to(HARNESS)}: {name}")
+    assert offenders == []
diff --git a/skills/tests/multiplayer-simulation/test_collision_scenarios.py b/skills/tests/multiplayer-simulation/test_collision_scenarios.py
new file mode 100644
index 0000000..697c5b0
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_collision_scenarios.py
@@ -0,0 +1,90 @@
+"""Collision scenario tests (C.1, C.2, C.3; design D4, D6)."""
+
+from __future__ import annotations
+
+import shutil
+from pathlib import Path
+
+import jsonschema
+import json
+import pytest
+from openspec_paths import repo_root_from
+
+from mpsim import probes
+from mpsim.runner import run
+
+HARNESS = Path(__file__).resolve().parent
+REPO = repo_root_from(__file__, 3)
+SCHEMA = json.loads(
+    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
+)
+
+
+@pytest.fixture(autouse=True)
+def _empty_registry():
+    saved = dict(probes.REGISTRY)
+    probes.REGISTRY.clear()
+    yield
+    probes.REGISTRY.clear()
+    probes.REGISTRY.update(saved)
+
+
+def test_baseline_collision_is_present_but_not_detected():
+    result = run("same-requirement-collision")
+    assert result.exit_code == 0
+    report = result.report
+    assert report["collision_present"] is True
+    assert report["collision_detected"] is False
+    assert report["probes"] == []
+    jsonschema.Draft202012Validator(SCHEMA).validate(report)
+
+
+def test_report_names_both_principals_with_distinct_agents():
+    report = run("same-requirement-collision").report
+    assert [p["name"] for p in report["principals"]] == ["alice", "bob"]
+    assert len({p["agent_id"] for p in report["principals"]}) == 2
+    assert [p["change_id"] for p in report["principals"]] == ["sim-alice-notes", "sim-bob-notes"]
+    assert report["blocked_ticks"] is None and report["unblocked"] is None
+
+
+def test_timeline_has_bob_planning_after_alice_pushed():
+    timeline = run("same-requirement-collision").report["timeline"]
+    pushed = next(i for i, e in enumerate(timeline)
+                  if (e["principal"], e["event"]) == ("alice", "pushed"))
+    bob_started = next(i for i, e in enumerate(timeline)
+                       if (e["principal"], e["event"]) == ("bob", "started"))
+    assert pushed < bob_started
+    assert any(e["event"] == "probed" and e["principal"] == "bob" for e in timeline)
+
+
+def test_different_requirements_produce_no_collision():
+    result = run("different-requirement-control")
+    assert result.exit_code == 0
+    assert result.report["collision_present"] is False
+    assert result.report["collision_detected"] is False
+
+
+def test_a_fixture_that_loses_the_shared_requirement_fails_loudly(tmp_path):
+    fixture = tmp_path / "fixture"
+    shutil.copytree(HARNESS / "fixtures" / "same-requirement-collision", fixture)
+    bob_spec = (fixture / "principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md")
+    bob_spec.write_text(bob_spec.read_text().replace("Note Titles", "Note Bodies"))
+
+    result = run("same-requirement-collision", fixture_dir=fixture)
+
+    assert result.exit_code == 1
+    assert result.report["error"]
+    assert "collision" in result.report["error"]
+    assert "absent" in result.report["error"]
+    jsonschema.Draft202012Validator(SCHEMA).validate(result.report)
+    assert str(tmp_path) not in result.text
+
+
+def test_a_control_fixture_that_gains_a_collision_also_fails_loudly(tmp_path):
+    fixture = tmp_path / "fixture"
+    shutil.copytree(HARNESS / "fixtures" / "different-requirement-control", fixture)
+    bob_spec = (fixture / "principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md")
+    bob_spec.write_text(bob_spec.read_text().replace("Note Bodies", "Note Titles"))
+    result = run("different-requirement-control", fixture_dir=fixture)
+    assert result.exit_code == 1
+    assert "unexpected" in result.report["error"]
diff --git a/skills/tests/multiplayer-simulation/test_contracts.py b/skills/tests/multiplayer-simulation/test_contracts.py
new file mode 100644
index 0000000..dcfaa38
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_contracts.py
@@ -0,0 +1,101 @@
+"""Contract tests: CLI contract, report schema, traceability and promotion (G.4, A.1).
+
+Everything is read through ``repo_root_from`` and ``change_dir`` so the tests
+survive archival of this change (design D10). The contract and schema are read
+from their promoted paths under ``openspec/contracts/multiplayer-simulation/``.
+"""
+
+from __future__ import annotations
+
+import json
+import re
+from pathlib import Path
+
+import jsonschema
+import pytest
+import yaml
+from referencing import Registry, Resource
+from openspec_paths import change_dir, repo_root_from
+
+CHANGE_ID = "multiplayer-simulation-harness"
+CAPABILITY = "multiplayer-simulation"
+
+REPO = repo_root_from(__file__, 3)
+PROMOTED = REPO / "openspec" / "contracts" / CAPABILITY
+CLI_CONTRACT = PROMOTED / "cli" / "mpsim.yaml"
+REPORT_SCHEMA = PROMOTED / "schemas" / "sim-report.schema.json"
+CLI_CONTRACT_SCHEMA = (
+    REPO / "openspec" / "contracts" / "gen-eval-framework" / "schemas" / "cli-contract.schema.json"
+)
+
+
+def _local_registry() -> Registry:
+    """Resolve the schema's sibling $refs from disk; the harness runs offline (D9)."""
+    registry: Registry = Registry()
+    for path in sorted(CLI_CONTRACT_SCHEMA.parent.glob("*.schema.json")):
+        doc = json.loads(path.read_text())
+        registry = registry.with_resource(doc["$id"], Resource.from_contents(doc))
+    return registry
+
+
+def _change_local(rel: str) -> Path:
+    return change_dir(REPO, CHANGE_ID) / "contracts" / rel
+
+
+def _slug(heading: str) -> str:
+    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
+
+
+def _spec_requirement_slugs() -> set[str]:
+    spec = change_dir(REPO, CHANGE_ID) / "specs" / CAPABILITY / "spec.md"
+    headings = re.findall(r"^### Requirement:\s*(.+?)\s*$", spec.read_text(), re.MULTILINE)
+    assert headings, f"no requirement headings found in {spec}"
+    return {f"{CAPABILITY}.{_slug(h)}" for h in headings}
+
+
+def _citations(node) -> list[str]:
+    found: list[str] = []
+    if isinstance(node, dict):
+        for key, value in node.items():
+            if key == "traceability":
+                found.extend(value.get("requirements", []))
+            else:
+                found.extend(_citations(value))
+    elif isinstance(node, list):
+        for item in node:
+            found.extend(_citations(item))
+    return found
+
+
+def test_cli_contract_validates_against_the_cli_contract_schema():
+    schema = json.loads(CLI_CONTRACT_SCHEMA.read_text())
+    contract = yaml.safe_load(CLI_CONTRACT.read_text())
+    validator = jsonschema.Draft202012Validator(schema, registry=_local_registry())
+    errors = [e.message for e in validator.iter_errors(contract)]
+    assert errors == []
+
+
+def test_report_schema_is_a_valid_draft_2020_12_schema():
+    schema = json.loads(REPORT_SCHEMA.read_text())
+    jsonschema.Draft202012Validator.check_schema(schema)
+    assert schema["$schema"].endswith("2020-12/schema")
+
+
+def test_every_traceability_citation_resolves_to_a_requirement_heading():
+    contract = yaml.safe_load(CLI_CONTRACT.read_text())
+    cited = _citations(contract)
+    assert cited, "the contract cites no requirements"
+    known = _spec_requirement_slugs()
+    unresolved = sorted(set(cited) - known)
+    assert unresolved == []
+
+
+@pytest.mark.parametrize(
+    ("promoted", "local"),
+    [
+        (CLI_CONTRACT, "cli/mpsim.yaml"),
+        (REPORT_SCHEMA, "schemas/sim-report.schema.json"),
+    ],
+)
+def test_promoted_copy_is_byte_identical_to_the_change_local_copy(promoted: Path, local: str):
+    assert promoted.read_bytes() == _change_local(local).read_bytes()
diff --git a/skills/tests/multiplayer-simulation/test_descriptor_drift.py b/skills/tests/multiplayer-simulation/test_descriptor_drift.py
new file mode 100644
index 0000000..83a5639
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_descriptor_drift.py
@@ -0,0 +1,36 @@
+"""The committed descriptor cannot drift from the CLI contract (G.4; design D3, D8)."""
+
+from __future__ import annotations
+
+import subprocess
+import sys
+from pathlib import Path
+
+from openspec_paths import repo_root_from
+
+HARNESS = Path(__file__).resolve().parent
+REPO = repo_root_from(__file__, 3)
+GENERATOR = REPO / "packages" / "gen-eval" / "scripts" / "generate_tool_descriptor.py"
+CONTRACT = REPO / "openspec" / "contracts" / "multiplayer-simulation" / "cli" / "mpsim.yaml"
+DESCRIPTOR = HARNESS / "evaluation" / "descriptor.yaml"
+
+
+def _check(descriptor: Path) -> subprocess.CompletedProcess:
+    return subprocess.run(
+        [sys.executable, str(GENERATOR), "--contract", str(CONTRACT), "--out", str(descriptor),
+         "--check"],
+        capture_output=True, text=True,
+    )
+
+
+def test_committed_descriptor_matches_the_contract():
+    proc = _check(DESCRIPTOR)
+    assert proc.returncode == 0, proc.stdout + proc.stderr
+
+
+def test_a_mutated_descriptor_fails_the_check(tmp_path):
+    mutated = tmp_path / "descriptor.yaml"
+    mutated.write_text(DESCRIPTOR.read_text().replace("name: --tick-budget", "name: --tick-budgets"))
+    assert mutated.read_text() != DESCRIPTOR.read_text()
+    proc = _check(mutated)
+    assert proc.returncode != 0
diff --git a/skills/tests/multiplayer-simulation/test_gen_eval_pack.py b/skills/tests/multiplayer-simulation/test_gen_eval_pack.py
new file mode 100644
index 0000000..5aca505
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_gen_eval_pack.py
@@ -0,0 +1,111 @@
+"""The gen-eval scenario pack (G.1, G.2, G.3; design D3, D8).
+
+gen-eval silently skips a scenario that fails to load, so the pack run also asserts that
+every scenario in the pack actually ran and that "Invalid scenario" never appears.
+"""
+
+from __future__ import annotations
+
+import json
+import os
+import re
+import shutil
+import subprocess
+import sys
+from pathlib import Path
+
+import yaml
+
+HARNESS = Path(__file__).resolve().parent
+EVALUATION = HARNESS / "evaluation"
+SCENARIO_DIR = EVALUATION / "scenarios"
+GEN_EVAL = Path(sys.executable).parent / "gen-eval"
+EXPECTED_NAMED = {
+    "same-requirement-collision",
+    "different-requirement-control",
+    "memory-store-blocked-dependency",
+    "independent-principals-control",
+}
+
+
+def _declared_ids(scenario_dir: Path) -> list[str]:
+    ids: list[str] = []
+    for path in sorted(scenario_dir.glob("*.yaml")):
+        ids.extend(s["id"] for s in yaml.safe_load(path.read_text()))
+    return ids
+
+
+def _run_pack(evaluation: Path, out: Path) -> subprocess.CompletedProcess:
+    env = dict(os.environ)
+    env["PATH"] = os.pathsep.join(
+        [str(HARNESS / "bin"), str(Path(sys.executable).parent), env.get("PATH", "")]
+    )
+    env.pop("COORDINATION_API_URL", None)
+    return subprocess.run(
+        [str(GEN_EVAL), "--descriptor", str(evaluation / "descriptor.yaml"),
+         "--fail-threshold", "1.0", "--output-dir", str(out)],
+        cwd=HARNESS, env=env, capture_output=True, text=True,
+    )
+
+
+def _report(out: Path) -> dict:
+    return json.loads((out / "gen-eval-report.json").read_text())
+
+
+def test_pack_declares_the_four_named_scenarios():
+    assert EXPECTED_NAMED <= set(_declared_ids(SCENARIO_DIR))
+    ids = _declared_ids(SCENARIO_DIR)
+    assert len(ids) == len(set(ids))
+
+
+def test_the_pack_passes_against_the_baseline(tmp_path):
+    proc = _run_pack(EVALUATION, tmp_path / "out")
+    combined = proc.stdout + proc.stderr
+    assert proc.returncode == 0, combined
+    assert "Invalid scenario" not in combined
+    report = _report(tmp_path / "out")
+    declared = _declared_ids(SCENARIO_DIR)
+    assert report["total_scenarios"] == len(declared)
+    assert report["passed"] == len(declared)
+    assert report["failed"] == 0 and report["errors"] == 0 and report["skipped"] == 0
+    ran = {v.get("scenario_id") for v in report["verdicts"]}
+    assert EXPECTED_NAMED <= ran
+
+
+def test_a_changed_measurement_fails_the_pack(tmp_path):
+    pack = tmp_path / "evaluation"
+    shutil.copytree(EVALUATION, pack)
+    # The descriptor's contract path is relative to its own location; point the copy home.
+    descriptor = yaml.safe_load((pack / "descriptor.yaml").read_text())
+    descriptor["contract"] = str(
+        (EVALUATION / descriptor["contract"]).resolve()
+    )
+    (pack / "descriptor.yaml").write_text(yaml.safe_dump(descriptor, sort_keys=False))
+    target = pack / "scenarios" / "collision.yaml"
+    text = target.read_text()
+    flipped = text.replace(
+        "          collision_detected: false\n          probes: []",
+        "          collision_detected: true\n          probes: []",
+        1,
+    )
+    assert flipped != text
+    target.write_text(flipped)
+
+    proc = _run_pack(pack, tmp_path / "out")
+    assert proc.returncode == 1, proc.stdout + proc.stderr
+    report = _report(tmp_path / "out")
+    failed = [v for v in report["verdicts"] if v.get("status") != "pass"]
+    assert [v["scenario_id"] for v in failed] == ["same-requirement-collision"]
+
+
+def test_every_pinned_baseline_names_the_item_that_flips_it():
+    pins = {"collision_detected": "ri-06", "blocked_ticks": "ri-11"}
+    checked = 0
+    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
+        text = path.read_text()
+        comments = "\n".join(re.findall(r"#.*", text))
+        for key, item in pins.items():
+            if re.search(rf"^\s*{key}:", text, re.MULTILINE):
+                checked += 1
+                assert item in comments, f"{path.name} pins {key} without naming {item}"
+    assert checked >= 2
diff --git a/skills/tests/multiplayer-simulation/test_oracle.py b/skills/tests/multiplayer-simulation/test_oracle.py
new file mode 100644
index 0000000..1b1fe23
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_oracle.py
@@ -0,0 +1,46 @@
+"""Ground-truth collision oracle tests (C.1, C.2; design D4)."""
+
+from __future__ import annotations
+
+from pathlib import Path
+
+from mpsim.oracle import collision_present, delta_requirements
+
+
+def _delta(root: Path, capability: str, *headings: str) -> Path:
+    spec = root / "specs" / capability / "spec.md"
+    spec.parent.mkdir(parents=True)
+    body = "## MODIFIED Requirements\n\n" + "".join(
+        f"### Requirement: {h}\n\nThe system SHALL do {h}.\n\n" for h in headings
+    )
+    spec.write_text(body)
+    return root
+
+
+def test_same_heading_in_same_capability_is_a_collision(tmp_path):
+    a = _delta(tmp_path / "a", "sim-notes", "Note Titles")
+    b = _delta(tmp_path / "b", "sim-notes", "Note Titles", "Other")
+    assert collision_present(a, b) is True
+
+
+def test_different_headings_in_same_capability_are_not_a_collision(tmp_path):
+    a = _delta(tmp_path / "a", "sim-notes", "Note Titles")
+    b = _delta(tmp_path / "b", "sim-notes", "Note Bodies")
+    assert collision_present(a, b) is False
+
+
+def test_same_heading_in_different_capabilities_is_not_a_collision(tmp_path):
+    a = _delta(tmp_path / "a", "sim-notes", "Note Titles")
+    b = _delta(tmp_path / "b", "sim-tags", "Note Titles")
+    assert collision_present(a, b) is False
+
+
+def test_delta_requirements_returns_capability_heading_pairs(tmp_path):
+    root = _delta(tmp_path / "a", "sim-notes", "One", "Two")
+    assert delta_requirements(root) == {("sim-notes", "One"), ("sim-notes", "Two")}
+
+
+def test_a_delta_without_specs_has_no_requirements(tmp_path):
+    (tmp_path / "empty").mkdir()
+    assert delta_requirements(tmp_path / "empty") == set()
+    assert collision_present(tmp_path / "empty", tmp_path / "empty") is False
diff --git a/skills/tests/multiplayer-simulation/test_probes.py b/skills/tests/multiplayer-simulation/test_probes.py
new file mode 100644
index 0000000..26d6067
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_probes.py
@@ -0,0 +1,155 @@
+"""Probe seam tests (S.1-S.5; design D4). The registry starts empty."""
+
+from __future__ import annotations
+
+import hashlib
+import threading
+from pathlib import Path
+
+import pytest
+
+from mpsim import probes
+from mpsim.errors import UsageError
+from mpsim.probes import Collision, ProbeResult
+from mpsim.runner import run
+from mpsim.scenarios import scenario_ids
+
+HARNESS = Path(__file__).resolve().parent
+COLLISION_SCENARIOS = ("same-requirement-collision", "different-requirement-control")
+
+
+@pytest.fixture(autouse=True)
+def _isolated_registry():
+    saved = dict(probes.REGISTRY)
+    probes.REGISTRY.clear()
+    yield
+    probes.REGISTRY.clear()
+    probes.REGISTRY.update(saved)
+
+
+class StubProbe:
+    def __init__(self, probe_id="stub", *, level="requirement", other_change="sim-alice-notes"):
+        self.probe_id = probe_id
+        self._collision = Collision(level, other_change, "Note Titles")
+
+    def detect(self, view, change_id):
+        return ProbeResult(self.probe_id, "ok", [self._collision], None)
+
+
+class RaisingProbe:
+    probe_id = "raiser"
+
+    def detect(self, view, change_id):
+        raise RuntimeError("boom")
+
+
+class HangingProbe:
+    probe_id = "hanger"
+
+    def detect(self, view, change_id):
+        threading.Event().wait(30)
+        return ProbeResult(self.probe_id, "ok", [], None)
+
+
+def _hash_tree(*dirs: Path) -> dict[str, str]:
+    digests = {}
+    for root in dirs:
+        for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
+            digests[str(path.relative_to(HARNESS))] = hashlib.sha256(path.read_bytes()).hexdigest()
+    return digests
+
+
+def test_no_probe_is_registered_at_import_time():
+    import importlib
+    import sys
+
+    sys.modules.pop("mpsim.probes", None)
+    fresh = importlib.import_module("mpsim.probes")
+    try:
+        assert fresh.REGISTRY == {}
+    finally:
+        sys.modules["mpsim.probes"] = probes
+
+
+def test_requirement_level_collision_sets_collision_detected():
+    probes.register(StubProbe())
+    result = run("same-requirement-collision")
+    assert result.exit_code == 0
+    report = result.report
+    assert report["collision_detected"] is True
+    assert [p["probe_id"] for p in report["probes"]] == ["stub"]
+    assert report["probes"][0]["status"] == "ok"
+    assert report["probes"][0]["collisions"] == [
+        {"level": "requirement", "other_change": "sim-alice-notes", "requirement": "Note Titles"}
+    ]
+
+
+def test_non_requirement_level_collision_does_not_count_as_detection():
+    probes.register(StubProbe(level="file"))
+    report = run("same-requirement-collision").report
+    assert report["collision_detected"] is False
+    assert report["probes"][0]["status"] == "ok"
+
+
+def test_collision_against_an_unrelated_change_does_not_count():
+    probes.register(StubProbe(other_change="sim-somebody-else"))
+    assert run("same-requirement-collision").report["collision_detected"] is False
+
+
+def test_raising_probe_is_recorded_as_error_and_run_completes():
+    probes.register(RaisingProbe())
+    result = run("same-requirement-collision")
+    assert result.exit_code == 0
+    entry = result.report["probes"][0]
+    assert entry["probe_id"] == "raiser"
+    assert entry["status"] == "error"
+    assert entry["error"] and "boom" in entry["error"]
+    assert result.report["collision_detected"] is False
+
+
+def test_probe_exceeding_the_timeout_is_recorded_as_error(monkeypatch):
+    monkeypatch.setattr(probes, "PER_PROBE_TIMEOUT", 0.2)
+    probes.register(HangingProbe())
+    result = run("same-requirement-collision")
+    assert result.exit_code == 0
+    entry = result.report["probes"][0]
+    assert entry["status"] == "error"
+    assert "timeout" in entry["error"].lower()
+
+
+def test_unknown_probe_id_is_a_usage_error():
+    with pytest.raises(UsageError, match="does-not-exist"):
+        run("same-requirement-collision", probe_ids=["does-not-exist"])
+
+
+def test_probe_selection_restricts_the_run():
+    probes.register(StubProbe("one"))
+    probes.register(StubProbe("two"))
+    report = run("same-requirement-collision", probe_ids=["two"]).report
+    assert [p["probe_id"] for p in report["probes"]] == ["two"]
+
+
+def test_no_probe_flag_runs_every_registered_probe():
+    probes.register(StubProbe("one"))
+    probes.register(StubProbe("two"))
+    report = run("same-requirement-collision").report
+    assert [p["probe_id"] for p in report["probes"]] == ["one", "two"]
+
+
+def test_registering_a_probe_edits_no_scenario_definition():
+    watched = [HARNESS / "mpsim" / "scenarios", HARNESS / "evaluation" / "scenarios"]
+    watched = [d for d in watched if d.exists()]
+    before = _hash_tree(*watched)
+    probes.register(StubProbe())
+    for scenario_id in scenario_ids():
+        report = run(scenario_id).report
+        if scenario_id in COLLISION_SCENARIOS:
+            assert [p["probe_id"] for p in report["probes"]] == ["stub"], scenario_id
+    assert _hash_tree(*watched) == before
+    assert before, "expected scenario files to hash"
+
+
+def test_duplicate_registration_is_rejected():
+    probes.register(StubProbe("dup"))
+    with pytest.raises(ValueError):
+        probes.register(StubProbe("dup"))
diff --git a/skills/tests/multiplayer-simulation/test_report.py b/skills/tests/multiplayer-simulation/test_report.py
new file mode 100644
index 0000000..a3aaf30
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_report.py
@@ -0,0 +1,87 @@
+"""Report builder tests (D.2; design D8)."""
+
+from __future__ import annotations
+
+import json
+import re
+from pathlib import Path
+
+import jsonschema
+import pytest
+from openspec_paths import repo_root_from
+
+from mpsim.report import ReportError, new_report, render
+
+REPO = repo_root_from(__file__, 3)
+SCHEMA = json.loads(
+    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
+)
+PRINCIPALS = [
+    {"name": "alice", "agent_id": "alice-agent-1", "change_id": "sim-alice-notes"},
+    {"name": "bob", "agent_id": "bob-agent-1", "change_id": "sim-bob-notes"},
+]
+
+
+def _valid(**over):
+    base = dict(principals=PRINCIPALS, timeline=[])
+    base.update(over)
+    return new_report("same-requirement-collision", **base)
+
+
+def test_new_report_has_every_schema_property_with_null_for_inapplicable_fields():
+    report = _valid()
+    assert set(report) == set(SCHEMA["properties"])
+    assert report["blocked_ticks"] is None
+    assert report["unblocked"] is None
+    assert report["final_tick"] is None
+    assert report["error"] is None
+    assert report["schema_version"] == "1"
+
+
+def test_render_emits_sorted_keys_without_trailing_whitespace():
+    out = render(_valid())
+    parsed = json.loads(out)
+    assert list(parsed) == sorted(parsed)
+    assert out.endswith("\n") and not out.endswith("\n\n")
+    assert all(line == line.rstrip() for line in out.splitlines())
+    assert out == render(_valid())  # stable
+
+
+def test_rendered_report_validates_against_the_promoted_schema():
+    out = render(_valid(collision_present=True, collision_detected=False, probes=[]))
+    jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out))
+
+
+def test_error_report_may_have_no_principals_and_null_timeline():
+    out = render(new_report("same-requirement-collision", error="fixture lost the requirement"))
+    jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out))
+
+
+def test_error_free_report_with_one_principal_fails_schema_validation():
+    out = render(_valid(principals=PRINCIPALS[:1]))
+    with pytest.raises(jsonschema.ValidationError):
+        jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out))
+
+
+def test_unknown_field_is_rejected_by_the_builder():
+    with pytest.raises(TypeError):
+        new_report("x", bogus=1)
+
+
+def test_render_rejects_a_value_containing_the_world_root(tmp_path: Path):
+    root = tmp_path / "world"
+    report = _valid(error=f"git failed in {root}/principals/alice")
+    with pytest.raises(ReportError, match="world"):
+        render(report, forbidden_paths=[str(root)])
+
+
+def test_render_rejects_a_forty_character_hex_string():
+    sha = "a" * 20 + "0123456789" + "b" * 10
+    assert len(sha) == 40 and re.fullmatch(r"[0-9a-f]{40}", sha)
+    with pytest.raises(ReportError, match="hex"):
+        render(_valid(error=f"bad ref {sha}"))
+
+
+def test_render_allows_shorter_hex_and_ordinary_text():
+    out = render(_valid(error="ref abc123 not found"))
+    assert "abc123" in out
diff --git a/skills/tests/multiplayer-simulation/test_scaffold.py b/skills/tests/multiplayer-simulation/test_scaffold.py
new file mode 100644
index 0000000..78d352c
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_scaffold.py
@@ -0,0 +1,50 @@
+"""Scaffold sanity: the offline guard is active and the launcher is wired (D2, D9)."""
+
+from __future__ import annotations
+
+import socket
+import stat
+import subprocess
+import sys
+import types
+from pathlib import Path
+
+import pytest
+
+HARNESS = Path(__file__).resolve().parent
+
+
+def test_inet_connect_is_blocked():
+    """O.1/O.3: a connect to 127.0.0.1:9 raises under the autouse fixture."""
+    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
+        with pytest.raises(OSError, match="blocked"):
+            s.connect(("127.0.0.1", 9))
+    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
+        with pytest.raises(OSError, match="blocked"):
+            s.connect_ex(("127.0.0.1", 9))
+
+
+def test_inet6_connect_is_blocked():
+    """AF_INET6 is covered through a stand-in `self`, since some hosts lack IPv6 sockets."""
+    fake = types.SimpleNamespace(family=socket.AF_INET6)
+    with pytest.raises(OSError, match="blocked"):
+        socket.socket.connect(fake, ("::1", 9))
+    with pytest.raises(OSError, match="blocked"):
+        socket.socket.connect_ex(fake, ("::1", 9))
+
+
+def test_launcher_is_executable_and_imports_package():
+    launcher = HARNESS / "bin" / "mpsim"
+    assert launcher.stat().st_mode & stat.S_IXUSR
+    out = subprocess.run(
+        [sys.executable, "-c", "import mpsim, mpsim.errors, mpsim.scenarios"],
+        cwd=HARNESS, capture_output=True, text=True,
+    )
+    assert out.returncode == 0, out.stderr
+
+
+def test_scenario_registry_discovers_nothing_yet_or_sorted():
+    from mpsim.scenarios import scenario_ids
+
+    ids = scenario_ids()
+    assert ids == sorted(ids)
diff --git a/skills/tests/multiplayer-simulation/test_world.py b/skills/tests/multiplayer-simulation/test_world.py
new file mode 100644
index 0000000..f5b74ab
--- /dev/null
+++ b/skills/tests/multiplayer-simulation/test_world.py
@@ -0,0 +1,152 @@
+"""World builder tests (P.1-P.4 at the API level, design D6)."""
+
+from __future__ import annotations
+
+import subprocess
+from pathlib import Path
+
+import pytest
+
+from mpsim.errors import UsageError
+from mpsim.world import World
+
+SEED = {
+    "openspec/specs/sim-notes/spec.md": "# sim-notes\n\n### Requirement: Alpha\n",
+    "roadmap.yaml": "schema_version: 1\n",
+}
+
+
+def _git(cwd: Path, *args: str) -> str:
+    out = subprocess.run(
+        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
+        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
+             "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd)},
+    )
+    return out.stdout.strip()
+
+
+def _build(tmp_path: Path, names=("alice", "bob")) -> World:
+    return World.create(tmp_path / "world", names, seed_files=SEED)
+
+
+def _commit_change(world: World, who: str, change: str, tick: int = 1, push: bool = True):
+    world.add_worktree(who, change, tick)
+    wt = world.worktree_path(who, change)
+    (wt / "openspec" / "changes" / change).mkdir(parents=True)
+    (wt / "openspec" / "changes" / change / "proposal.md").write_text(f"# {change}\n")
+    world.commit(who, change, f"feat: {change}", tick)
+    if push:
+        world.push(who, change)
+
+
+def test_two_principals_have_distinct_identities_clones_worktrees_and_agents(tmp_path):
+    world = _build(tmp_path)
+    _commit_change(world, "alice", "sim-alice-notes")
+    _commit_change(world, "bob", "sim-bob-notes")
+    world.fetch("alice")
+
+    alice, bob = world.principal("alice"), world.principal("bob")
+    assert alice.email == "alice@sim.invalid"
+    assert bob.email == "bob@sim.invalid"
+    assert alice.agent_id != bob.agent_id
+    assert alice.agent_id == "alice-agent-1"
+    assert alice.clone != bob.clone
+    assert world.worktree_path("alice", "sim-alice-notes") != world.worktree_path(
+        "bob", "sim-bob-notes"
+    )
+    # Identity of every commit reachable from the change branch but not from main.
+    a_authors = _git(
+        alice.clone, "log", "--format=%an <%ae>|%cn <%ce>", "origin/main..sim/alice/sim-alice-notes"
+    ).splitlines()
+    assert a_authors == ["alice <alice@sim.invalid>|alice <alice@sim.invalid>"]
+    b_authors = _git(
+        bob.clone, "log", "--format=%an <%ae>", "origin/main..sim/bob/sim-bob-notes"
+    ).splitlines()
+    assert b_authors == ["bob <bob@sim.invalid>"]
+
+
+def test_seed_commit_is_authored_by_sim_seed(tmp_path):
+    world = _build(tmp_path)
+    author = _git(world.principal("alice").clone, "log", "-1", "--format=%an <%ae>", "origin/main")
+    assert author == "sim-seed <sim-seed@sim.invalid>"
+    assert world.remote_url.startswith("file://")
+
+
+def test_unpushed_commit_is_invisible_to_the_other_principal(tmp_path):
+    world = _build(tmp_path)
+    _commit_change(world, "alice", "sim-alice-notes", push=False)
+    sha = _git(world.principal("alice").clone, "rev-parse", "sim/alice/sim-alice-notes")
+    world.fetch("bob")
+    bob_clone = world.principal("bob").clone
+    assert "alice" not in _git(bob_clone, "for-each-ref", "--format=%(refname)")
+    probe = subprocess.run(["git", "cat-file", "-e", sha], cwd=bob_clone, capture_output=True)
+    assert probe.returncode != 0
+
+
+def test_pushed_commit_becomes_visible_after_fetch(tmp_path):
+    world = _build(tmp_path)
+    _commit_change(world, "alice", "sim-alice-notes")
+    world.fetch("bob")
+    refs = _git(world.principal("bob").clone, "for-each-ref", "--format=%(refname)")
+    assert "refs/remotes/origin/sim/alice/sim-alice-notes" in refs
+
+
+def test_three_principals_build(tmp_path):
+    world = _build(tmp_path, names=("alice", "bob", "carol"))
+    principals = [world.principal(n) for n in ("alice", "bob", "carol")]
+    assert len({p.email for p in principals}) == 3
+    assert len({p.clone for p in principals}) == 3
+    assert len({p.agent_id for p in principals}) == 3
+
+
+def test_one_principal_is_a_usage_error_naming_the_minimum(tmp_path):
+    with pytest.raises(UsageError, match="at least 2 principals"):
+        World.create(tmp_path / "world", ("alice",), seed_files=SEED)
+
+
+def test_duplicate_principal_names_are_rejected(tmp_path):
+    with pytest.raises(UsageError):
+        World.create(tmp_path / "world", ("alice", "alice"), seed_files=SEED)
+
+
+def test_commit_dates_derive_from_the_tick_and_ignore_global_config(tmp_path, monkeypatch):
+    gitconfig = tmp_path / "evil.gitconfig"
+    gitconfig.write_text("[user]\n\tname = Mallory\n\temail = m@example.com\n"
+                         "[commit]\n\tgpgsign = true\n")
+    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
+    monkeypatch.setenv("HOME", str(tmp_path))
+    world = _build(tmp_path)
+    _commit_change(world, "alice", "sim-alice-notes", tick=3)
+    clone = world.principal("alice").clone
+    date = _git(clone, "log", "-1", "--format=%aI|%cI|%an", "sim/alice/sim-alice-notes")
+    assert date == "2026-01-01T00:03:00+00:00|2026-01-01T00:03:00+00:00|alice"
+
+
+def test_identical_inputs_in_different_roots_give_identical_commit_ids(tmp_path):
+    w1 = World.create(tmp_path / "one", ("alice", "bob"), seed_files=SEED)
+    w2 = World.create(tmp_path / "two" / "deeper", ("alice", "bob"), seed_files=SEED)
+    for w in (w1, w2):
+        _commit_change(w, "alice", "sim-alice-notes", tick=2)
+    refs = [
+        _git(w.principal("alice").clone, "rev-parse", "sim/alice/sim-alice-notes") for w in (w1, w2)
+    ]
+    assert refs[0] == refs[1]
+
+
+def test_principal_view_is_read_only_and_exposes_worktree_and_remote(tmp_path):
+    world = _build(tmp_path)
+    _commit_change(world, "alice", "sim-alice-notes")
+    view = world.view("alice", "sim-alice-notes")
+    assert view.worktree == world.worktree_path("alice", "sim-alice-notes")
+    assert view.remote_url == world.remote_url
+    assert view.principal == "alice"
+    assert view.read_text("openspec/changes/sim-alice-notes/proposal.md") == "# sim-alice-notes\n"
+    assert not hasattr(view, "push") and not hasattr(view, "commit")
+    with pytest.raises(AttributeError):
+        view.worktree = Path("/elsewhere")  # frozen
+
+
+def test_read_ref_returns_file_content_from_the_fetched_remote_main(tmp_path):
+    world = _build(tmp_path)
+    world.fetch("bob")
+    assert world.read_ref("bob", "origin/main", "roadmap.yaml") == SEED["roadmap.yaml"]
```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- .github/workflows/ci.yml
- openspec/changes/multiplayer-simulation-harness/design.md
- openspec/changes/multiplayer-simulation-harness/loop-state.json
- openspec/changes/multiplayer-simulation-harness/session-log.md
- openspec/changes/multiplayer-simulation-harness/tasks.md
- openspec/contracts/README.md
- openspec/contracts/multiplayer-simulation/cli/mpsim.yaml
- openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json
- skills/pyproject.toml

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `skills/*/scripts/*.py`)
Applies to:
- skills/autopilot/scripts/convergence_loop.py

Check for unhandled exceptions on the failure paths this module is meant to guard (network, subprocess, file I/O). Verify a function documented as "never raises" actually catches every exception class it claims to. Flag silent behavior changes to existing callers.

#### Group 3 (default: `skills/tests/**`)
Applies to:
- skills/tests/autopilot/test_convergence_loop.py
- skills/tests/multiplayer-simulation/README.md
- skills/tests/multiplayer-simulation/bin/mpsim
- skills/tests/multiplayer-simulation/conftest.py
- skills/tests/multiplayer-simulation/evaluation/descriptor.yaml
- skills/tests/multiplayer-simulation/evaluation/scenarios/blocked.yaml
- skills/tests/multiplayer-simulation/evaluation/scenarios/collision.yaml
- skills/tests/multiplayer-simulation/evaluation/scenarios/usage.yaml
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/different-requirement-control/seed/openspec/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/proposal.md
- skills/tests/multiplayer-simulation/fixtures/independent-principals-control/seed/roadmap.yaml
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/retrieval-owner/plan/openspec/changes/sim-retrieval-api/proposal.md
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/principals/storage-owner/plan/openspec/changes/sim-memory-store-core/proposal.md
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/proposal.md
- skills/tests/multiplayer-simulation/fixtures/memory-store-blocked-dependency/seed/roadmap.yaml
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/alice/plan/openspec/changes/sim-alice-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/proposal.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/scenario.yaml
- skills/tests/multiplayer-simulation/fixtures/same-requirement-collision/seed/openspec/specs/sim-notes/spec.md
- skills/tests/multiplayer-simulation/mpsim/__init__.py
- skills/tests/multiplayer-simulation/mpsim/__main__.py
- skills/tests/multiplayer-simulation/mpsim/agents.py
- skills/tests/multiplayer-simulation/mpsim/applier.py
- skills/tests/multiplayer-simulation/mpsim/clock.py
- skills/tests/multiplayer-simulation/mpsim/errors.py
- skills/tests/multiplayer-simulation/mpsim/fixture.py
- skills/tests/multiplayer-simulation/mpsim/model.py
- skills/tests/multiplayer-simulation/mpsim/oracle.py
- skills/tests/multiplayer-simulation/mpsim/paths.py
- skills/tests/multiplayer-simulation/mpsim/probes/__init__.py
- skills/tests/multiplayer-simulation/mpsim/report.py
- skills/tests/multiplayer-simulation/mpsim/runner.py
- skills/tests/multiplayer-simulation/mpsim/scenarios/__init__.py
- skills/tests/multiplayer-simulation/mpsim/scenarios/blocked.py
- skills/tests/multiplayer-simulation/mpsim/scenarios/collision.py
- skills/tests/multiplayer-simulation/mpsim/world.py
- skills/tests/multiplayer-simulation/test_agents.py
- skills/tests/multiplayer-simulation/test_archive_stability.py
- skills/tests/multiplayer-simulation/test_blocked_scenarios.py
- skills/tests/multiplayer-simulation/test_cli.py
- skills/tests/multiplayer-simulation/test_collision_scenarios.py
- skills/tests/multiplayer-simulation/test_contracts.py
- skills/tests/multiplayer-simulation/test_descriptor_drift.py
- skills/tests/multiplayer-simulation/test_gen_eval_pack.py
- skills/tests/multiplayer-simulation/test_oracle.py
- skills/tests/multiplayer-simulation/test_probes.py
- skills/tests/multiplayer-simulation/test_report.py
- skills/tests/multiplayer-simulation/test_scaffold.py
- skills/tests/multiplayer-simulation/test_world.py

Same standard as scripts/tests/: verify the test would fail if the behavior it targets were broken. Check that fixture paths use openspec_paths.change_dir rather than a literal openspec/changes/<id>/ path where the guide requires it.

### Spec excerpts
#### specs/multiplayer-simulation/spec.md
## ADDED Requirements

### Requirement: Simulated Principals Have Separate Identities, Worktrees, And Agents

The simulation harness SHALL build a world containing one local bare git repository as the
shared remote and two or more simulated principals. Each principal SHALL have a distinct git
author identity (name and an `@sim.invalid` email), its own clone of the shared remote, its
own git worktree per simulated change, and its own scripted agent with a distinct agent id.
A principal SHALL observe another principal's work only through commits pushed to the shared
remote.

#### Scenario: Two principals act under separate identities and worktrees

- **WHEN** a scenario with principals `alice` and `bob` runs and each principal's agent
  commits one simulated change
- **THEN** every commit reachable from `alice`'s change branch but not from `main` has
  author `alice <alice@sim.invalid>`
- **AND** every commit reachable from `bob`'s change branch but not from `main` has author
  `bob <bob@sim.invalid>`
- **AND** the two principals' worktree paths are different directories
- **AND** the report's `principals` array lists both principals with distinct `agent_id`
  values

#### Scenario: Unpushed work is invisible to other principals

- **WHEN** `alice` commits a change in her worktree without pushing it
- **AND** `bob` fetches from the shared remote
- **THEN** `bob`'s clone contains no ref or commit from `alice`'s unpushed change

#### Scenario: A world with three principals is supported

- **WHEN** a test builds a world with three principals
- **THEN** three distinct identities, clones and agent ids are created, and the world builds
  without error

#### Scenario: Fewer than two principals is rejected

- **WHEN** `mpsim run` is invoked with `--fixture-dir` pointing at a fixture that declares
  one principal
- **THEN** the process exits with code 64
- **AND** stderr names the minimum of two principals

### Requirement: Same-Requirement Collision Scenario Records Plan-Time Detection

The harness SHALL provide a scenario `same-requirement-collision`. In it, one principal pushes
a simulated OpenSpec change whose spec delta modifies requirement R of a seeded capability.
A second principal then plans a simulated change whose spec delta modifies the same
requirement R. At the second principal's plan step the harness SHALL record:

- `collision_present`: computed by a ground-truth oracle from fixture contents;
- `collision_detected`: true only when a registered collision probe reported a
  requirement-level collision against the first principal's change;
- `probes`: one entry per collision probe that ran.

The scenario SHALL pin the baseline in force at the time of this change: `collision_present`
is `true`, `collision_detected` is `false`, and `probes` is empty. A companion control scenario
`different-requirement-control` SHALL have the two principals modify different requirements.

#### Scenario: Baseline collision is present but not detected

- **WHEN** `mpsim run --scenario same-requirement-collision` runs with no collision probe
  registered
- **THEN** the process exits 0
- **AND** the report has `collision_present: true`, `collision_detected: false`, and
  `probes: []`

#### Scenario: Different requirements produce no collision

- **WHEN** `mpsim run --scenario different-requirement-control` runs
- **THEN** the process exits 0
- **AND** the report has `collision_present: false` and `collision_detected: false`

#### Scenario: A fixture that loses the shared requirement fails loudly

- **WHEN** `mpsim run --scenario same-requirement-collision` is invoked with `--fixture-dir`
  pointing at a copy of its fixture altered so the two spec deltas no longer name the same
  requirement heading
- **THEN** the process exits 1
- **AND** the report's `error` field states that the scenario's required collision is
  absent from the fixture

### Requirement: Plan-Time Detectors Attach Through A Probe Seam

The harness SHALL invoke plan-time collision detectors only through a `CollisionProbe`
interface. That interface SHALL consist of a `probe_id`, and a `detect` operation that
receives a read-only view of the planning principal's worktree and the shared remote URL and
returns a result with `status` (`ok` or `error`), `collisions` (each with `level`,
`other_change` and `requirement`), and an optional `error` message. Registering a new probe
SHALL NOT require editing any scenario definition other than its pinned expectations. A probe
that raises an exception or exceeds its timeout SHALL be recorded with `status: error`, and
the scenario SHALL still complete.

#### Scenario: A registered probe that reports a collision flips detection

- **WHEN** a test registers a stub probe that reports one requirement-level collision
  against the first principal's change
- **AND** runs the `same-requirement-collision` scenario
- **THEN** the report has `collision_detected: true`
- **AND** `probes` contains one entry with the stub's `probe_id` and `status: ok`

#### Scenario: A failing probe is recorded and does not abort the run

- **WHEN** a test registers a probe whose `detect` raises an exception
- **AND** runs the `same-requirement-collision` scenario
- **THEN** the process exits 0
- **AND** `probes` contains that probe with `status: error` and a non-empty `error`
- **AND** `collision_detected` is `false`

#### Scenario: A probe that exceeds its timeout is recorded as an error

- **WHEN** a test registers a probe whose `detect` does not return within the per-probe
  timeout
- **THEN** the run completes, and that probe is recorded with `status: error` and an `error`
  that names the timeout

#### Scenario: Registering a probe edits no scenario definition

- **WHEN** a test registers a new stub probe through the registry
- **AND** runs every built-in scenario
- **THEN** no file under `mpsim/scenarios/` or `evaluation/scenarios/` was modified
- **AND** the stub's `probe_id` appears in `probes` of both collision scenarios

#### Scenario: Probe selection rejects unknown probe ids

- **WHEN** `mpsim run --scenario same-requirement-collision --probe does-not-exist` is invoked
- **THEN** the process exits 64
- **AND** stderr names the unknown probe id

### Requirement: Memory-Store Scenario Reports Time Blocked On Dependency

The harness SHALL provide a scenario `memory-store-blocked-dependency` that reproduces the
dependency half of the motivating memory-store incident. Principal `retrieval-owner` owns a
roadmap item that depends on an item owned by principal `storage-owner`. The scenario SHALL
advance a logical tick clock using step durations declared in the fixture. On each tick it
SHALL decide whether the dependent item is ready by calling the roadmap-runtime admission
rule (`Roadmap.ready_items`) on the `roadmap.yaml` at the shared remote's `main`, the
integration ref. The harness SHALL NOT use readiness logic of its own. Simulated principals
SHALL NOT edit `roadmap.yaml` on their change branches and SHALL NOT push to `main`; every
roadmap status change SHALL be committed to `main` by a simulated supervisor step (the status
applier) authored as `sim-supervisor`. Every status change SHALL be declared as data in the
fixture's step script, never in harness code. Within a tick, the status changes of steps
finishing at that tick SHALL be committed to `main` before any waiting principal evaluates
readiness. For each principal, the report SHALL
include `blocked_ticks`, defined as the first tick at which its implement step is admitted
minus the tick at which its own preceding steps finished, and `unblocked` (boolean). The
scenario SHALL pin the baseline in force at the time of this change:
`blocked_ticks.retrieval-owner` equals 10 and `blocked_ticks.storage-owner` equals 0, under
the fixture durations recorded in design D5. A companion control scenario
`independent-principals-control` SHALL have no dependency between the principals.

#### Scenario: Baseline dependent principal is blocked until the dependency is implemented

- **WHEN** `mpsim run --scenario memory-store-blocked-dependency` runs
- **THEN** the process exits 0
- **AND** the report has `blocked_ticks` of `{"retrieval-owner": 10, "storage-owner": 0}`
  and `unblocked` of `true` for both principals

#### Scenario: Independent principals are never blocked

- **WHEN** `mpsim run --scenario independent-principals-control` runs
- **THEN** every principal's `blocked_ticks` is 0

#### Scenario: A dependency that never completes is bounded by the tick budget

- **WHEN** the scenario runs with `--tick-budget 5`, which is lower than the dependency's
  completion tick
- **THEN** the process exits 0
- **AND** the report has `final_tick` equal to 5, `unblocked.retrieval-owner` equal to
  `false`, and
  `blocked_ticks.retrieval-owner` equal to 4 (the budget minus its earliest start tick)

#### Scenario: Status transitions reach only the integration ref

- **WHEN** `mpsim run --scenario memory-store-blocked-dependency` completes
- **THEN** no commit reachable from any `sim/*` branch but not from the seed commit modifies
  `roadmap.yaml`
- **AND** every commit on `main` after the seed is authored by `sim-supervisor`
- **AND** `roadmap.yaml` at `main` shows both items with status `completed`

#### Scenario: Status transitions are declared only in fixture data

- **WHEN** the harness driver package `mpsim/` is scanned statically
- **THEN** no module contains a roadmap status literal (`approved`, `in_progress`,
  `completed`) used as a `set_status` value
- **AND** running the scenario with a `--fixture-dir` copy whose implement step declares no
  `on_finish.set_status` leaves `unblocked.retrieval-owner` equal to `false`

#### Scenario: Readiness comes from the admission rule, not the harness

- **WHEN** the scenario is run with `--fixture-dir` pointing at a copy of its fixture whose
  roadmap gives the dependency item status `completed` at tick 0
- **THEN** `blocked_ticks.retrieval-owner` is 0, because `Roadmap.ready_items` admits the
  dependent as soon as its own plan step finishes

### Requirement: Scenarios Run Offline Without A Shared Coordinator

Every harness scenario SHALL complete with no network access and no coordinator. The shared
remote SHALL be a local `file://` bare repository. The harness SHALL NOT import
agent-coordinator or coordination-bridge modules, SHALL NOT use HTTP or MCP transports, and
SHALL produce the same report whether or not coordinator environment variables are set. The
harness test suite SHALL run in the skills CI sweep with no services started.

#### Scenario: Scenarios pass with network sockets blocked

- **WHEN** the harness test suite runs with `AF_INET` and `AF_INET6` socket connections
  patched to raise
- **THEN** every scenario test passes

#### Scenario: The driver imports no coordinator or transport modules

- **WHEN** every module under `mpsim/` is parsed with `ast`
- **THEN** none imports a module from `agent-coordinator`, `coordination_bridge`, an HTTP
  client (`httpx`, `requests`, `urllib.request`, `http.client`) or an MCP client

#### Scenario: Coordinator environment variables do not change the outcome

- **WHEN** `mpsim run` is executed for every scenario once with `COORDINATION_API_URL`
  unset, and once with it set to `http://127.0.0.1:9`
- **THEN** each scenario's two stdout payloads are byte-identical

#### Scenario: The harness test directory is reached by CI

- **WHEN** the CI coverage guard `skills/tests/ci_coverage/test_ci_test_coverage.py` runs
- **THEN** it passes with `tests/multiplayer-simulation` listed in the in-skill sweep of
  `.github/workflows/ci.yml`

### Requirement: Scenario Reports Are Deterministic

The harness SHALL emit each scenario report as a single JSON object on stdout that validates
against `openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json`. The JSON
SHALL be serialized with sorted keys. Fields that do not apply to a scenario SHALL be present
with value `null`. Reports 

[spec excerpt truncated]


### Open ledger items
- [5] Re-verification of open ledger item 5: still present. The change-local header keeps the in-flight provenance note and a relative schema path that resolves correctly only from `openspec/changes/<id>/contracts/cli/`; from the promoted location `openspec/contracts/multiplayer-simulation/cli/` four `..` segments leave the repository. Task 1.1 still requires the promoted copy to be byte-identical, so the stale comment ships in the canonical file. Replace the relative path with a repo-root-relative one (`openspec/contracts/gen-eval-framework/schemas/cli-contract.schema.json`) and reword the provenance note so it is true at both locations.
- [6] Interpreter selection for the two subprocess entry points is unspecified. `bin/mpsim` "runs `python -m mpsim`"; `mpsim` imports `skills/roadmap-runtime/scripts` (needs pyyaml/jsonschema from the skills venv). Task 7.3 prepends only `bin/` to PATH and runs the `gen-eval` console script by name, so both resolutions depend on the skills venv already being first on PATH. Under `uv run --project skills pytest` that holds, but a developer running `pytest` from an activated other venv, or an IDE runner, gets a confusing ImportError or a `gen-eval: command not found`.
- [10] The probe invocation point is stated two different ways. D4 says the driver calls every registered probe "at each principal's plan step" (which would include Alice's plan step and the plan steps of both memory-store principals), while the Same-Requirement requirement says probes are run and recorded "at the second principal's plan step". The difference is observable: under D4's wording a single stub probe would produce two `probes` entries in `same-requirement-collision` (one per principal's plan step), contradicting S.1's pin of "one entry with the stub's probe_id", and the blocked scenarios would carry non-null `probes`/`collision_detected`, contradicting D8's "fields that do not apply are null" and S.5's "appears in probes of both collision scenarios" (implying not in the other two). State in D4 and task 4.4 that probes run only at the planning (second) principal's plan step in the collision scenarios, and that the blocked scenarios report `probes: null`.
- [11] D5 does not say whether the implement step of a principal with no dependency is also admitted through `Roadmap.ready_items()` or by harness logic. The sentence "A principal with no dependency is ready at earliest_start_tick" reads as a harness-local rule, which the Memory-Store requirement forbids ("SHALL NOT use readiness logic of its own"). The choice matters for B.4: that fixture seeds the dependency item (`ri-storage`) as `completed` at tick 0, and D5 states `ready_items()` admits only items whose status is `approved`. If every principal's implement step goes through `ready_items()`, storage-owner is never admitted in B.4 (its item is `completed`, not `approved`), so it finishes with `unblocked: false` and `blocked_ticks: 47` at the default budget, and the applier would also write `in_progress` over a `completed` item if it were admitted. B.4 and task 5.1 pin only retrieval-owner's value, so the storage-owner side of that report is unspecified and a reviewer of the pinned gen-eval YAML cannot tell which outcome is intended. Decide (recommended: every principal's implement admission goes through `ready_items()`, no exception) and pin storage-owner's expected `unblocked`/`blocked_ticks` in B.4, or make the B.4 fixture remove storage-owner's implement step.
- [12] D7 declares the `Agent.act` protocol as returning `None`, but three lines later `ScriptedAgent` must "return the step's declared status transitions to the scheduler", and task 2.3 tests that it "returns the step's declared status transitions". Under operator decision A1 the return value is the only channel from agent to applier, so the protocol signature should return the transitions (for example a `StepResult` with `set_status: str | None`), not `None`.
- [13] After the A1 fix, D5 introduces `mpsim/applier.py` (the status applier) and task 5.2 implements it, but D2's package inventory was not updated and still omits it. D6 also gives clones only to principals; nothing says where the applier's checkout of `main` lives (its own clone under `<world>/supervisor/`, or a worktree of the remote), nor that its commits use the same tick-derived fixed dates and `GIT_CONFIG_GLOBAL=/dev/null` rules as principal commits, which D.1 byte-identity depends on. Add `applier.py` to D2 and state the applier's working copy and determinism rules in D5 or D6.
- [14] D5 says the ri-11 flip is "three fixture edits plus one expectation edit" and then lists three numbered items, of which only two are fixture edits and the third is the expectation edit. plan-findings iteration 2 describes it as "three fixture edits plus a rule change". Make the count match the list (two fixture edits, one expectation edit, plus ri-11's own rule and schema change).
- [15] Group 2 check on the Deterministic requirement: the SHALL clauses "serialized with sorted keys" and "fields that do not apply SHALL be present with value null" have no WHEN/THEN scenario. D.1 (byte-identical reruns) does not prove key ordering, and D.2 (schema validation) does not prove null-presence because the schema's `required` list would be satisfied by either null or a value. Task 2.5 does test both, so the gap is in the spec only; add a scenario (for example: WHEN any scenario report is parsed THEN its top-level keys are in sorted order AND every schema property is present, with null for inapplicable fields) and trace it to task 2.5. Every other SHALL in the delta has at least one scenario; no MODIFIED requirements exist, so nothing was dropped.
- [16] Re-verification of open ledger item 6: still unaddressed. Task 1.4's `bin/mpsim` runs a bare `python`, and task 7.3 invokes the `gen-eval` console script by name with only `bin/` prepended to PATH, so both depend on the skills venv already being first on PATH. Cheapest fix: have `bin/mpsim` use `#!/usr/bin/env python3` and have the subprocess tests (6.1, 7.3) pass `sys.executable` explicitly (`[sys.executable, '-m', 'mpsim', ...]` and `[sys.executable, '-m', 'gen_eval', ...]` if gen-eval exposes a module entry point), with `bin/` on PATH only for gen-eval's own invocation of `mpsim`. Record the choice in D3 and the README task 8.2.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.