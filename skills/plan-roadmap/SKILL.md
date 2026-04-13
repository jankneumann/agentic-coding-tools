---
name: plan-roadmap
description: "Decompose long markdown proposals into prioritized OpenSpec change candidates with dependency DAG"
category: Planning
tags: [roadmap, decomposition, planning]
triggers:
  - "plan-roadmap"
  - "plan roadmap"
  - "decompose proposal"
---

# Plan Roadmap

Decompose a long-form markdown proposal into a prioritized set of OpenSpec change candidates, each with a dependency DAG, effort estimate, and acceptance outcomes. Produces a `roadmap.yaml` artifact and optionally scaffolds the approved changes as OpenSpec change directories.

## Arguments

`$ARGUMENTS` - Path to a markdown proposal file, or inline proposal text.

## Input

A long markdown proposal containing:
- **Capabilities / Features**: sections describing what the system should do (identified by headings, bullet lists, or explicit "capability" / "feature" markers)
- **Constraints**: non-functional requirements, limits, or invariants (identified by "constraint", "requirement", "must", "shall" markers)
- **Phases / Milestones**: temporal groupings that suggest ordering (identified by "phase", "milestone", "stage", "step" headings)

The proposal may be provided as a file path or pasted inline.

## Output

- `roadmap.yaml` conforming to the roadmap schema (`openspec/changes/roadmap-openspec-orchestration/contracts/roadmap.schema.json`)
- Each item in the roadmap has: `item_id`, `title`, `description`, `effort`, `priority`, `depends_on`, `acceptance_outcomes`
- Dependency DAG is acyclic (validated before output)

## Steps

### 1. Read Proposal

Load the markdown proposal from the provided path or accept inline text. Validate that it contains the minimum required sections (at least one identifiable capability or feature).

### 2. Extract Capabilities and Phases

Parse the markdown structure to identify:
- Individual capabilities/features (from headings and structured lists)
- Constraints that apply globally or to specific capabilities
- Phase/milestone boundaries that suggest ordering

This step is deterministic -- it uses structural markdown parsing (headings, lists, markers), not LLM inference.

### 3. Build Candidate Items with Size Validation

Create `RoadmapItem` objects for each extracted capability. Then validate sizing:
- **Merge undersized items**: items estimated below the minimum effort threshold (e.g., two XS items covering related functionality are merged into one S item)
- **Split oversized items**: items spanning multiple independent systems or capabilities are split into separate items

### 4. Generate Dependency DAG

Infer dependency edges between items based on:
- Explicit ordering from phases/milestones
- Keyword references between items (one item mentioning another's key terms)
- Constraint propagation (infrastructure items before feature items)

Validate the resulting DAG is acyclic.

### 5. Present Candidates for User Approval

Display the candidate roadmap items with their dependencies, effort estimates, and acceptance outcomes. Allow the user to approve, modify, or reject individual items.

### 6. Scaffold Approved Changes as OpenSpec Change Directories

For each approved item, create an OpenSpec change directory under `openspec/changes/` containing:
- `proposal.md` with a `parent_roadmap` field linking back to the roadmap
- `tasks.md` skeleton
- `specs/` directory

## Runtime Reference

Shared models and utilities are in `skills/roadmap-runtime/scripts/`. The decomposer imports `Roadmap`, `RoadmapItem`, `Effort`, `ItemStatus`, and related types from the runtime's `models` module.
