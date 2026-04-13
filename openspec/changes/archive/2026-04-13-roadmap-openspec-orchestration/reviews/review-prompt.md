# Plan Review: roadmap-openspec-orchestration

You are reviewing a planning proposal for the `roadmap-openspec-orchestration` OpenSpec change. Your task is to evaluate the plan artifacts and produce structured findings.

## Instructions

1. Read ALL plan artifacts listed below
2. Evaluate against the review checklist
3. Output ONLY a valid JSON object conforming to the schema below — no markdown, no commentary

## Artifacts to Review

Read these files (all paths relative to repo root):

- `openspec/changes/roadmap-openspec-orchestration/proposal.md` — What and why
- `openspec/changes/roadmap-openspec-orchestration/design.md` — How it will be built
- `openspec/changes/roadmap-openspec-orchestration/specs/roadmap-orchestration/spec.md` — Requirements
- `openspec/changes/roadmap-openspec-orchestration/tasks.md` — Task decomposition
- `openspec/changes/roadmap-openspec-orchestration/work-packages.yaml` — Work packages and DAG
- `openspec/changes/roadmap-openspec-orchestration/contracts/README.md` — Contract definitions

## Context

This change proposes adding two new skills (`plan-roadmap` and `autopilot-roadmap`) that orchestrate the decomposition of large markdown proposals into multiple OpenSpec changes and execute them iteratively. Key aspects:

- Builds on existing skills (plan-feature, implement-feature, autopilot) without modifying them
- Introduces three new artifact types: roadmap.yaml, checkpoint.json, learning-log.md
- Adds a usage-limit-aware vendor scheduling policy engine
- Uses filesystem as canonical state, coordinator as optional cache

The existing codebase pattern for shared cross-skill code is `skills/parallel-infrastructure/scripts/`.

## Review Checklist

Evaluate against these dimensions:

1. **Specification Completeness** — SHALL/MUST language, testable scenarios, no ambiguity
2. **Contract Consistency** — Schemas match spec requirements, artifacts well-defined
3. **Architecture Alignment** — Follows existing codebase patterns, no unnecessary dependencies
4. **Security Review** — Input validation, no secrets exposure
5. **Performance Review** — No unbounded operations, pagination where needed
6. **Observability Review** — Monitoring, logging, alerting requirements
7. **Compatibility Review** — Breaking changes identified, migration paths
8. **Resilience Review** — Retry/timeout/fallback for dependencies, failure modes
9. **Work Package Validity** — DAG acyclic, non-overlapping write scopes, correct dependencies

## Output Schema

```json
{
  "review_type": "plan",
  "target": "roadmap-openspec-orchestration",
  "reviewer_vendor": "<your-vendor-name>",
  "findings": [
    {
      "id": 1,
      "type": "<spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience>",
      "criticality": "<low|medium|high|critical>",
      "description": "Clear description of the issue",
      "resolution": "Specific proposed fix",
      "disposition": "<fix|regenerate|accept|escalate>"
    }
  ]
}
```

Focus on findings that are medium criticality or higher. Include low-criticality findings only if they reveal a pattern.
