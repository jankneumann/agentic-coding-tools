# Tasks — rescope-context-drift-enforcement

Phases follow the migration order in `design.md`: base resolution, then attribution, then
exit codes, then the servo. Each phase is observable before the next enforces on it.

## 1. Pin what the base ref means

- [x] 1.1 Write a test that the resolved base revision appears in the report — **S**
  **Spec scenarios**: Resolved base is recorded
  **Design decisions**: D1
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] 1.2 Write a test that the remote ref wins over a stale local ref — **S**
  **Spec scenarios**: Gate reproduces across environments in both directions
  **Design decisions**: D1
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None
  Build a repo whose local base branch is behind `origin/<base>`, assert the gate resolves
  to the remote revision.

- [x] 1.3 Write a test that one tree yields one verdict across checkout shapes — **M**
  **Spec scenarios**: Gate reproduces across environments in both directions
  **Design decisions**: D1
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None
  A fresh clone with no local base branch, and a checkout whose local base branch trails its
  remote, must agree on outcome and exit code. This is the regression pin for the verified
  CI-green/local-red split.

- [x] Checkpoint: run the gate suite, confirm the three new tests fail for the right reason

- [x] 1.4 Resolve the base name to exactly one revision — **S**
  **Design decisions**: D1
  **Files**: `skills/project-context-refresh/scripts/gate.py`
  **Dependencies**: 1.2, 1.3

- [x] 1.5 Use the resolved revision for the changed-file diff — **S**
  **Design decisions**: D1
  **Files**: `skills/project-context-refresh/scripts/gate.py`
  **Dependencies**: 1.4
  `_default_changed_files` (`gate.py:359`) currently diffs the raw base name while
  `describe_tree` (`gate.py:735`) uses `origin/<base>`. Both consume the resolved revision.

- [x] 1.6 Record the resolved revision in the report — **S**
  **Spec scenarios**: Resolved base is recorded
  **Files**: `skills/project-context-refresh/scripts/gate.py`
  **Dependencies**: 1.1, 1.4

- [x] Checkpoint: confirm the resolved revision appears in the report before touching the schema

- [x] 1.7 Publish the report schema addition for the resolved base — **S**
  **Contracts**: `contracts/context-drift-gate.schema.json`
  **Files**: `openspec/schemas/context-drift-gate.schema.json`, `openspec/contracts/project-context-refresh/schemas/context-drift-gate.schema.json`
  **Dependencies**: 1.6

- [x] 1.8 Correct the stale `--base` help text — **XS**
  **Files**: `skills/project-context-refresh/scripts/cli.py`
  **Dependencies**: 1.5
  `cli.py:372-379` claims `--base` is "used only to scope work-package context-impact
  validation"; `run_gate:575` has used it for `describe_tree` unconditionally since before
  this change.

- [x] Checkpoint: run the gate suite green, review the diff, confirm only gate.py and cli.py changed

## 2. Classify drift as inherited or introduced

- [x] 2.1 Write a test that base-present drift is attributed inherited — **S**
  **Spec scenarios**: Inherited drift names the integration branch as owner
  **Design decisions**: D2, D3
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] 2.2 Write a test that branch-caused drift is attributed introduced — **S**
  **Spec scenarios**: Introduced drift is attributed to the branch
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] 2.3 Write a test that indeterminate attribution resolves to inherited — **XS**
  **Spec scenarios**: Ambiguous attribution errs toward inherited
  **Design decisions**: D2
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] Checkpoint: confirm the attribution tests fail, and that no existing test broke

- [x] 2.4 Add a merge-base resolver for the gate — **S**
  **Design decisions**: D2
  **Files**: `skills/project-context-refresh/scripts/gate.py`
  **Dependencies**: 2.1, 1.4
  `checkpoint.py:385` already resolves merge bases; reuse its shape rather than a new idiom.

- [x] 2.5 Attribute findings by path-level ancestry — **M**
  **Spec scenarios**: Inherited drift names the integration branch as owner, Introduced drift is attributed to the branch
  **Design decisions**: D2
  **Files**: `skills/project-context-refresh/scripts/gate.py`
  **Dependencies**: 2.2, 2.3, 2.4
  `git diff --name-only <provenance.source_revision>..<merge_base> -- <input_roots>`.

- [x] 2.6 Annotate each reported finding with its attribution — **S**
  **Files**: `skills/project-context-refresh/scripts/gate.py`
  **Dependencies**: 2.5

- [x] 2.7 Publish the report schema addition for attribution — **S**
  **Contracts**: `contracts/context-drift-gate.schema.json`
  **Files**: `openspec/schemas/context-drift-gate.schema.json`, `openspec/contracts/project-context-refresh/schemas/context-drift-gate.schema.json`
  **Dependencies**: 2.6

- [x] 2.8 Confirm classify_degradation stayed pure — **XS**
  **Design decisions**: D3
  **Files**: `skills/tests/project-context-refresh/test_classify_degradation.py`
  **Dependencies**: 2.5
  `TestPurity` asserts no IO by patching, and `:235` hard-pins the informational set.
  Attribution must live outside that function. Verification only; no production change.

- [x] Checkpoint: run gate plus classify_degradation suites, review the diff, confirm scope

## 3. Make the blocking verdict event-aware

- [x] 3.1 Write a test that inherited-only drift passes a pull request — **S**
  **Spec scenarios**: Inherited drift alone does not fail a pull request
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] 3.2 Write a test that introduced drift fails a pull request — **S**
  **Spec scenarios**: Introduced drift fails a pull request
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] 3.3 Write a test that inherited drift blocks on the integration branch — **S**
  **Spec scenarios**: Inherited drift blocks on the integration branch
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] Checkpoint: confirm the three exit-code tests fail, and existing exit-code tests still pass

- [x] 3.4 Accept the triggering event as gate input — **S**
  **Design decisions**: D4
  **Files**: `skills/project-context-refresh/scripts/gate.py`, `skills/project-context-refresh/scripts/cli.py`
  **Dependencies**: 3.1

- [x] 3.5 Derive exit codes from the attribution-by-event matrix — **S**
  **Spec scenarios**: Inherited drift alone does not fail a pull request, Introduced drift fails a pull request, Inherited drift blocks on the integration branch
  **Files**: `skills/project-context-refresh/scripts/gate.py`
  **Dependencies**: 3.2, 3.3, 3.4, 2.6

- [x] 3.6 Write a test that an unhandled event fails — **XS**
  **Spec scenarios**: Unknown event fails loudly
  **Design decisions**: D4
  **Files**: `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: None

- [x] 3.7 Dispatch on the event inside the gate job — **M**
  **Spec scenarios**: Gate runs on every declared event, Unknown event fails loudly
  **Design decisions**: D4
  **Files**: `.github/workflows/ci.yml`
  **Dependencies**: 3.5, 3.6
  Follow `requirement-traceability-sweep` (`ci.yml:626`, dispatch `ci.yml:737-798`): one job
  on all three events, `case "$EVENT_NAME"`, explicit failing `*)` arm. No job-level `if:`.

- [x] 3.8 Keep the Makefile target reproducing the CI invocation — **S**
  **Files**: `Makefile`, `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: 3.7
  `test_gate.py:824` parses the Makefile to assert the two match; the event argument must
  not break that equivalence.

- [x] Checkpoint: run the full gate suite, review the ci.yml diff against the sweep precedent

## 4. Fix context-impact attribution

- [x] 4.1 Write a test that a co-present work-package file is not blamed — **S**
  **Spec scenarios**: Co-present work-package files are not blamed for unrelated paths
  **Design decisions**: D6
  **Files**: `skills/tests/validate-packages/test_context_impact.py`
  **Dependencies**: None
  Reproduce PR #423: a commit that moves a work-packages.yaml and regenerates unrelated
  decision documents.

- [x] 4.2 Attribute changed paths by declared scope — **M**
  **Spec scenarios**: Co-present work-package files are not blamed for unrelated paths
  **Design decisions**: D6
  **Files**: `skills/validate-packages/scripts/context_impact.py`
  **Dependencies**: 4.1

- [x] Checkpoint: run the validate-packages suite, confirm the compat tests still pass

## 5. Auto-remediate dependency-update pull requests

- [x] 5.1 Write a test that human pull requests are never written to — **S**
  **Spec scenarios**: Human pull request is not written to
  **Design decisions**: D5
  **Files**: `skills/tests/project-context-refresh/test_remediation_policy.py`
  **Dependencies**: None

- [x] 5.2 Write a test that write permission is job-scoped — **XS**
  **Spec scenarios**: Write permission is scoped to the remediation job
  **Design decisions**: D5
  **Files**: `skills/tests/project-context-refresh/test_remediation_policy.py`
  **Dependencies**: None
  Static assertion over `.github/workflows/*.yml`: no workflow-level write grant, exactly
  one job declaring one.

- [x] Checkpoint: confirm both policy tests fail, since no remediation job exists yet

- [x] 5.3 Add the dependency-update remediation job — **M**
  **Spec scenarios**: Dependency-update pull request is remediated, Write permission is scoped to the remediation job
  **Design decisions**: D5
  **Files**: `.github/workflows/ci.yml`
  **Dependencies**: 5.1, 5.2, 3.7

- [x] 5.4 Refresh the base before regenerating — **S**
  **Spec scenarios**: Dependency-update pull request is remediated
  **Design decisions**: D5
  **Files**: `.github/workflows/ci.yml`
  **Dependencies**: 5.3
  Artifacts derived from a stale base are themselves drift; `docs/merge-logs/2026-08-24.md:29`
  records replaying the same merge commit as "theatre".

- [x] 5.5 Make the regenerate command identical to the check command — **S**
  **Design decisions**: D5
  **Files**: `.github/workflows/ci.yml`, `Makefile`
  **Dependencies**: 5.4
  Per `generate_tool_descriptor.py:570-573`, differing argv between checker and writer
  reports drift on an up-to-date file forever.

- [x] Checkpoint: run the policy suite green, review the ci.yml permissions diff line by line

  **Note (5.5):** satisfied inside the workflow, not the Makefile. One `run_producer()`
  helper is the only place `cli.py` is invoked for either mode, and `cli.py <mode>
  <producer-id>` takes no other argument — so writer and checker have nothing left to
  disagree about. `Makefile` needed no edit and was not touched.

## 6. Record inherited-versus-introduced evidence

- [x] 6.1 Write a test for the context_gate event shape — **S**
  **Design decisions**: D7
  **Files**: `skills/tests/merge-pull-requests/test_merge_events.py`
  **Dependencies**: None

- [x] Checkpoint: confirm the event shape test fails before the emitter exists

- [x] 6.2 Emit a context_gate event per gate run — **S**
  **Design decisions**: D7
  **Files**: `skills/project-context-refresh/scripts/gate.py`, `skills/merge-pull-requests/scripts/merge_events.py`
  **Dependencies**: 6.1, 2.6

  **Deviation (implemented):** emission is opt-in to a destination outside the
  checkout, not an append to `docs/merge-logs/metrics.jsonl` as proposal section 6
  described. That path is inside the graded tree and would break the ratified
  `Gate leaves the checkout unchanged` scenario. A destination inside the checkout is
  refused. Unset means no record, so today's behaviour is byte-for-byte preserved.

- [x] 6.3 Give the `context_gate` row a destination — **S**
  **Design decisions**: D7
  **Files**: `.github/workflows/ci.yml`, `skills/tests/project-context-refresh/test_gate.py`
  **Dependencies**: 6.2, 3.7
  Added after 6.2 landed: `CONTEXT_GATE_METRICS_PATH` existed only where it was defined, so
  the emitter was correct, tested, and unreachable in every real run. The gate job now sets
  it to `${{ runner.temp }}` — outside the checkout, which `gate.py` refuses to write — and
  uploads the row as a build artifact on all three events.
  **Rejected first (reverted in `2627f7c7`):** emitting from the merge train's `dry_run`.
  It contradicted that function's own contract ("a dry run that dirties main is not a dry
  run") and observed only `main`, never a pull request — the population where the
  inherited-versus-introduced split actually varies.
  **Known limit:** per-run artifacts are not an aggregated trend line. The rows now exist on
  the right population; joining them is separate work with no wiring in place.

## 7. Close the promotion gap

- [x] 7.1 Rewrite both promotion notes together — **S**
  **Design decisions**: D8
  **Files**: `docs/guides/session-completion.md`
  **Dependencies**: 3.7
  Replace the known-gap section with an applied record, and update the coverage-ratchet
  note's back-reference in the same edit so the adjacency claim in
  `specs/fitness-functions/spec.md:115-116` stays true.
  **Deviation (implemented):** an *applied* record would be false — the promotion is
  not applied and a pull request cannot apply it. The section was retitled to a
  pending promotion, `Status: NOT APPLIED` was kept, and what the rewrite records is
  the removed blocker plus the outstanding owner action (tasks 7.2, 7.3).

- [x] Checkpoint: confirm the guide reads coherently and no back-reference dangles

## 8. Integration

- [x] 8.1 Re-sync the skill mirrors — **XS**
  **Files**: `.claude/skills/**`, `.agents/skills/**`
  **Dependencies**: 6.2, 4.2
  `gate-drift-with-mirrors-hooks-and-blocking-ci` will fail CI on mirror drift.
  **Correction:** it does not. `.claude/skills/` and `.agents/skills/` are gitignored
  (`.gitignore:277`), so mirror drift can never reach a diff, and `ci.yml:197` states
  outright that the drift gate is not about mirror drift. The only CI check is
  `install.sh --check`, which validates install *portability* — it passed while all six
  mirrors still held the pre-change `gate.py`. The re-sync was run (`skills/install.sh`,
  not a repo-root `install.sh` as the verification step names) and produced no tracked
  change. Real local hygiene, no CI signal, no committable evidence.

- [x] 8.2 Confirm the edited modules are ruff-clean — **XS**
  **Files**: (verification only)
  **Dependencies**: 8.1
  `add-skills-lint-ci-gate` made `ruff` blocking over `skills/` at pinned 0.16.0 rules.

- [x] 8.3 Verify one verdict across checkout shapes end to end — **S**
  **Spec scenarios**: Gate reproduces across environments in both directions
  **Files**: (verification only)
  **Dependencies**: 8.2
  Clone the branch fresh, run `make context-drift-gate`, compare against the same command in
  a checkout whose local base branch trails its remote. Both must agree.
  **Result:** both agree. A fresh clone with no local `main`, and a clone whose local
  `main` trailed `origin/main` by five commits, each exited **0** with `outcome: fresh`
  and each recorded `base_resolved_revision: 244442bc`, `base_resolved_from: remote`.
  The stale local ref lost to the remote, on the exact shape that produced the verified
  CI-green/local-red split.

- [x] Checkpoint: full suite, `openspec validate --strict`, review the cumulative diff
  1,149 tests green across seven suites (project-context-refresh 453, validate-packages 151,
  merge-pull-requests 192 + 170, project-context-runtime 94, install_sh 28, validate-feature
  61+5s). `openspec validate --strict` valid. ruff 0.16.0 clean over every edited tree.
