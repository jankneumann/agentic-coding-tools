---
name: parallel-plan-feature
description: Create OpenSpec proposal with contracts and work-packages for multi-agent parallel implementation
category: Git Workflow
tags: [openspec, planning, proposal, parallel, contracts, work-packages]
triggers:
  - "parallel plan feature"
  - "parallel plan"
  - "plan parallel feature"
requires:
  coordinator:
    required: [CAN_DISCOVER, CAN_QUEUE_WORK, CAN_LOCK]
    safety: [CAN_GUARDRAILS]
    enriching: [CAN_HANDOFF, CAN_MEMORY, CAN_POLICY, CAN_AUDIT]
---

# Parallel Plan Feature

Create an OpenSpec proposal with contract-first artifacts and a `work-packages.yaml` for multi-agent parallel implementation. Degrades to linear-plan-feature behavior when the coordinator is unavailable.

## Arguments

`$ARGUMENTS` - Feature description (e.g., "add user authentication with OAuth2")

## Prerequisites

- OpenSpec CLI installed (v1.0+)
- Coordinator available with required capabilities (`CAN_DISCOVER`, `CAN_QUEUE_WORK`, `CAN_LOCK`)
- Architecture artifacts current (`make architecture`)

## Coordinator Capability Check

At skill start, detect coordinator capabilities:

```
REQUIRED (hard failure without coordinator):
  CAN_DISCOVER  — discover_agents() for cross-feature conflict detection
  CAN_QUEUE_WORK — submit_work() for work package dispatch
  CAN_LOCK — acquire_lock() for resource claim registration

REQUIRED (safety):
  CAN_GUARDRAILS — check_guardrails() for destructive operation detection

ENRICHING (degrades gracefully):
  CAN_HANDOFF — write_handoff() for session continuity
  CAN_MEMORY — remember()/recall() for procedural memories
  CAN_POLICY — check_policy() for authorization decisions
  CAN_AUDIT — query_audit() for audit trail
```

If required capabilities are unavailable, degrade to `/linear-plan-feature` behavior and emit a warning.

## Steps

### 0. Detect Coordinator and Read Handoff

Run the coordination detection preamble from `docs/coordination-detection-template.md`.

If `CAN_HANDOFF=true`, read latest handoff context.
If `CAN_MEMORY=true`, recall relevant planning memories.
If coordinator is unavailable, delegate to `/linear-plan-feature $ARGUMENTS`.

### 1. Verify Clean State

```bash
git pull origin main
git status
```

Resolve any uncommitted changes before proceeding.

### 2. Gather Context (Parallel Exploration)

Launch parallel Task(Explore) agents to gather context from multiple sources:

- Read `openspec/project.md` for project purpose and conventions
- Run `openspec list --specs` for existing specifications
- Run `openspec list` for in-progress changes that might conflict
- Search codebase for existing implementations related to the feature
- Read `docs/architecture-analysis/architecture.summary.json` for component inventory
- Read `docs/architecture-analysis/parallel_zones.json` for safe parallel zones

**Context Synthesis**: Wait for all results, synthesize into unified context summary with project constraints, existing patterns, potential conflicts, and available parallel zones.

### 3. Scaffold Proposal

Create standard OpenSpec change directory and artifacts:

```bash
openspec new change "<change-id>"
```

Generate in dependency order:
1. `proposal.md` — What and why (from user description + context)
2. `design.md` — Architectural decisions, alternatives, risks
3. `specs/**/spec.md` — Requirement deltas (SHALL/MUST statements)
4. `tasks.md` — Implementation plan with dependency tracking

### 4. Generate Contracts

Produce machine-readable interface definitions in `contracts/`. This is the key differentiator from linear planning — contracts become the coordination boundary between parallel agents.

#### 4a. OpenAPI Contracts

For API features, generate from the template at `openspec/schemas/feature-workflow/templates/openapi-stub.yaml`:

```yaml
contracts/
  openapi/
    v1.yaml          # OpenAPI 3.1.0 spec with paths, schemas, examples
```

Requirements:
- Every endpoint has request/response schemas with `example` fields
- Discriminator fields for polymorphic responses
- Error response schemas following RFC 7807

#### 4b. Database Contracts

For features touching the database:

```yaml
contracts/
  db/
    schema.sql        # CREATE TABLE / ALTER TABLE statements
    seed.sql          # Test fixture data
```

#### 4c. Event Contracts

For features with async communication:

```yaml
contracts/
  events/
    user.created.schema.json    # JSON Schema for event payload
```

#### 4d. Type Generation Stubs

Generate type stubs from contracts for consuming packages:

```yaml
contracts/
  generated/
    models.py         # Pydantic models from OpenAPI schemas
    types.ts          # TypeScript interfaces from OpenAPI schemas
```

### 5. Generate Work Packages

Decompose tasks into agent-scoped work packages in `work-packages.yaml`. Follow the schema at `openspec/schemas/work-packages.schema.json`.

#### 5a. Package Decomposition

Group tasks by architectural boundary:
- `wp-contracts` — Generate/validate contracts (always first, priority 1)
- `wp-<backend-module>` — Backend implementation per bounded context
- `wp-<frontend-module>` — Frontend implementation per component group
- `wp-integration` — Merge worktrees and run full test suite (always last)

#### 5b. Scope Assignment

For each package, declare explicit file scope:

```yaml
scope:
  write_allow:
    - "src/api/**"        # Files this package may modify
    - "tests/api/**"
  read_allow:
    - "src/**"            # Files this package may read
    - "contracts/**"
  deny:
    - "src/frontend/**"   # Files this package must NOT touch
```

**Rule**: Parallel packages MUST have non-overlapping `write_allow` scopes.

#### 5c. Lock Declaration

For each package, declare resource claims:

```yaml
locks:
  files:
    - "src/api/users.py"           # Exclusive file locks
  keys:
    - "api:GET /v1/users"          # Logical endpoint locks
    - "db:schema:users"            # Schema locks
    - "event:user.created"         # Event channel locks
  ttl_minutes: 120
  reason: "Backend API implementation"
```

Follow canonicalization rules from `docs/lock-key-namespaces.md`.

#### 5d. Dependency DAG

Compute the package dependency graph:
- `wp-contracts` has no dependencies (root)
- Implementation packages depend on `wp-contracts`
- `wp-integration` depends on all implementation packages

#### 5e. Verification Steps

Assign verification tier per package:
- Tier A (full): Unit tests + integration tests + linting
- Tier B (CI): Delegated to CI pipeline
- Tier C (static): Linting and schema validation only

### 6. Validate All Artifacts

```bash
# Validate OpenSpec artifacts
openspec validate <change-id> --strict

# Validate work-packages.yaml against schema
scripts/.venv/bin/python scripts/validate_work_packages.py \
  openspec/changes/<change-id>/work-packages.yaml

# Validate parallel safety (scope + lock non-overlap)
scripts/.venv/bin/python scripts/parallel_zones.py \
  --validate-packages openspec/changes/<change-id>/work-packages.yaml --json
```

Fix any validation errors before proceeding.

### 7. Register Resource Claims

**Coordinator-dependent step** (requires `CAN_LOCK`).

Pre-register resource claims with the coordinator so other features can detect conflicts:

```
For each package in work-packages.yaml:
  For each lock key in package.locks.keys:
    acquire_lock(file_path=key, reason="planned: <feature-id>/<package-id>", ttl_minutes=0)
```

Use `ttl_minutes=0` for planning claims — they signal intent without expiring.

### 8. Present for Approval

Share the full proposal with stakeholders:
- `proposal.md` — What and why
- `design.md` — How and trade-offs
- `contracts/` — Machine-readable interfaces
- `work-packages.yaml` — Execution plan with DAG visualization
- Validation results from Step 6

If `CAN_HANDOFF=true`, write completion handoff with:
- Completed planning artifacts
- Key decisions and assumptions
- Resource claims registered
- Recommended next: `/parallel-implement-feature <change-id>` after approval

**STOP HERE — Wait for approval before proceeding to implementation.**

## Output

- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/design.md`
- `openspec/changes/<change-id>/tasks.md`
- `openspec/changes/<change-id>/specs/**/spec.md`
- `openspec/changes/<change-id>/contracts/` (OpenAPI, types, mocks, schemas)
- `openspec/changes/<change-id>/work-packages.yaml`

## Context Slicing for Implementation

When `/parallel-implement-feature` dispatches work packages, each agent receives only the context it needs:

| Package Type | Context Slice |
|-------------|---------------|
| `wp-contracts` | `proposal.md` + spec deltas + contract templates |
| Backend packages | `design.md` (backend section) + `contracts/openapi/` + package scope |
| Frontend packages | `design.md` (frontend section) + `contracts/generated/types.ts` + package scope |
| `wp-integration` | Full `work-packages.yaml` + all contract artifacts |

This prevents context window bloat and keeps each agent focused on its bounded context.

## Next Step

After proposal approval:
```
/parallel-implement-feature <change-id>
```
