# Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

## Pending promotion: `context-drift-gate` is not a required status check

**Status: NOT APPLIED.** The blocker that kept this promotion unapplied is gone; the
promotion itself is still outstanding and still needs a repository admin.

Branch protection on `main` requires exactly six contexts:

```
test  test-infra-skills  test-skills  validate-specs  check-docker-imports  secret-scan
```

The `context-drift-gate` job (`.github/workflows/ci.yml`) is **not** among them.
Adding a seventh context is a repository-settings operation that a pull request
cannot perform, so the job ships as a **blocking job, not a required context**:
it runs on every PR and turns the check red, but a merge is not mechanically
prevented when it fails.

That is precisely the posture the retired decision-index job had, and it is how
`docs/decisions/` drifted on `main` in the first place (issue #157) — repeatedly
merged past while red because nothing enforced it. Treat a red
`context-drift-gate` as blocking by convention until the promotion below is applied.

**What was blocking the promotion, and what changed.** The precondition below —
"green on `main`" — was unreachable, because the gate attributed `main`'s own
pre-existing drift to every branch that merely inherited it. One stale artifact on
the integration branch failed the gate identically on 12 unrelated pull requests,
one-line dependabot bumps included (`docs/merge-logs/2026-08-24.md:26`). Promoting
a check with that failure mode would have blocked every merge in the repository.

`rescope-context-drift-enforcement` removed that failure mode:

- The gate resolves the base explicitly — `origin/<base>`, then a local ref, then a
  recorded null — and the report records both the resolved revision and how it
  resolved, so a verdict can be audited against a known tree.
- Every finding carries an `attribution` (`inherited` | `introduced` |
  `indeterminate`) and an `attributed_owner`.
- The exit code depends on the triggering event. On `pull_request`, introduced
  drift exits 2, while inherited and indeterminate drift exit 0 and are reported
  with the integration branch named as owner. On `merge_group` and `push: main`,
  **all** blocking drift exits 2 — at those points there is no other branch to
  inherit from. An unhandled event is an error, not a pass.
- The gate job runs on all three of those events with no job-level `if:`, because a
  required check that is skipped reports success to branch protection.
- `make context-drift-gate` with no `CONTEXT_GATE_EVENT` keeps the **strict** rule —
  every blocking finding fails — which is what it did before this change.

**What that does not establish.** It does not make the gate green on `main`, and
landing it on a branch is not the precondition being met. The precondition is
satisfied only when the gate is observed green on `main` after this change is
merged and `main`'s own inherited drift has been remediated; making a red check
required blocks every merge. Until then, this section records an unapplied
promotion, and the remaining action belongs to the repository owner, not to any
pull request.

**Promotion (one-time, requires repo admin):**

```bash
gh api -X POST \
  /repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks/contexts \
  -f 'contexts[]=context-drift-gate'
```

This endpoint is additive — it appends to the existing list rather than replacing
it, so the six current contexts are preserved. Verify afterwards:

```bash
gh api /repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks \
  --jq '.contexts'
```

The output MUST list all seven contexts.

**Do not delete this section once it is applied** — replace the status line above
with `**Status: APPLIED <date>.**` and keep the promotion command and its
verification on record. The `coverage-ratchet` section below back-references this
one, and `openspec/specs/fitness-functions/spec.md:115-116` makes that adjacency
normative: deleting this note would leave a spec-level claim pointing at nothing.

## Advisory by design: `coverage-ratchet` is not a required status check

**Status: INTENTIONALLY ADVISORY.** Unlike the pending promotion above, this is not
a gap awaiting an operator — the `coverage-ratchet` job
(`.github/workflows/ci.yml`) ships non-required on purpose
(introduce-fitness-function-gates, design D5).

The job measures line coverage for the `agent-coordinator` and `skills` suites
and compares each against `coverage-baseline.json` at the repo root, failing when
a suite drops by more than `tolerance_pp` (0.5pp). Coverage measurement is new in
this repo, so the first weeks of numbers are the noisiest they will ever be;
making a fresh ratchet required would block merges on measurement artefacts
rather than on real regressions.

**When the ratchet reports a regression**, either restore the coverage or, if the
drop is deliberate (deleted code, retired suite), reset the baseline and say why
in the commit message.

**When the ratchet reports an improvement**, move the bar up and commit the
result — the job prints the exact command, which is:

```bash
python scripts/coverage_ratchet.py \
  --coverage-xml agent-coordinator=agent-coordinator/coverage.xml \
  --coverage-xml skills=skills/coverage.xml \
  --update --updated-by "<who or which change>"
```

**Promotion to a required context (one-time, requires repo admin):**

```bash
gh api -X POST \
  /repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks/contexts \
  -f 'contexts[]=coverage-ratchet'
```

Same additive endpoint as the pending `context-drift-gate` promotion above —
existing contexts are preserved. Verify afterwards:

```bash
gh api /repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks \
  --jq '.contexts'
```

Do not promote until the job has been green on `main` for at least a week of
real PRs and the baseline reflects a settled measurement; making a red check
required blocks every merge. When it is promoted, replace this section's status
line with the date and the reason.
