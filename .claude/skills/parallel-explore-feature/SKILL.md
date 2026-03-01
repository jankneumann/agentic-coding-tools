---
name: parallel-explore-feature
description: Identify high-value next features with resource claim analysis for parallel feasibility
category: Git Workflow
tags: [openspec, discovery, architecture, prioritization, parallel]
triggers:
  - "parallel explore feature"
  - "parallel explore"
  - "explore parallel feature"
requires:
  coordinator:
    required: [CAN_DISCOVER, CAN_LOCK]
    safety: [CAN_GUARDRAILS]
    enriching: [CAN_HANDOFF, CAN_MEMORY, CAN_POLICY, CAN_AUDIT]
---

# Parallel Explore Feature

Analyze the codebase and coordinator state to recommend features suitable for multi-agent parallel implementation. Extends `linear-explore-feature` with resource claim analysis and feasibility assessment.

## Arguments

`$ARGUMENTS` - Optional focus area (e.g., "performance", "API layer", "frontend", "security")

## Prerequisites

- OpenSpec CLI installed (v1.0+)
- Architecture artifacts current (`make architecture`)
- Coordinator available with `CAN_DISCOVER` and `CAN_LOCK` capabilities

## Coordinator Capability Check

```
REQUIRED:
  CAN_DISCOVER  — discover_agents() for active feature and claim enumeration
  CAN_LOCK      — check_locks() for current lock state inspection

SAFETY:
  CAN_GUARDRAILS — pre-check candidate descriptions for destructive patterns

ENRICHING:
  CAN_MEMORY   — recall previous exploration and feature decisions
  CAN_HANDOFF  — read/write exploration context across sessions
  CAN_POLICY   — check agent permissions for candidate scope
  CAN_AUDIT    — log exploration decisions for traceability
```

If coordinator is unavailable, degrade to `linear-explore-feature` behavior without resource analysis.

## Steps

### 0. Detect Coordinator

Run the coordination detection preamble from `docs/coordination-detection-template.md`.

If `CAN_MEMORY=true`, recall relevant history:
- Tags: `["feature-discovery", "<focus-area>"]`

If `CAN_HANDOFF=true`, read latest exploration handoff.

### 1. Gather Architecture Context

Identical to `linear-explore-feature` Step 1. Use parallel Task(Explore) agents:

- Read `openspec/project.md` for project purpose and conventions
- Read `docs/architecture-analysis/architecture.summary.json` for module inventory
- Read `docs/architecture-analysis/parallel_zones.json` for independent modification zones
- List active OpenSpec changes via `openspec list`
- Scan for TODO/FIXME/HACK markers in source code

### 2. Enumerate Active Resource Claims

**Coordinator-dependent step** (requires `CAN_DISCOVER` and `CAN_LOCK`).

- Call `check_locks()` to get all active file and logical locks
- Call `discover_agents()` to enumerate in-flight features and their claimed resources
- Build a resource occupation map: which files, API endpoints, DB schemas, and events are currently claimed

If coordinator is unavailable, skip this step and note "resource analysis unavailable" in output.

### 3. Assess Parallel Feasibility

For each candidate feature from Step 1:

1. **Estimate scope**: Identify likely files, API endpoints, DB tables, and events the feature would touch
2. **Check lock overlap**: Compare estimated scope against the resource occupation map from Step 2
3. **Classify feasibility**:
   - `FULL` — No resource overlap with in-flight features; safe for full parallel execution
   - `PARTIAL` — Some overlap; can run in parallel with serialized access to shared resources
   - `SEQUENTIAL` — Heavy overlap; must wait for in-flight features to complete

### 4. Rank and Present Candidates

Produce a ranked shortlist with:

| Field | Description |
|-------|-------------|
| Candidate | Feature description |
| Value | Business/technical value assessment |
| Complexity | S/M/L estimate |
| Parallel Feasibility | `FULL` / `PARTIAL` / `SEQUENTIAL` |
| Resource Conflicts | List of overlapping locks (if any) |
| Recommended Workflow | `parallel-plan-feature` or `linear-plan-feature` |
| Independent Zones | Which `parallel_zones.json` groups are available |

### 5. Write Handoff

If `CAN_HANDOFF=true`, write exploration context:
- Candidates discovered with feasibility ratings
- Current resource occupation snapshot
- Recommended next command for top candidate

## Output

- Ranked candidate shortlist with parallel feasibility assessment
- Resource conflict analysis for each candidate
- Recommended workflow (parallel vs linear) per candidate

## Next Step

For the selected candidate:
```
/parallel-plan-feature <description>   # If feasibility is FULL or PARTIAL
/linear-plan-feature <description>     # If feasibility is SEQUENTIAL
```
