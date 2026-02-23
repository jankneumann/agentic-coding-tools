# Tasks: integrate-security-into-validation

## Requirement Mapping

- Feature Validation Skill (MODIFIED) → 1.1, 1.2, 2.1
- Validation Prerequisite Checks (MODIFIED) → 1.1
- Security Review Artifact Precheck (REMOVED) → 1.1
- Standalone Security Review Skill (UNCHANGED) → (no tasks needed)

## 1. Validate-Feature SKILL.md Changes

- [x] 1.1 Remove security-review-report precheck and add Security phase to validate-feature
  **Dependencies**: None
  **Files**: `skills/validate-feature/SKILL.md`
  **Traces**: Feature Validation Skill, Validation Prerequisite Checks, Security Review Artifact Precheck (REMOVED)
  **Details**:
  - Remove the `--skip-security-check` flag from arguments section
  - Remove the entire "Verify security review artifact unless explicitly skipped" prerequisite block (lines checking for `security-review-report.md`, commit SHA matching, and associated error messages)
  - Add `--skip-security` flag to arguments section
  - Add `security` to the list of valid phase names
  - Add a new **Phase 3: Security** section between Smoke (Phase 2) and E2E (Phase 3→4), renumbering subsequent phases:
    - Phase 3: Security — invoke `python3 skills/security-review/scripts/main.py` with `--repo .`, `--zap-target http://localhost:${AGENT_COORDINATOR_REST_PORT:-3000}`, `--change $CHANGE_ID`, `--out-dir docs/security-review`, `--allow-degraded-pass`
    - If `--skip-security` flag is set, skip with informational message
    - Security phase is non-critical: capture exit code, report result, continue with remaining phases on failure
    - Report gate decision (PASS/FAIL/INCONCLUSIVE) in phase results
  - Update the phase count in the overview from "five" to "seven" (Deploy, Smoke, Security, E2E, Architecture, Spec Compliance, Log Analysis)
  - Update the validation report template to include Security phase result line

- [x] 1.2 Update validate-feature validation report to include security results
  **Dependencies**: 1.1
  **Files**: `skills/validate-feature/SKILL.md`
  **Traces**: Feature Validation Skill
  **Details**:
  - In the validation report template section, add a Security phase line between Smoke and E2E:
    - `✓ Security: PASS — No threshold findings (dependency-check: ok, zap: ok)`
    - `✗ Security: FAIL — 2 high-severity findings detected`
    - `⚠ Security: INCONCLUSIVE — Scanners degraded (no container runtime)`
    - `○ Security: Skipped`
  - Ensure the PASS/FAIL determination accounts for the Security phase result

## 2. Workflow Documentation Updates

- [x] 2.1 Update CLAUDE.md workflow and skills-workflow.md
  **Dependencies**: None (independent of SKILL.md changes — different files)
  **Files**: `CLAUDE.md`, `docs/skills-workflow.md`
  **Traces**: Feature Validation Skill (MODIFIED)
  **Details**:
  - In `CLAUDE.md` workflow section, remove the `/security-review <change-id> (optional) → Security gate review` line from the indented sub-steps under `/implement-feature`
  - In `docs/skills-workflow.md`:
    - Update the step dependencies table: remove `security-review-report.md precheck (unless skipped)` from validate-feature's inputs
    - Add "Security scan (dependency-check + ZAP)" to validate-feature's capabilities description
    - Update the validate-feature phase list to include Security between Smoke and E2E
    - Keep `/security-review` section as a standalone skill for ad-hoc use

## 3. Validation

- [x] 3.1 Validate OpenSpec artifacts (`openspec validate integrate-security-into-validation --strict`)
  **Dependencies**: 1.1, 1.2, 2.1
  **Files**: `openspec/changes/integrate-security-into-validation/`
  **Details**: Run strict validation to ensure proposal, specs, and tasks are consistent.
