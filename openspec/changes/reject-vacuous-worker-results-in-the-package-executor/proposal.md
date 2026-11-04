# Reject vacuous worker results in the package executor

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `reject-vacuous-worker-results-in-the-package-executor`
> Effort: L
> Priority: 1

## Summary

Make the work-queue result contract unable to express a vacuous pass: empty verification steps yield passed false, the reported git.head.commit must resolve in the package worktree, and each result carries a PASS / ISSUES / BLOCKED outcome plus a per-step method. dag_scheduler.mark_completed and the integration gate accept a package only from a validated PASS result.

## Dependencies

- None

## Acceptance Outcomes

- build_result with zero steps produces verification.passed == false, and validate_work_result reports it as an error.
- A result naming a commit absent from the package worktree fails validation.
- The integration gate returns a blocking status, and dag_scheduler does not mark the package completed, when its only result is failed or BLOCKED.
- Every existing emitter still validates against work-queue-result: new schema fields are optional or all emitters are migrated in the same change.

## Rationale

Phase 1: package_executor.py:189 computes all([]) as true, validate_verification_consistency accepts zero steps, and record_package_result counts a failed result as present, so dependants can unblock on work that was never verified.
