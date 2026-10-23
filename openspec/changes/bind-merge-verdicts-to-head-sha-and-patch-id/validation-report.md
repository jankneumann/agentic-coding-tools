# Validation Report: bind-merge-verdicts-to-head-sha-and-patch-id

## Spec Compliance
**Status**: pass
`openspec validate --strict bind-merge-verdicts-to-head-sha-and-patch-id` is valid, and all tasks in `tasks.md` are checked. Each spec scenario ID cited in `tasks.md` has a test:
- Verdict currency (`verdict-current`, `verdict-rebased`, `verdict-stale`, `verdict-unbound-stale`): `merge-pull-requests/scripts/tests/test_verdict_binding.py`, which uses a real git repository and a real `git patch-id --stable`.
- Independence (`self-review-rejected`, `unknown-author-same-vendor-rejected`, `same-family-recorded`): the same file, plus `tests/merge-pull-requests/test_review_predicate_total.py`.
- Total predicate (`ineligible-without-waiver-blocks`, "Eligible vendor review fails closed"): `test_review_predicate_total.py`.
- Execution (`skip-pr-diff-review-after-iterate`, `cheap-path-merges`, `policy-waiver-recorded`, `merge-push-race-fails`): `merge-pull-requests/scripts/tests/test_execute_plan.py`.
- Operator waiver (`operator-waiver-recorded`, `operator-waiver-empty-rejected`): the CLI tests in `test_execute_plan.py`, plus `test_merge_pr_records_events.py`.
- Head pinning (`merge-pinned`): `test_merge_pr_head_pin.py`.
- Schema 1.2 (`plan-1-1-rejected`): `test_merge_plan_contract.py`.

The end-to-end merge path against GitHub is not exercised: no live PR is merged in tests. `gh` is mocked at the `run_gh_unchecked` and `ExecutionDependencies` seams.

## Evidence
**Status**: pass
All runs below were made from `skills/` with the shared skills venv. Each suite ran as its own pytest invocation, because the suites have a known conftest plugin-name clash when combined.
- `merge-pull-requests/scripts/tests`: 266 passed
- `tests/merge-pull-requests`: 307 passed
- `parallel-infrastructure/scripts/tests`: 543 passed
- `ruff check` (merge-pull-requests scripts, `review_dispatcher.py`, tests): all checks passed
- `git grep -n iterate_consensus_path -- skills/merge-pull-requests skills/tests`: empty (rc=1)
- `bash skills/install.sh --check`: runtime mirrors in sync
- SKILL.md is 1128 lines, unchanged from before

## Deploy
**Status**: skipped
This is a skill library and contract change with no deployable service (the surface is declared non-deployable).

## Smoke
**Status**: skipped
Not applicable, because there is no service.

## Security
**Status**: not applicable
The change narrows the merge path rather than widening it, and adds no network, auth or secret handling. Trailer-derived author identity is documented as advisory provenance, not authentication (see `references/verdict-binding.md`).

## E2E
**Status**: skipped
There is no UI or API surface.

## Gatekeeper
**Status**: degraded
No sub-agent dispatch adapter was available, so the GATEKEEPER risk and verifiability judgment did not run. A signal-only permissive verdict (`proceed_with_review`) stood in for it. This is a gate that could not run, not a gate that passed. Multi-vendor review also ran single-vendor (`claude_code`, min_quorum 1 under the cloud-container policy).

## Overall
**Status**: pass
