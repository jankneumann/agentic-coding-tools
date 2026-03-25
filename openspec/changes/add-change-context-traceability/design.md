# Design: change-context.md Traceability Artifact

## Context

The OpenSpec feature workflow generates 5+ artifacts per change, but no single artifact answers "how do spec requirements map to code changes and what test evidence proves each one?" This design introduces a structured traceability matrix that doubles as a TDD enforcement mechanism.

## Goals

- Provide a single artifact that maps every spec requirement to its implementing code, tests, and validation evidence
- Enforce test-driven development structurally — tests derived from spec scenarios before implementation code
- Eliminate duplication between change-context.md and validation-report.md's spec compliance section
- Support both linear and parallel workflows

## Non-Goals

- Replacing proposal.md, design.md, or tasks.md — those serve different purposes
- Machine-executable test generation — tests are written by the agent, guided by the matrix
- Formal JSON schema for change-context.md — follows the existing markdown-with-tables convention

## Decisions

### Decision 1: 3-Phase Incremental Generation

**Chosen**: Build change-context.md in 3 phases aligned with the workflow:
- Phase 1 (pre-implementation): Skeleton with Req ID, Spec Source, Description, planned Test(s). Write failing tests (RED).
- Phase 2 (implementation): Code written to make tests pass (GREEN). Files Changed column populated.
- Phase 3 (validation): Evidence column filled with pass/fail results from live system.

**Alternative A**: Generate entirely during validation (single phase). Rejected because the implementation agent's knowledge of why each file was changed is lost by the time validation runs. Validation would need to reconstruct the mapping from git diff.

**Alternative B**: Generate entirely during implementation (two phase). Rejected because evidence collection requires live system validation, which only happens in the validate-feature phase.

**Rationale**: The 3-phase model captures context at the point where it's freshest: spec→test mapping when specs are being read, code→file mapping when code is being written, evidence when tests are run against live systems. It also naturally enforces TDD by making Phase 1 (test writing) a prerequisite for Phase 2 (implementation).

### Decision 2: Replace Spec Compliance Section in validation-report.md

**Chosen**: validation-report.md's "Spec Compliance Details" section (scenario-level pass/fail table) is replaced with a reference to change-context.md. The validation report retains operational phases (Deploy, Smoke, Security, E2E, Architecture, Logs, CI/CD) and adds a one-line summary.

**Alternative**: Keep both artifacts with duplicated spec compliance data. Rejected because it creates maintenance burden and divergence risk.

**Rationale**: change-context.md provides strictly more information than the existing spec compliance table (it adds Files Changed, Test(s), and Design Decision Trace). The validation report's job is operational health; spec compliance belongs in the traceability artifact.

### Decision 3: Structural TDD Enforcement via Step Ordering

**Chosen**: Insert a new step 3a "Generate Change Context & Test Plan" before the existing "Implement Tasks" step. This step creates the traceability skeleton and writes failing tests. The existing TDD advisory note (3 lines) is removed.

**Alternative**: Strengthen the existing TDD note without structural changes. Rejected because advisory notes are routinely ignored — the 3-line note has not prevented tests from being written after implementation.

**Rationale**: Making test writing a prerequisite step with a concrete artifact (change-context.md with Test(s) column) creates a structural checkpoint. The agent must populate the matrix and write tests before moving to implementation.

### Decision 4: Parallel Workflow Review Findings Integration

**Chosen**: change-context.md includes a "Review Findings Summary" section (parallel workflow only) that synthesizes findings from `artifacts/<package-id>/review-findings.json`. Findings with disposition `fix`, `escalate`, or `regenerate` are always included; `accept` findings only if `medium`+ criticality.

**Alternative**: Keep review findings only in JSON files. Rejected because PR reviewers would need to parse multiple JSON files to understand what was flagged.

**Rationale**: The change-context.md serves as the single review artifact. Including a findings summary gives reviewers complete context without navigating separate files.

## Risks and Trade-offs

### Risk 1: Phase 1 Tests May Be Imprecise
Tests written before implementation may not perfectly match the final API/interface. The implementation phase may require test refinements.

**Mitigation**: The skill instruction explicitly allows updating Test(s) during Phase 2. iterate-on-implementation also updates the matrix when findings reveal missing requirements.

### Risk 2: Pre-existing Changes Without change-context.md
Changes started before this feature is deployed won't have the artifact.

**Mitigation**: validate-feature generates the skeleton on-the-fly if change-context.md is missing, using the same logic as implement-feature step 3a but without the TDD enforcement (tests already exist).

### Risk 3: Import Failures in RED Phase
Tests that reference implementation types/interfaces will fail to import before implementation exists.

**Mitigation**: Edge case documented — write test functions with placeholder assertions. Import failures in RED phase are expected and validate that tests truly precede code. Integration/e2e test stubs use `@pytest.mark.integration` markers and won't run during the RED phase.

## Migration Plan

No migration needed. This is an additive change to skill instructions. Existing changes continue to work. The validate-feature fallback handles backward compatibility.
