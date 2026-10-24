# Design: Reject vacuous worker results in the package executor

> Change ID: `reject-vacuous-worker-results-in-the-package-executor`
> Roadmap item: `ri-04` (`verification-enforcement-discipline`)
> Selected approach: **A — tighten the existing executor, validator and gates**

## Context

Phase B workers build a `work_queue.result` payload with
`PackageExecutor.build_result`. Phase C validates it with
`result_validator.validate_package_result`, which wraps
`validate_work_result.validate_result`, and then feeds two decision points:

- `DAGScheduler.mark_completed`, which unblocks dependants;
- `IntegrationOrchestrator.check_integration_gate`, which allows the merge.

None of the four stages distinguishes "verified" from "claimed". The executor
computes `all([]) == True`. The validator skips its consistency check on empty steps
and never looks at the commit. Both decision points accept a package from its
presence alone.

## Decisions

### D1 — Vacuous truth is removed at the source and at the checker

`build_result` computes `passed = bool(steps) and all(step.passed)`, and
`validate_verification_consistency` reports an error on zero steps. Both changes
are needed:

- the executor fix stops *our* emitter from producing the claim;
- the checker fix stops *any* emitter (another vendor's worker, a hand-written
  result) from getting it through.

The schema already declares `steps.minItems: 1`. The explicit check still matters
because it names the problem ("no verification steps") instead of leaving a generic
schema message, and because it keeps working if a caller validates with a looser
schema.

The checker also rejects three step-level forms of the same lie, each on a step
that claims `passed: true`:

- `method: not_run`;
- an integer `exit_code` other than 0 (the command failed);
- empty evidence: no `artifacts` and no `metrics`. This applies to every step
  kind, including `command` steps, because a pass that leaves no trace is not
  evidence. Any single artifact or metric is enough.

A failing step is not held to these rules, since a failure claims nothing.
`method: inspected` with evidence is still allowed (A2).

### D2 — The commit check binds the head to the package branch, opt-in and enforced at acceptance

`validate_result(data, schema=None, *, worktree_path=None)` adds a
`commit_resolves` check. It keeps that name, but it checks more than resolution.
With `cwd=worktree_path`, and a 10-second timeout per `git` call, it requires all
of these:

1. **The head resolves.** `git rev-parse --verify --quiet <sha>^{commit}`.
   `rev-parse` handles abbreviated SHAs, and an ambiguous prefix fails, which is
   what we want.
2. **The head is on the package branch.** The package branch is
   `refs/heads/<git.head.branch>` when the result reports a branch, and the
   worktree's `HEAD` otherwise. `git merge-base --is-ancestor <head> <branch>`
   must exit 0. Exit 1 means "not reachable", which catches a commit that exists
   only on another branch, and a dangling commit. Any other exit is reported as
   "could not be checked". Either way the check fails.
3. **The head is not the base.** `git.base.ref` must resolve to a commit, and
   that commit must differ from the head. A worker that made no commit reports
   the base as its head, and that is not a pass.

Failures:

- A missing directory, a non-repository, a timeout or a non-zero exit fails the
  check, with an error that names the commit and the path.
- So does a base ref or branch that does not resolve. The check cannot be
  satisfied by leaving its inputs unresolvable.
- A commit that does not match `^[0-9a-fA-F]{7,64}$` fails without invoking `git`.
- So does a branch or base ref that is empty or starts with `-`. The schema
  already constrains these fields, but this check must not depend on the schema
  having run, and `git` would read a value starting with `-` as an option.
- Inherited `GIT_DIR`-style environment variables are stripped, so the check
  inspects the given worktree and not the caller's repository.

The check does not compare `files_modified` with the commit's diff (Non-Goal). It
also accepts a head that is an older ancestor of the base, because it compares
the head only with the base commit itself, as the user decision states.
`git.head.branch` is self-reported. Falling back to the worktree's `HEAD` covers
results that omit it.

Without `worktree_path` the check is recorded as
`{"passed": true, "skipped": true, "errors": [], "reason": "no worktree_path supplied"}`.
A skipped check does not fail `validate_result`, because `validate-feature`'s
evidence phase and other library callers run without a worktree. It is never
reported as a pass, though: `accept_package_result` (D4) treats a skipped commit
check as a refusal. Fail-closed lives at the point where completion is decided.

*Rejected:* deriving the worktree path from `git.head.worktree`. That field is a
name, and the mapping from name to path belongs to `worktree.py`, not to the
validator.

### D3 — `outcome` and `method` are optional fields with a single derivation

Schema additions (both optional, `schema_version` stays 1):

- top level: `outcome: {"enum": ["PASS", "ISSUES", "BLOCKED"]}`
- `VerificationStepResult`: `method: {"enum": ["executed", "ci", "inspected", "not_run"]}`

A single pure function, `validate_work_result.derive_outcome(data)`, is the only
derivation. It gives `BLOCKED` when the status is failed. It gives `PASS` when the
status is completed, the steps are non-empty, every step passed,
`verification.passed` is true, and `scope_check.passed` is not false. Otherwise it gives `ISSUES`.

`effective_outcome(data)` returns `data["outcome"]` when present, otherwise
`derive_outcome(data)`. `build_result`, the consistency checker, the acceptance
function and the execution summary all call these two functions, so the rule
exists in one place.

The consistency check `validate_outcome_consistency`:

- reports `outcome == "PASS"` with `derive_outcome != "PASS"` as an error (an
  upgrade);
- reports `status == "failed"` with an `outcome` present that is not `BLOCKED` as
  an error;
- allows downgrades (A4).

`build_result` gains an optional `outcome` parameter. When it is omitted, the
derived value is emitted. When it is supplied, it is emitted as given, so the
validator, not the builder, decides whether it is consistent. This keeps the
builder honest about what the worker claimed.

`build_failure_result`'s synthetic `aborted` step gains `method: not_run`.

### D4 — `PackageAcceptance` is the only currency that completes a package

A new dependency-free module, `package_acceptance.py`, defines the verdict, and
`result_validator.py` re-exports it:

```python
@dataclass(frozen=True)
class PackageAcceptance:
    package_id: str
    accepted: bool
    outcome: str | None          # effective outcome, None if unreadable
    reasons: tuple[str, ...] = ()
    override: dict[str, str] | None = None   # {"reason", "approver"}

    @classmethod
    def override_for(cls, package_id, reason, approver) -> "PackageAcceptance": ...
```

(The classmethod is `override_for`, not `override`, because a dataclass field and a
classmethod cannot share the name `override`.)

The verdict also carries `result_digest: str | None`. This is
`digest_result(result)`, a SHA-256 of the canonical JSON of the result the
verdict was made from. `accept_package_result` sets it. D5 uses it to bind the
verdict to the result.

`accept_package_result(result_data, package_def, expected_contracts_revision,
expected_plan_revision, worktree_path, schema=None)` runs
`validate_package_result(..., worktree_path=worktree_path)`. It is accepted only
when all of these hold:

- `valid` is true;
- `commit_resolves` is not skipped;
- `effective_outcome == "PASS"`.

Each failed condition contributes one reason string.

`DAGScheduler.mark_completed(package_id, acceptance)` accepts only an
`isinstance(acceptance, PackageAcceptance)` whose `package_id` matches and whose
`accepted` is true. Anything else sets the state to `FAILED`, sets `error` to
`"result not accepted: <reasons>"`, and returns `False`. The caller then decides
whether to retry or to `cancel_dependents`. The existing `FAILED` semantics are
reused, not a new state.

The required parameter is a deliberate signature break (A6). A call without
evidence must not type-check.

`dag_scheduler` imports `PackageAcceptance` from `package_acceptance`, not from
`result_validator`. The scheduler needs only the type for its `isinstance` check,
and importing `result_validator` would pull in `jsonschema` and the validator's
`sys.path` setup. `package_acceptance.py` imports only the standard library.

### D5 — The gate checks acceptance before reviews

In `check_integration_gate` the order is:

1. missing result → `blocked_incomplete` (unchanged);
2. **result present but acceptance missing or not accepted →
   `blocked_not_passing`** (new);
3. missing reviews → `blocked_incomplete`;
4. escalations, then blocking findings, then pass (unchanged).

Acceptance is checked before reviews because reviewing a package that did not pass
wastes a review dispatch, and the failure is more fundamental.

Step 2 also requires the verdict to belong to the recorded result. A verdict with
no override must carry a `result_digest` equal to `digest_result` of the result
recorded with it. Otherwise the reason is "acceptance was not issued for the
recorded result". This covers both a verdict made for a different result and a
verdict that carries no digest. An override carries no digest and is exempt,
because it records a human decision about the package, not about one payload. The
digest compares content, so recording a copy of the accepted result still
passes. Mutating the result after acceptance blocks the gate.

A new `IntegrationGateStatus.BLOCKED_NOT_PASSING = "blocked_not_passing"`. It is
not a reuse of `blocked_incomplete`, so callers and the summary can tell "never
reported" from "reported a failure". Every gate response gains
`not_passing: [{package_id, outcome, reasons}]` (empty when none) and
`overrides: [{package_id, reason, approver}]`.

`get_packages_pending_review` is unchanged. It still lists packages that have a
result, so a failed package can still be reviewed if a caller wants to.

### D6 — Override is a constructor, not a flag

`PackageAcceptance.override_for(package_id, reason, approver)` strips both strings
and raises `ValueError` if either is empty. It returns
`accepted=True, outcome=None, reasons=("override: <reason>",), override={...}`.

Because the override is just an acceptance, every consumer accepts it through the
same code path. Because it carries `override`, every consumer can surface it:

- `PackageStatus` gains `override: dict | None`, which `get_status_summary` reports;
- the gate lists overrides.

There is no boolean that can skip the check silently. `PackageAcceptance` also
enforces this in `__post_init__`:

- `accepted=True` without an override requires `outcome == "PASS"`, and anything
  else raises `ValueError`;
- a directly passed override must have a non-blank reason and approver.

So a hand-built `PackageAcceptance("wp", True, None)` cannot complete a package.

### D7 — Emitter compatibility is pinned by tests, not by convention

New tests in `skills/tests/parallel-infrastructure/test_vacuous_results.py`
validate the following against the schema file in `openspec/schemas/`:

- `build_result` (passing, failing, zero-step);
- `build_failure_result`;
- a legacy fixture with neither new field.

The tests also assert that the two schema copies are byte-identical.

Existing co-located fixtures that encode the vacuous pass are migrated to one
passing step:

- `test_integration_orchestrator._make_result` uses `steps: []` with
  `passed: True`;
- `test_validate_work_result` and `test_result_validator` may carry similar
  fixtures.

Migrating them is the point of the change, not collateral damage.

## Risks

- **Signature break on `mark_completed`.** Its only callers are tests and prose
  (`grep` confirms). The prose in `implement-feature` does not show the
  signature.
- **`git` subprocess in the validator.** The check is bounded by a timeout. It runs
  only when a path is supplied and never touches the network.
- **Concurrent schema edits.** No other active change edits
  `work-queue-result.schema.json`. The roadmap's concurrency note concerns
  `review-findings`.
