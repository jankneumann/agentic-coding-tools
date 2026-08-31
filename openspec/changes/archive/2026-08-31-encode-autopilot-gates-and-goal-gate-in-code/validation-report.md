# Validation Report: encode-autopilot-gates-and-goal-gate-in-code

**Date**: 2026-08-31 17:39:53
**Commit**: 9df61c813e911d58d593b7c89b69184eb66f7d70
**Validated tree**: 4db47cdd1f46a3c4be475ae836638fe755965652
**Branch**: openspec/encode-autopilot-gates-and-goal-gate-in-code
**Phases run**: spec, evidence (`--phase spec,evidence`)

## Deployable Surface

**Not deployable** — declared `deployable: false` in `work-packages.yaml`, and
`gate_logic.py --change-dir` resolves the same: `{"deployable": false, "source":
"declared"}`. This change is Python skill scripts and SKILL.md prose with no
running service, so Deploy, Smoke, Security and E2E are **not applicable** rather
than skipped-and-owed. The required phase set collapses to **Spec Compliance**.

Docker is unavailable on this host, which does not affect the outcome: no required
phase needs it.

## Phase Results

| Phase | Result | Detail |
|---|---|---|
| Deploy | ○ n/a | Non-deployable surface (declared) |
| Smoke | ○ n/a | Non-deployable surface (declared) |
| Gen-Eval | ○ skip | No interface descriptors for this change |
| Security | ○ n/a | Non-deployable surface (declared) |
| E2E | ○ n/a | Non-deployable surface (declared) |
| Architecture | ○ skip | Not requested (`--phase spec,evidence`); context drift gate ran green separately |
| Task-drift gate (7.0) | ✓ pass | 0 unchecked boxes across 8 commits |
| Traceability gate (7.0b) | ✓ pass | exit 0, change-scoped; 68 operations cite 35 requirements; no violation attributable to this change |
| **Spec Compliance** | **✓ pass** | 7/7 requirements verified — see `change-context.md` |
| Evidence | ⚠ pass with note | Work-package schema/DAG/locks valid; context-impact repaired during this run; no per-package result artifacts (see below) |
| Logs | ○ n/a | No services started |
| CI | ✓ pass | PR #441: 18 pass, 0 fail, 1 expected skip |

## Spec Compliance

**Status**: pass

7/7 requirements verified. Each was verified by running its mapped tests against the implemented tree:

| Req ID | Requirement | Tests | Result |
|---|---|---|---|
| skill-workflow.1 | Autopilot Gate Call Sites | test_gate_call_sites.py | 35 passed |
| skill-workflow.2 | Console Interviewer Protocol | test_console_interviewer.py, test_gate_evaluate_cli.py, test_runner_cli.py | 39 passed |
| skill-workflow.3 | Goal Gate at DONE | test_goal_gate.py | 22 passed |
| skill-workflow.4 | Loop State Gate Records | test_loop_state.py, test_apply_outcome_contract.py, test_loopstate_schema.py | 47 passed |
| skill-workflow.5 | Prose-Free Gate Enforcement | test_prose_free_gates.py | 29 passed |
| roadmap-orchestration.1 | Adaptive Roadmap Execution | test_checkpoint_replan.py, test_replan_gate.py | 19 passed |
| roadmap-orchestration.2 | Proposal Decomposition (replan mode) | test_replan_scope.py | 11 passed |

Plus contract schemas (14 passed) and the posture e2e (4 passed). **220 tests total, 0 failures.**

Scenario coverage: the delta carries 35 scenarios — 9 carried forward unchanged from
the canonical specs, **26 new obligations, all 26 with tests**.

## Evidence Phase — note

`work-packages.yaml` validates (schema, depends_on refs, DAG acyclicity, lock-key
canonicalisation). **No per-package `work-queue-result.json` artifacts exist**: the
six packages were dispatched as sub-agents directly rather than through the
coordinator work queue, so the queue's result contract was never the medium. Scope
was verified instead by inspecting `git status` against each package's
`write_allow` before each commit, and every package's verification commands were
run and recorded in its commit message. This is weaker than a schema-validated
result per package and is recorded here rather than papered over.

This phase also caught real drift: `wp-contracts` and `wp-skill-docs` had grown
`.py` test files, implying the `semantic_code` surface neither declared. Both
declarations were corrected during this run; `validate_context_impact --base main`
is now VALID.

## Known Failures Not Attributable to This Change

`test_smoke_local_real_mode_refuses_an_unresolved_archetype` and
`test_smoke_local_real_mode_unreachable_endpoint_refuses_before_dispatch` fail on
this host and on a clean `main` checkout alike. They pass on the CI runner (main is
green with them in its sweep), so they are environment-dependent — issue #440, with
the correction recorded there.

## Result

**PASS** — Ready for `/cleanup-feature encode-autopilot-gates-and-goal-gate-in-code`.

The pre-merge gate agrees when given the change directory so it can read the
deployable declaration:

```
gate_logic.py <report> --change-dir openspec/changes/encode-autopilot-gates-and-goal-gate-in-code
```
