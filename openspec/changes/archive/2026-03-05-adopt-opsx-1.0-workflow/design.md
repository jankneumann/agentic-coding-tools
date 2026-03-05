# Design: Adopt OpenSpec 1.0 OPSX Workflow

## Context

The project has a mature 5-stage feature development workflow with 6 core skills. OpenSpec 1.0 introduces a schema-driven artifact system with dependency graphs, lifecycle states, project-level config/rules, and instruction-based artifact generation (`openspec instructions ...`). The current skills and docs still contain assumptions from older command naming and wrapper patterns, which now causes ambiguity during execution.

The challenge is mapping our richer-than-default workflow (exploration, iteration findings, validation reports, deferred tasks, architecture impact) onto the OpenSpec 1.0 schema system without losing process discipline.

## Goals / Non-Goals

### Goals
- Define a custom `feature-workflow` schema that captures all artifact types our process produces
- Simplify skill implementations by delegating artifact lifecycle guidance/state awareness to OpenSpec 1.0 commands
- Preserve the existing approval gates and workflow sequence
- Enable OpenSpec state tracking for artifact completion visibility
- Maintain backward compatibility during transition (skills keep their names)

### Non-Goals
- Changing the number of skills or their approval gates
- Replacing skills with raw OpenSpec commands as the user interface
- Migrating existing archived changes to the new schema format

## Decisions

### Decision 1: Custom Schema with Explicit Optional Artifact Paths

The `feature-workflow` schema extends `spec-driven` with additional artifact types. Some artifacts (exploration, design, plan-findings, impl-findings, validation-report, deferred-tasks) are optional: they can be generated when useful, but are not blockers for required artifacts.

**Schema dependency graph:**

```
exploration ─────────┐
                     │
proposal ────────────┤
  │                  │
  ├── specs ─────────┤
  │                  │
  └── design         │
                     │
tasks ───────────────┤  (requires: specs)
  │                  │
  ├── plan-findings  │  (requires: proposal, tasks)
  │                  │
  ├── architecture-impact (requires: tasks)
  │
  ├── validation-report  (requires: tasks)
  │                  │
  └── deferred-tasks     (requires: tasks)
```

Key insight: `tasks` depends only on `specs`, not `design`. This matches our current behavior where `design.md` is optional and shouldn't block task creation. Artifacts like `plan-findings` and `validation-report` are post-planning artifacts that depend on `tasks` existing but don't gate each other.

**Alternative considered**: Separate schemas for planning-only vs. full-lifecycle. Rejected because a single schema gives complete visibility into the artifact graph and avoids schema switching complexity.

### Decision 2: Skills as Orchestrators with Agent-Native OpenSpec Precedence

Skills remain the user-facing interface. They orchestrate the workflow (parallel exploration, iteration loops, quality checks, approval gates) while delegating artifact guidance/lifecycle to agent-native OpenSpec artifacts first, with direct CLI fallback when agent-native artifacts are missing or incompatible.

Precedence:
1. Agent-native OpenSpec artifacts for the active agent runtime.
2. Direct OpenSpec CLI command family fallback.

Agent-native locations in this repo:
- Claude commands: `.claude/commands/opsx/*.md`
- Claude skills: `.claude/skills/openspec-*/SKILL.md`
- Codex skills: `.codex/skills/openspec-*/SKILL.md`
- Gemini commands: `.gemini/commands/opsx/*.toml`
- Gemini skills: `.gemini/skills/openspec-*/SKILL.md`

```
User → /plan-feature → [agent-native opsx skill OR openspec new/instructions fallback] → Approval gate
User → /implement-feature → [agent-native apply skill OR openspec instructions apply fallback] → PR review gate
User → /validate-feature → [agent-native validate/verify skill OR openspec instructions fallback + deployment phases] → Validation gate
User → /cleanup-feature → [agent-native archive skill OR openspec archive fallback] → Done
```

**Alternative considered**: Exposing OpenSpec commands directly to users. Rejected because skills encode important workflow discipline (parallel exploration, structured iteration with finding types, quality checks, handoff gates) that commands alone do not provide.

### Decision 3: Findings as Structured Artifacts

Iteration findings (from `/iterate-on-plan` and `/iterate-on-implementation`) become first-class artifacts rather than ephemeral console output. Each iteration appends to the findings artifact, creating a traceable record of refinement decisions.

```markdown
# Plan Findings: <change-id>

## Iteration 1 (2026-02-17)
| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | completeness | high | Missing failure scenario for auth | Added scenario |

## Iteration 2 (2026-02-17)
...
```

**Alternative considered**: One findings file per iteration. Rejected because a single cumulative file gives better context for review and avoids artifact proliferation.

### Decision 4: Remove Legacy Wrappers and Standardize Cross-Agent Behavior

Instead of re-introducing legacy `/openspec-*` wrappers, core skills use the generated OpenSpec artifacts shipped for each agent runtime, with CLI fallback to preserve deterministic behavior.

**Alternative considered**: Re-adding `/openspec-*` wrappers for compatibility. Rejected because it adds maintenance surface and duplicates behavior now covered by direct command usage in the core skills.
**Alternative considered**: CLI-only implementation. Rejected because it ignores the upgraded generated artifacts and increases per-agent drift risk.

### Decision 5: Template-Driven Artifact Content

Each artifact type gets a template in `openspec/schemas/feature-workflow/templates/`. Templates define structure and required sections. `openspec instructions <artifact> --change <id>` surfaces these expectations consistently in skill flows.

Templates enforce our conventions:
- `exploration.md` — structured context synthesis (not free-form notes)
- `plan-findings.md` — tabular format with type/criticality columns
- `impl-findings.md` — same format with implementation-specific finding types
- `architecture-impact.md` — structural diff, flow changes, parallel zone impact
- `validation-report.md` — phase-based results with pass/fail symbols
- `deferred-tasks.md` — migrated tasks with provenance and target

### Decision 6: Architecture Refresh as Workflow Sidecar, Impact as Per-Change Artifact

The `/refresh-architecture` skill produces project-global artifacts (`docs/architecture-analysis/`) that do not belong to any single change. It stays standalone. The impact analysis of a specific change is per-change data and belongs in the schema as `architecture-impact`.

**Integration touchpoints:**

| Workflow Stage | Architecture Action | Trigger |
|---|---|---|
| `/plan-feature` (exploration) | Full refresh if stale | `make architecture` before proposal/spec/task authoring |
| `/validate-feature` | Diff + validate on changed files | `make architecture-diff` + `make architecture-validate` |
| `/cleanup-feature` (post-merge) | Full refresh on main | `make architecture` after merge |

**Why separate from validation-report:** The architecture impact analysis has its own template, findings format, and audience (architects reviewing structural consequences). Embedding it in the validation report would conflate deployment health with structural health.

**Alternative considered**: Making `docs/architecture-analysis/` artifacts per-change (generated into `openspec/changes/<id>/`). Rejected because architecture artifacts are expensive to generate, are most useful as a shared baseline, and would create massive duplication across changes.

### Decision 7: Enforce Cross-Agent Parity Checks

Because workflow artifacts now exist per agent runtime, the plan includes explicit parity checks across Claude/Codex/Gemini so behavior does not diverge.

Parity checks cover:
- Equivalent artifact mapping (plan/apply/validate/archive) across runtimes
- Same fallback trigger conditions
- Same gating guarantees (`openspec validate --strict` still authoritative)

### Decision 8: Add Pre-Planning Opportunity Discovery Skill

Introduce `/explore-feature` as an optional pre-planning supporting skill that identifies candidate features from architecture diagnostics, codebase signals, and active OpenSpec state. It does not replace approval gates or planning artifacts; it improves proposal quality and prioritization before `/plan-feature`.

Outputs:
- Ranked opportunity list with reproducible weighted scoring (impact, strategic fit, effort, risk)
- Dual buckets (`quick-win`, `big-bet`) to balance immediate value and larger investments
- Explicit `blocked-by` dependencies per candidate
- Recommendation history to reduce repeated resurfacing of unchanged deferred work
- Machine-readable artifacts for downstream automation:
  - `docs/feature-discovery/opportunities.json`
  - `docs/feature-discovery/history.json`
- Recommended next `/plan-feature` input
- Explicit rationale tied to architecture/code evidence

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Agent-native artifacts drift between runtimes | Add explicit parity checks in validation tasks and docs |
| Command semantics drift across OpenSpec updates | Validate command assumptions in CI via `openspec --help`, `openspec instructions --help`, and `openspec schema validate` |
| Custom schema format may change | Schema is a single YAML file — easy to update |
| Skills become coupled to generated artifact format | Keep CLI fallback as stable escape hatch |
| Findings artifacts may add noise to change directories | Only created when iteration skills are actually used; optional in schema |

## Migration Plan

1. **Validate current schema/config** — Ensure `feature-workflow` and templates pass `openspec schema validate` and command-driven expectations
2. **Integrate agent-native artifacts** — Modify 6 skills to prefer generated OpenSpec artifacts for Claude/Codex/Gemini
3. **Wire CLI fallback** — Keep `openspec` command family fallback in each high-level skill
4. **Update documentation** — Rewrite `AGENTS.md`, `docs/skills-workflow.md`, and `CLAUDE.md` to document precedence and parity requirements
5. **Validate end-to-end + parity** — Run `/plan-feature` and `/implement-feature` test flows, verify cross-agent parity checklist, plus `openspec validate --strict`

Step 1 is foundational. Steps 2 and 3 can run in parallel with file-scope isolation. Step 4 depends on 2-3. Step 5 depends on 1-4.

## Open Questions

- Should `exploration` be required in this project schema or remain optional for fast-path fixes?
- Should `/validate-feature` always generate `architecture-impact`, or allow skipping it for docs-only changes?
