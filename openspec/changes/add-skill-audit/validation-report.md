# Validation Report: add-skill-audit

**Date**: 2026-09-16 11:46:12
**Commit**: 410fe7deff87f8e67503a91cd553ccda208b2792
**Validated tree**: 82f17a1f4d019f5204e96cc74e1d0040e94882f1
**Branch**: claude/skills-modern-models-design-rwjlym
**Phases requested**: `--phase spec,evidence`

## Phase Results

✓ Spec Compliance: 9/9 requirements verified against the live system
✓ Evidence: work packages consistent; no work-queue results emitted (see below)
○ Deploy: skipped (not requested)
○ Smoke Tests: skipped (not requested)
○ Security: skipped (not requested)
○ E2E Tests: skipped (not requested)
○ Gen-Eval: skipped (not requested)
○ Architecture: skipped (not requested); artifacts are known stale, refresh pipeline errors
○ Log Analysis: skipped (Deploy did not run)
○ CI/CD: skipped (no PR open for this branch)
○ Choices: no ledger

## Deployable surface

`gate_logic.py --describe-surface` over the 91 changed paths classifies this
change **deployable** (`source: derived`, "changed paths include a deployable
service") because it edits `agent-coordinator/src/agents_config.py` and
`coordination_api.py`. Smoke, Security, and E2E are therefore **required**
phases that were **skipped by request**, not "not applicable". The pre-merge
gate will block until they run.

## Spec Compliance

**Status**: pass

Critical sub-gates:

| Sub-gate | Result | Detail |
|---|---|---|
| 7.0 Task checkbox drift | pass | 0 unchecked boxes across 23 tasks and 8 checkpoints |
| 7.0b Requirement-to-contract traceability | pass | exit 0; 69 operations cite 37 requirements; no violation names this change's capabilities |

The traceability gate needed `--base-ref origin/main`. Local `main` in this
cloud clone is stale and divergent (85 commits not on `origin/main`), so the
default base cannot resolve a merge base. This is clone state, not a defect in
the change.

`change-context.md` is filled through Phase 3: Files Changed populated for all
nine rows, Evidence `pass 8ee790a` for all nine, Coverage Summary updated. It was
left at Phase 1 when this report was first written, which is a gap in the earlier
run of this phase, not a new finding.

Per-requirement verification, all against the live system at this commit:

| Req ID | How verified | Evidence |
|---|---|---|
| skill-workflow.1 | Ran the CLI on `quick-task`; ledger carries layers, dispatch profile, findings; report written | pass 410fe7d |
| skill-workflow.2 | Contract-delete guard and repo-token downgrade | pass 410fe7d (9 tests) |
| skill-workflow.3 | Freshness stamp, exit codes, candidate-work stubs | pass 410fe7d (8 tests); 4 live stubs validated against `candidate-work.schema.json` |
| skill-workflow.4 | Report header reads `convention: rightsizing` by default | pass 410fe7d |
| skill-workflow.5 | Ran against a closed port: exit 0, `evidence: unavailable` recorded | pass 410fe7d |
| skill-workflow.6 | SKILL.md 102 lines, one-level references, both frontmatter states; mirrors match | pass 410fe7d (14 tests) |
| agent-archetypes.1 | v3 loads all-guided, v4 accepted, unknown value and unknown key rejected | pass 410fe7d (123 tests) |
| agent-archetypes.2 | Live resolution: INIT verbatim, PLAN goal-directed, IMPLEMENT byte-identical guided, escalation preserves mode, bridge passthrough | pass 410fe7d (29 + 12 tests) |
| harness-engineering.1 | Attribution precedence, unknown bucket, concentration rule, source preservation | pass 410fe7d (12 tests) |

## Evidence

**Status**: pass with findings

- **No `artifacts/<package-id>/work-queue-result.json` exists.** The two
  implementation packages ran as in-session sub-agents rather than coordinator
  work-queue workers, because the coordinator rejects this session's key for
  lock and queue operations. Per-package result schemas could therefore not be
  validated. Package outcomes were verified directly instead: scope audited
  per commit against `write_allow`, and every verification command in
  `work-packages.yaml` re-run by the orchestrator.
- **Contract and plan revision consistency**: single revision 1 throughout; no
  package reported a divergent revision.
- **Cross-package file overlap**: one shared path,
  `openspec/changes/add-skill-audit/tasks.md`, written by all three packages.
  See the finding below.

### Finding E1 — the shared task record cannot satisfy all three rules at once

`implement-feature` step 4 requires each task's checkbox flip to land in the
same commit as its implementation, so every implementing package must write
`tasks.md`. This validation phase permits that shared write only when every
reporting package declares the path in `write_allow`. But
`validate_work_packages.validate_scope_overlap` rejects any `write_allow`
overlap between parallel packages, with a single hardcoded exemption for
`wp-integration` and no mechanism to declare a shared change-local record.

Declaring the path fails the package validator; not declaring it fails this
phase's cross-package check. Both were tried on this change and the failure was
reproduced in each direction. The declaration was reverted to keep the package
validator green, which is also the prevailing repo convention: of the active
changes, only `add-harbor-benchmark-routing` and
`followup-add-prime-agent-harness` declare their task record.

Severity: low for this change, structural for the repo. Filed as a follow-up
rather than fixed here: changing the validator is outside this change's scope.

## Smoke Tests

**Status**: skipped

Not requested (`--phase spec,evidence`). Required for this change because the
surface is deployable; the pre-merge gate will block until this runs.

## Security

**Status**: skipped

Not requested. Required for this change because the surface is deployable.

## E2E Tests

**Status**: skipped

Not requested. Required for this change because the surface is deployable.

## Test evidence at this commit

| Suite | Result |
|---|---|
| `agent-coordinator/tests` (unit) | 2537 passed, 11 skipped |
| `skills/tests/skill-audit` | 86 passed |
| `skills/tests/ci_coverage` | 128 passed |
| `openspec validate --strict` | valid |
| `skills/install.sh --check` | mirrors match canonical payload |
| ruff, coordinator source and new skill | clean |

Whole-suite collection of `skills/tests` reports 36 errors. All 36 are
pre-existing flat module-name collisions (`models`, `runner`) reproduced at
base commit 2726d31; zero are attributable to this change. CI does not surface
them because it runs the skill suites per directory.

## Result

**PASS** for the two requested phases.

**NOT YET MERGEABLE**: Smoke, Security, and E2E are required for this
deployable surface and have not run. Run them with a container runtime
available, then re-check the pre-merge gate.
