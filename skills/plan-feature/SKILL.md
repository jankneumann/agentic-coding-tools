---
name: plan-feature
description: "Create OpenSpec proposal with tiered execution (coordinated / local-parallel / sequential)"
category: Git Workflow
tags: [openspec, planning, proposal, contracts, work-packages]
triggers:
  - "plan feature"
  - "plan a feature"
  - "design feature"
  - "propose feature"
  - "start planning"
  - "linear plan feature"
  - "parallel plan feature"
  - "parallel plan"
  - "plan parallel feature"
---

# Plan Feature

Create an OpenSpec proposal for a new feature. Automatically selects execution tier based on coordinator availability and feature complexity. Ends when proposal is approved.

## Arguments

`$ARGUMENTS` - Feature description (e.g., "add user authentication")

## OpenSpec Execution Preference

Use OpenSpec-generated runtime assets first, then CLI fallback:
- Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- Fallback: direct `openspec` CLI commands

## Steps

### 0. Detect Coordinator and Select Tier [all tiers]

Run the coordinator detection script:

```bash
python3 "<skill-base-dir>/../coordination-bridge/scripts/check_coordinator.py" --json
```

Parse JSON output and set capability flags. Then select tier:

```
If COORDINATOR_AVAILABLE and CAN_DISCOVER and CAN_QUEUE_WORK and CAN_LOCK:
  TIER = "coordinated"
Else if user invoked via "parallel plan" trigger OR feature touches 2+ architectural boundaries:
  TIER = "local-parallel"
Else:
  TIER = "sequential"
```

Emit tier notification:
```
Tier: <tier> -- <rationale>
```

If `CAN_HANDOFF=true`, read recent handoff context. If `CAN_MEMORY=true`, recall relevant memories.

### 1. Setup Planning Worktree [all tiers]

The shared checkout is **read-only** -- never commit or modify files there. All planning work happens in a feature-level worktree.

```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "<change-id>"
cd $WORKTREE_PATH

git rev-parse --show-toplevel  # Should match WORKTREE_PATH
git branch --show-current       # Should be openspec/<change-id>
```

If the worktree already exists (e.g., from a previous session), reuse it. All subsequent steps happen **inside the worktree**.

### 2. Review Existing Context (Parallel Exploration) [all tiers]

Gather context from multiple sources concurrently using Task(Explore) agents:

```
Task(subagent_type="Explore", prompt="Read openspec/project.md and summarize the project purpose, tech stack, and conventions", run_in_background=true)
Task(subagent_type="Explore", prompt="Run 'openspec list --specs' and summarize existing specifications", run_in_background=true)
Task(subagent_type="Explore", prompt="Run 'openspec list' and identify in-progress changes that might conflict with: $ARGUMENTS", run_in_background=true)
Task(subagent_type="Explore", prompt="Search the codebase for existing implementations related to: $ARGUMENTS", run_in_background=true)
Task(subagent_type="Explore", prompt="Read docs/architecture-analysis/architecture.summary.json and parallel_zones.json for component inventory and safe parallel zones", run_in_background=true)
```

Wait for all results and synthesize into unified context summary.

Before creating artifacts, ensure architecture artifacts are current:

```bash
if [ ! -f docs/architecture-analysis/architecture.summary.json ] || \
   [ "$(git log -1 --format=%ct main)" -gt "$(stat -f %m docs/architecture-analysis/architecture.summary.json 2>/dev/null || echo 0)" ]; then
  make architecture
fi
```

### 3. Create OpenSpec Proposal [all tiers]

Preferred path: Use runtime-native fast-forward/new workflow.

CLI fallback path:

```bash
openspec new change "<change-id>"
openspec instructions proposal --change "<change-id>"
openspec instructions specs --change "<change-id>"
openspec instructions tasks --change "<change-id>"
openspec instructions design --change "<change-id>"  # When complexity warrants it
```

Expected artifacts:
- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/tasks.md`
- `openspec/changes/<change-id>/specs/<capability>/spec.md`
- Optional `openspec/changes/<change-id>/design.md`

### 4. Generate Contracts [local-parallel+]

**Skip this step if TIER is "sequential".**

Produce machine-readable interface definitions in `contracts/`. Contracts become the coordination boundary between parallel agents.

#### 4a. OpenAPI Contracts

For API features, generate from `openspec/schemas/feature-workflow/templates/openapi-stub.yaml`:

```yaml
contracts/openapi/v1.yaml    # OpenAPI 3.1.0 spec with paths, schemas, examples
```

Requirements: every endpoint has request/response schemas with `example` fields, discriminator fields for polymorphic responses, error response schemas following RFC 7807.

#### 4b. Database Contracts

```yaml
contracts/db/schema.sql      # CREATE TABLE / ALTER TABLE statements
contracts/db/seed.sql         # Test fixture data
```

#### 4c. Event Contracts

```yaml
contracts/events/user.created.schema.json   # JSON Schema for event payload
```

#### 4d. Type Generation Stubs

```yaml
contracts/generated/models.py    # Pydantic models from OpenAPI schemas
contracts/generated/types.ts     # TypeScript interfaces from OpenAPI schemas
```

### 5. Generate Work Packages [local-parallel+]

**Skip this step if TIER is "sequential".**

Decompose tasks into agent-scoped work packages in `work-packages.yaml`. Follow the schema at `openspec/schemas/work-packages.schema.json`.

#### 5a. Package Decomposition

Group tasks by architectural boundary:
- `wp-contracts` -- Generate/validate contracts (always first, priority 1)
- `wp-<backend-module>` -- Backend implementation per bounded context
- `wp-<frontend-module>` -- Frontend implementation per component group
- `wp-integration` -- Merge worktrees and run full test suite (always last)

#### 5b. Scope Assignment

For each package, declare explicit file scope:

```yaml
scope:
  write_allow:
    - "src/api/**"
  read_allow:
    - "src/**"
    - "contracts/**"
  deny:
    - "src/frontend/**"
```

**Rule**: Parallel packages MUST have non-overlapping `write_allow` scopes.

#### 5c. Lock Declaration

```yaml
locks:
  files:
    - "src/api/users.py"
  keys:
    - "api:GET /v1/users"
    - "db:schema:users"
    - "event:user.created"
  ttl_minutes: 120
  reason: "Backend API implementation"
```

Follow canonicalization rules from `docs/lock-key-namespaces.md`.

#### 5d. Dependency DAG

- `wp-contracts` has no dependencies (root)
- Implementation packages depend on `wp-contracts`
- `wp-integration` depends on all implementation packages

#### 5e. Verification Steps

Assign verification tier per package: Tier A (full), Tier B (CI), Tier C (static).

### 6. Validate All Artifacts [all tiers]

**Sequential tier:**
```bash
openspec validate <change-id> --strict
```

**Local-parallel+ tiers** (additionally):
```bash
skills/.venv/bin/python "<skill-base-dir>/../validate-packages/scripts/validate_work_packages.py" \
  openspec/changes/<change-id>/work-packages.yaml

skills/.venv/bin/python "<skill-base-dir>/../refresh-architecture/scripts/parallel_zones.py" \
  --validate-packages openspec/changes/<change-id>/work-packages.yaml --json
```

Fix any validation errors before proceeding.

### 7. Register Resource Claims [coordinated only]

**Skip unless TIER is "coordinated" and CAN_LOCK=true.**

Pre-register resource claims with the coordinator:

```
For each package in work-packages.yaml:
  For each lock key in package.locks.keys:
    acquire_lock(file_path=key, reason="planned: <feature-id>/<package-id>", ttl_minutes=0)
```

Use `ttl_minutes=0` for planning claims -- they signal intent without expiring.

### 8. Commit, Push, and Pin Worktree [all tiers]

```bash
git add openspec/changes/<change-id>/
git commit -m "plan: <change-id> -- proposal, design, specs, tasks$([ "$TIER" != "sequential" ] && echo ", contracts, work-packages")"
git push -u origin openspec/<change-id>

python3 "<skill-base-dir>/../worktree/scripts/worktree.py" pin "<change-id>"
```

### 9. Present for Approval [all tiers]

Share the proposal:
- `proposal.md` -- What and why
- `design.md` -- How (if applicable)
- `tasks.md` -- Implementation plan

**Additional for local-parallel+ tiers:**
- `contracts/` -- Machine-readable interfaces
- `work-packages.yaml` -- Execution plan with DAG

If `CAN_HANDOFF=true`, write completion handoff.

**STOP HERE -- Wait for approval before proceeding to implementation.**

## Output

- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/design.md`
- `openspec/changes/<change-id>/tasks.md`
- `openspec/changes/<change-id>/specs/**/spec.md`
- `openspec/changes/<change-id>/contracts/` (local-parallel+ only)
- `openspec/changes/<change-id>/work-packages.yaml` (local-parallel+ only)

## Context Slicing for Implementation

When `/implement-feature` dispatches work packages, each agent receives only the context it needs:

| Package Type | Context Slice |
|-------------|---------------|
| `wp-contracts` | `proposal.md` + spec deltas + contract templates |
| Backend packages | `design.md` (backend section) + `contracts/openapi/` + package scope |
| Frontend packages | `design.md` (frontend section) + `contracts/generated/types.ts` + package scope |
| `wp-integration` | Full `work-packages.yaml` + all contract artifacts |

## Next Step

After approval:
```
/implement-feature <change-id>
```
