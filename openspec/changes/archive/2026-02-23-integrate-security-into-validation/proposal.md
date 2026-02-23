# Change: integrate-security-into-validation

## Why

The `/security-review` skill currently runs as a separate prerequisite before `/validate-feature`, but its most valuable scanner (ZAP DAST) requires a live API endpoint — which only exists during validate-feature's deploy phase. This creates a chicken-and-egg problem: either ZAP is skipped entirely, or the user must manually start the API just for the security scan. OWASP Dependency-Check also has reliability issues running standalone (native binary failures, Java prerequisites). By embedding security scanning as a phase within `/validate-feature`, both scanners can leverage the already-deployed services, eliminating the ordering problem and simplifying the workflow from two separate invocations to one.

## What Changes

### Validate-feature gains a Security Scan phase

- `/validate-feature` SHALL include a new **Security** phase that runs after Deploy + Smoke (when the API is confirmed healthy) and before E2E
- The Security phase SHALL invoke the existing `security-review/scripts/main.py` orchestrator, passing the live deployment URL as `--zap-target` and the change-id via `--change`
- The Security phase SHALL be **non-critical** — failures are reported but do not stop remaining validation phases (same pattern as E2E, Spec Compliance, Log Analysis)
- The Security phase SHALL support `--skip-security` flag to skip entirely (replacing the current `--skip-security-check`)
- The Security phase SHALL use `--allow-degraded-pass` when scanner prerequisites (Java, container runtime) are unavailable, reporting degraded coverage rather than blocking validation
- Phase results SHALL be included in the validation report with pass/fail/skip/degraded status

### Remove security-review-report precheck from validate-feature **BREAKING**

- The prerequisite check that verifies `security-review-report.md` exists with matching commit SHA SHALL be removed
- The `--skip-security-check` flag SHALL be replaced by `--skip-security` (which skips the scan phase itself)
- `/validate-feature` SHALL no longer require running `/security-review` beforehand

### Security-review remains as standalone skill

- `/security-review` SHALL continue to work independently for ad-hoc scans, CI pipelines, and non-feature-workflow use cases
- No changes to security-review scripts, models, parsers, or gate logic — validate-feature reuses them as-is
- The `--change` flag on `/security-review` SHALL continue to emit `security-review-report.md` for manual workflows

### Workflow documentation updated

- CLAUDE.md workflow diagram SHALL remove `/security-review` from the indented sub-steps under `/implement-feature`
- `docs/skills-workflow.md` SHALL update the step dependencies table: validate-feature no longer depends on security-review-report.md precheck
- `docs/skills-workflow.md` SHALL document the new Security phase within validate-feature's phase list

## Impact

### Affected specs

- `skill-workflow` — delta spec updating validate-feature phase list, removing security-review prerequisite, adding Security phase requirements

### Code touchpoints

- `skills/validate-feature/SKILL.md` — remove security-review-report precheck, add Security phase after Smoke, update flag documentation
- `CLAUDE.md` — remove `/security-review` from workflow sub-steps
- `docs/skills-workflow.md` — update step dependencies table and validate-feature description
- `openspec/changes/add-security-review-skill/specs/skill-workflow/spec.md` — archived change reference (no modification needed, delta already merged to main spec)

### Coordination

- `fix-scrub-isolation-and-script-paths` change (not yet started) updates `security-review/SKILL.md` script paths — no conflict since this change only modifies `validate-feature/SKILL.md` and documentation

### Rollback

Changes are limited to SKILL.md instruction files and documentation. Reverting is a single `git revert` of the merge commit. The security-review skill remains fully functional as a standalone tool. No runtime code, database, or infrastructure changes.
