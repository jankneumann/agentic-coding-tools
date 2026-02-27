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

### 1. Verify Environment

Check coordinator capabilities. If degrading to linear mode, delegate to `/linear-plan-feature`.

### 2. Gather Context (same as linear)

Use parallel Task(Explore) agents to gather context from existing specs, architecture artifacts, and code.

### 3. Scaffold Proposal

Create standard OpenSpec artifacts: `proposal.md`, `design.md`, `tasks.md`, and spec deltas.

### 4. Generate Contracts

Produce machine-readable interface definitions in `contracts/`:

- **OpenAPI specs** as the canonical contract artifact for API endpoints
- **Language-specific type generation**: Pydantic models (Python), TypeScript interfaces (frontend)
- **SQL schema definitions** for new database tables
- **Event schemas** (JSON Schema) for async communication
- **Executable mocks**: Prism-generated API stubs from the OpenAPI spec

### 5. Generate Work Packages

Decompose tasks into agent-scoped work packages in `work-packages.yaml`:

- Group tasks by architectural boundary (backend, frontend, contracts, integration)
- Declare explicit file scope (`write_allow`, `read_allow`, `deny`) per package
- Declare explicit resource claims (`locks.files`, `locks.keys`) per package
- Compute dependency DAG and validate non-overlap for parallel packages
- Set verification steps per package with appropriate tier requirements
- Validate against `openspec/schemas/work-packages.schema.json`

### 6. Validate Artifacts

```bash
# Validate OpenSpec artifacts
openspec validate <change-id> --strict

# Validate work-packages.yaml against schema
scripts/.venv/bin/python scripts/validate_work_packages.py openspec/changes/<change-id>/work-packages.yaml

# Validate parallel safety (scope + lock non-overlap)
scripts/.venv/bin/python scripts/parallel_zones.py --validate-packages openspec/changes/<change-id>/work-packages.yaml
```

### 7. Present for Approval

Present the proposal, contracts, and work packages for human approval.

## Output

- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/design.md`
- `openspec/changes/<change-id>/tasks.md`
- `openspec/changes/<change-id>/specs/**/spec.md`
- `openspec/changes/<change-id>/contracts/` (OpenAPI, generated types, mocks)
- `openspec/changes/<change-id>/work-packages.yaml`

## Next Step

After proposal approval:
```
/parallel-implement-feature <change-id>
```
