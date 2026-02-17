# Design: Adopt OpenSpec 1.0 OPSX Workflow

## Context

The project has a mature 5-stage feature development workflow with 6 core skills and 3 OpenSpec wrapper skills. OpenSpec 1.0 introduces OPSX, a schema-driven artifact system with dependency graphs, lifecycle states (BLOCKED/READY/DONE), and granular commands. The current skills manually manage artifact creation, validation, and archiving — logic that OPSX now provides as framework capabilities.

The challenge is mapping our richer-than-default workflow (which includes exploration, iteration findings, validation reports, and deferred tasks) onto OPSX's schema system without losing our process discipline.

## Goals / Non-Goals

### Goals
- Define a custom `feature-workflow` schema that captures all artifact types our process produces
- Simplify skill implementations by delegating artifact lifecycle management to OPSX
- Preserve the existing approval gates and workflow sequence
- Enable OPSX's state tracking for artifact completion visibility
- Maintain backward compatibility during transition (skills keep their names)

### Non-Goals
- Changing the number of skills or their approval gates
- Adopting OPSX commands as user-facing replacements for our skills (skills remain the interface)
- Migrating existing archived changes to the new schema format

## Decisions

### Decision 1: Custom Schema with Optional Artifact Paths

The `feature-workflow` schema extends `spec-driven` with additional artifact types. Some artifacts (exploration, design, plan-findings, impl-findings, validation-report, deferred-tasks) are optional — they become READY when dependencies are met but don't block downstream artifacts.

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
  ├── validation-report  (requires: tasks)
  │                  │
  └── deferred-tasks     (requires: tasks)
```

Key insight: `tasks` depends only on `specs`, not `design`. This matches our current behavior where `design.md` is optional and shouldn't block task creation. Artifacts like `plan-findings` and `validation-report` are post-planning artifacts that depend on `tasks` existing but don't gate each other.

**Alternative considered**: Separate schemas for planning-only vs. full-lifecycle. Rejected because a single schema gives OPSX full visibility into the artifact graph and enables `opsx:continue` to suggest the right next artifact at any stage.

### Decision 2: Skills as Orchestrators, OPSX as Engine

Skills remain the user-facing interface. They orchestrate the workflow (parallel exploration, iteration loops, quality checks, approval gates) while delegating artifact creation and state management to OPSX commands.

```
User → /plan-feature → [opsx:explore, opsx:ff] → Approval gate
User → /implement-feature → [opsx:apply] → PR review gate
User → /validate-feature → [opsx:verify + deployment phases] → Validation gate
User → /cleanup-feature → [opsx:sync, opsx:archive] → Done
```

**Alternative considered**: Exposing OPSX commands directly to users. Rejected because our skills encode important workflow discipline (parallel exploration, structured iteration with finding types, quality checks, worktree setup) that OPSX commands alone don't provide.

### Decision 3: Findings as Structured Artifacts

Iteration findings (from `/iterate-on-plan` and `/iterate-on-implementation`) become first-class OPSX artifacts rather than ephemeral console output. Each iteration appends to the findings artifact, creating a traceable record of refinement decisions.

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

### Decision 4: Gradual Retirement of Legacy Skills

The three `openspec-*` skills become thin wrappers that call the equivalent OPSX commands:

| Legacy Skill | Wrapper Behavior |
|---|---|
| `/openspec-proposal` | Calls `opsx:new` or `opsx:ff` depending on argument flags |
| `/openspec-apply` | Calls `opsx:apply` |
| `/openspec-archive` | Calls `opsx:sync` then `opsx:archive` |

After one release cycle, these wrappers can be removed. This avoids breaking any muscle memory or documentation references.

### Decision 5: Template-Driven Artifact Content

Each artifact type gets a template in `openspec/schemas/feature-workflow/templates/`. Templates define the structure and required sections. OPSX uses these when generating instructions for artifact creation.

Templates enforce our conventions:
- `exploration.md` — structured context synthesis (not free-form notes)
- `plan-findings.md` — tabular format with type/criticality columns
- `impl-findings.md` — same format with implementation-specific finding types
- `architecture-impact.md` — structural diff, flow changes, parallel zone impact
- `validation-report.md` — phase-based results with pass/fail symbols
- `deferred-tasks.md` — migrated tasks with provenance and target

### Decision 6: Architecture Refresh as Workflow Sidecar, Impact as Per-Change Artifact

The `/refresh-architecture` skill produces project-global artifacts (`.architecture/`) that don't belong to any single change. It stays standalone. However, the *impact analysis* of a specific change on the architecture IS per-change data and belongs in the schema as `architecture-impact`.

**Integration touchpoints:**

| Workflow Stage | Architecture Action | Trigger |
|---|---|---|
| `/plan-feature` (exploration) | Full refresh if stale | `make architecture` before `opsx:explore` |
| `/validate-feature` | Diff + validate on changed files | `make architecture-diff` + `make architecture-validate` |
| `/cleanup-feature` (post-merge) | Full refresh on main | `make architecture` after merge |

**Why separate from validation-report:** The architecture impact analysis has its own template, findings format, and audience (architects reviewing structural consequences). Embedding it in the validation report would conflate deployment health with structural health.

**Alternative considered**: Making `.architecture/` artifacts per-change (generated into `openspec/changes/<id>/`). Rejected because architecture artifacts are expensive to generate, are most useful as a shared baseline, and would create massive duplication across changes.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| OpenSpec 1.0 CLI not yet stable | Pin to specific version; validate with `openspec schemas --json` before adoption |
| Custom schema format may change | Schema is a single YAML file — easy to update |
| Skills become coupled to OPSX command interface | OPSX commands are documented and stable; wrapper pattern limits blast radius |
| Findings artifacts may add noise to change directories | Only created when iteration skills are actually used; optional in schema |

## Migration Plan

1. **Install OpenSpec 1.0** — Update CLI, verify `opsx:*` commands available
2. **Create schema and config** — Add `openspec/schemas/feature-workflow/` and `openspec/config.yaml`
3. **Update core skills** — Modify 6 skills to use OPSX commands internally
4. **Create legacy wrappers** — Convert 3 `openspec-*` skills to thin wrappers
5. **Update documentation** — Rewrite `openspec/AGENTS.md` and `CLAUDE.md` references
6. **Validate** — Run `/plan-feature` and `/implement-feature` on a test change to verify end-to-end
7. **Remove wrappers** — After one cycle, delete the legacy `openspec-*` skills

Steps 1-2 can be done independently. Steps 3-4 depend on 1-2. Step 5 can parallel with 3-4. Step 6 depends on 3-5. Step 7 happens later.

## Open Questions

- Does OpenSpec 1.0 support optional artifacts in schemas (artifacts that are READY but can be skipped without blocking downstream)?
- Can `opsx:ff` be scoped to a subset of artifacts (e.g., only planning artifacts, not lifecycle artifacts)?
- How does `opsx:continue` handle artifacts that are READY but conceptually belong to a later workflow phase?
