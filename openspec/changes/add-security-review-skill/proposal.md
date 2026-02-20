# Change: add-security-review-skill

## Why

Security review is currently distributed across ad-hoc checks and project-specific commands, so teams cannot apply a consistent security gate across repositories. We need a reusable `/security-review` skill that works across different stacks and gives a normalized, decision-ready risk outcome.

## What Changes

- Add a new reusable skill at `skills/security-review/SKILL.md` for cross-project security review.
- Add project profile detection so the skill auto-selects scanner workflows based on repository signals (for example Python, Node, Java, containerized API targets, and mixed-stack repositories).
- Add scanner adapters for:
  - OWASP Dependency-Check (native CLI when available, Docker fallback)
  - OWASP ZAP Docker scans (`zap-baseline.py`, `zap-api-scan.py`, optional full scan mode)
- Enforce script layout: all executable helpers for the skill live under `skills/security-review/scripts/`.
- Add dependency bootstrap helpers that either install required tooling or emit precise install instructions when prerequisites are missing.
- Add normalized finding aggregation into a canonical JSON structure and a markdown summary.
- Store intermediate and canonical security outputs under `docs/security-review/` for architecture-aligned discoverability.
- Add configurable risk gates (`--fail-on`) so severity thresholds produce deterministic PASS/FAIL/INCONCLUSIVE outcomes.
- Add explicit degraded-mode handling for missing prerequisites (for example Docker or Java unavailable) with actionable remediation.
- Add OpenSpec-aligned artifact flow: `/security-review` can emit `security-review-report.md`, and `/validate-feature` checks this artifact before full validation phases.

## Impact

- Affected specs:
  - `skill-workflow` via `openspec/changes/add-security-review-skill/specs/skill-workflow/spec.md`
- Affected code and docs:
  - `skills/security-review/SKILL.md` (new)
  - `skills/security-review/scripts/*` (new helper runners/parsers)
  - `skills/security-review/scripts/install_deps.sh` (new dependency bootstrap helper)
  - `skills/security-review/scripts/check_prereqs.sh` (new prerequisite detection helper)
  - `skills/security-review/docs/dependencies.md` (new install guidance by platform)
  - `openspec/schemas/feature-workflow/schema.yaml` + `openspec/schemas/feature-workflow/templates/security-review-report.md` (new artifact definition)
  - `skills/validate-feature/SKILL.md` (pre-validation security artifact check)
  - `docs/skills-workflow.md` (workflow integration for optional security review gate)
  - `AGENTS.md` (skill catalog update)
- Affected architecture layers:
  - **Execution**: scanner runner commands and report generation
  - **Coordination**: reusable workflow orchestration and profile-based task selection
  - **Trust**: vulnerability and DAST findings evaluation
  - **Governance**: normalized risk gate decisions and audit-ready report outputs
- Breaking changes: None. `/security-review` is additive and optional in the workflow.
