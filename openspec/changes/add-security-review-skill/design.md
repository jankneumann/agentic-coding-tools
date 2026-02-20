# Design: add-security-review-skill

## Context

The repository has strong workflow skills for planning, implementation, validation, and cleanup, but no dedicated reusable security review skill. Existing checks are fragmented across smoke tests, CI lint/test jobs, and one-off local commands. The requested capability must run across heterogeneous repositories, not just this codebase.

## Goals / Non-Goals

### Goals
- Provide a reusable `/security-review` workflow for cross-project use.
- Auto-detect project profile(s) and select scanner matrix accordingly.
- Support OWASP Dependency-Check and ZAP Docker adapters as first-class scanners.
- Provide dependency bootstrap scripts and explicit install guidance when prerequisites are missing.
- Normalize outputs into a canonical finding model and deterministic gate decision.
- Produce operator-friendly markdown plus machine-readable JSON for automation.

### Non-Goals
- Replacing project-specific SAST pipelines already maintained in CI.
- Building a full vulnerability management platform (ticketing, SLA tracking, triage UI).
- Guaranteeing zero false positives from upstream scanners.

## Decisions

### 1. Adapter-based scanner architecture
Use a scanner adapter contract (`plan -> execute -> parse -> normalize`) so tool-specific logic is isolated and reusable.

Rationale:
- Keeps SKILL.md orchestration readable.
- Allows incremental addition of scanners (for example gitleaks, trivy, semgrep) without rewriting core gate logic.

### 2. Multi-profile detection with explicit confidence
Detect profiles from repository signals (manifest files, lockfiles, docker compose/OpenAPI cues) and produce `high|med|low` confidence.

Rationale:
- Cross-project reliability requires explicit detection confidence, not hidden assumptions.
- Mixed-stack repos should run union scanner plans.

### 3. Dependency-Check execution preference
Execution order:
1. Native CLI (if installed and compatible)
2. Docker image fallback
3. Unavailable status with remediation guidance

Rationale:
- Native execution is usually faster in developer environments.
- Docker fallback preserves portability across projects.

### 4. ZAP execution modes
Support `baseline` and `api` as default practical modes; allow optional `full` mode for deeper manual runs.

Rationale:
- Baseline/API modes are operationally lighter for routine gate checks.
- Full scan is useful but too heavy as default in iterative developer loops.

### 5. Deterministic risk gate
Canonical severity ladder: `info < low < medium < high < critical`.
Decision policy:
- `FAIL` when findings at/above threshold exist.
- `INCONCLUSIVE` when required scanners are unavailable/failed.
- `PASS` only when threshold is unmet and required scanners executed.

Rationale:
- Deterministic outcomes are required for repeatable gate behavior.
- Inconclusive runs should not silently pass in strict mode.

### 6. Bootstrap-first dependency onboarding
Provide a bootstrap helper (`skills/security-review/scripts/install_deps.sh`) plus documented manual install instructions by OS. The runner performs preflight checks and either executes bootstrap or prints scoped install commands.

Rationale:
- Cross-project reuse requires predictable onboarding in repos with different baseline environments.
- Explicit install guidance reduces friction when automation cannot run (for example restricted CI agents).

### 7. OpenSpec artifact dependency before validation
Add `security-review-report.md` as a `feature-workflow` artifact and require `/validate-feature` to check it before running deployment/spec validation phases.

Rationale:
- Security gate evidence should be explicit and auditable in the change artifact set.
- Prevents running expensive validation phases when a mandatory security precheck is missing.

### 8. Repository-scoped report location under docs/
Write all `/security-review` intermediate and canonical outputs to `docs/security-review/` by default.

Rationale:
- Aligns with repository architecture-analysis and documentation artifact conventions.
- Keeps outputs easy to locate and inspect without hidden dot-directories.

## Alternatives Considered

### A. Hardcode a single scan sequence in SKILL.md
Rejected: difficult to maintain, weak for cross-project adaptation, and no clean extension path.

### B. ZAP + Dependency-Check only, no normalization layer
Rejected: tool outputs differ too much for consistent gate semantics and automation.

### C. CI-only implementation, no local skill
Rejected: conflicts with workflow requirement to support local/human approval gates.

## Risks / Trade-offs

- Scanner runtime variability may slow developer loops.
  Mitigation: modes (`quick|standard|deep`) and default baseline-first behavior.
- False positives may cause noisy failures.
  Mitigation: suppression/ignore config support and clear report attribution.
- Tool prerequisites vary across machines.
  Mitigation: preflight checks, bootstrap helper script, and actionable remediation output.

## Migration Plan

1. Add `/security-review` skill and scripts behind additive workflow path.
2. Validate on representative Python, Node, and mixed-stack repositories.
3. Document recommended invocation points in `docs/skills-workflow.md`.
4. Optionally add CI templates in a follow-up change after output schema stabilizes.

Rollback:
- Remove `skills/security-review/` and docs references.
- Keep existing workflow paths untouched because this change is additive.
