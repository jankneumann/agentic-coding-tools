# Exploration

## Objective

Define a reusable `/security-review` skill that works across repositories, supports OWASP Dependency-Check and ZAP Docker scanning, and emits normalized risk-gated outputs.

## Existing Context

### Related Specs

- `skill-workflow` (18 requirements): defines workflow skill behavior and integration points.
- `merge-pull-requests` (8 requirements): includes security-priority merge heuristics but no dedicated scanning skill.

### Active Changes

- `complete-missing-coordination-features` (98/99)
- `adopt-opsx-1.0-workflow` (21/22)
- `add-coordinator-assurance-verification` (16/35)
- `add-dynamic-authorization` (0/55)

No active change currently defines a reusable cross-project security review skill.

### Architecture Context

- `docs/architecture-analysis/architecture.summary.json` is present.
- High-impact nodes are configuration/database service boundaries; this change is workflow/tooling-centric and low-risk to runtime architecture.
- `docs/architecture-analysis/parallel_zones.json` indicates large independent zones, allowing skill/docs work with minimal conflict.

### Codebase Patterns

- Existing skills with helper scripts:
  - `skills/validate-feature/` (phase-based validation + pytest smoke tests)
  - `skills/merge-pull-requests/` (Python helper scripts for orchestration)
- Existing workflow docs already support optional skill stages and artifact-driven gates.

## Context Synthesis

### Constraints

- Must follow OpenSpec feature-workflow artifacts (`proposal`, `specs`, `tasks`; optional `design`).
- Tasks must include explicit dependencies and file scopes.
- New skill should be additive, not break existing workflow paths.

### Integration Points

- Add new skill folder at `skills/security-review/`.
- Extend `docs/skills-workflow.md` and `AGENTS.md` skill inventory.
- Extend `skill-workflow` spec capability with requirements for the new skill.

### Risks

- Tool availability differences across projects (Docker/Java/runtime prerequisites).
- False positives from scanners affecting gate trust.
- Heterogeneous repository structures reducing detection confidence.

## Recommendation

Proceed to proposal. The capability is additive, directly requested, and aligns with existing skill + script architecture patterns.
