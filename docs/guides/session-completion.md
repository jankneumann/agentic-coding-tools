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

## Known gap: `context-drift-gate` is not a required status check

**Status: NOT APPLIED.** This is an open gap, not a completed step.

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

The output MUST list all seven contexts. Once it does, delete this section — a
"known gap" that has been closed is worse than no note at all.

Do not apply the promotion until the gate is green on `main`; making a red check
required blocks every merge.

## Advisory by design: `coverage-ratchet` is not a required status check

**Status: INTENTIONALLY ADVISORY.** Unlike the section above, this is not a gap —
the `coverage-ratchet` job (`.github/workflows/ci.yml`) ships non-required on
purpose (introduce-fitness-function-gates, design D5).

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

Same additive endpoint as the `context-drift-gate` promotion above — existing
contexts are preserved. Verify afterwards:

```bash
gh api /repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks \
  --jq '.contexts'
```

Do not promote until the job has been green on `main` for at least a week of
real PRs and the baseline reflects a settled measurement; making a red check
required blocks every merge. When it is promoted, replace this section's status
line with the date and the reason.
