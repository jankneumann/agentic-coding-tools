# Design: Roadmap-Oriented OpenSpec Planning and Execution

## Overview

This change introduces two orchestration skills that sit above existing single-change workflows:

1. **plan-roadmap**: parse and decompose long strategic markdown into a roadmap DAG of OpenSpec changes.
2. **autopilot-roadmap**: execute roadmap DAG items iteratively using existing implementation/review skills, while feeding learnings forward.

## Decision Log

- **D1: Orchestrator-over-rewrite architecture** — New roadmap skills orchestrate existing skills instead of modifying every skill deeply.
- **D2: Filesystem-first durable state** — Roadmap progress is persisted under each change to support context reload and interruption recovery.
- **D3: Policy-driven vendor routing** — Limit handling is configuration-driven (wait vs switch), with telemetry captured for trade-off tuning.
- **D4: Progressive context loading** — Each phase loads only bounded artifacts (roadmap state + current item + recent learning entries).

## Artifacts

- `roadmap.yaml`: ordered roadmap items with dependency edges and status.
- `checkpoint.json`: current phase pointer and completed phase history.
- `learning-log.md`: decision and retrospective summary per executed item.

## Execution Flow

1. `plan-roadmap` builds candidate list and dependency DAG from proposal.
2. User approves roadmap items.
3. `autopilot-roadmap` selects next ready item.
4. Existing implementation/review skills run for that item.
5. Learnings and metrics are persisted.
6. Remaining roadmap items are re-ranked/reworded based on new constraints.
7. Loop until roadmap complete or paused.

## Risk Mitigations

- **Risk**: Over-decomposition into too many tiny changes.
  - **Mitigation**: enforce minimum change granularity heuristic and manual approval gate.
- **Risk**: Vendor switching increases quality variance.
  - **Mitigation**: use role-based dispatch and keep parallel review as final quality equalizer.
- **Risk**: Artifact drift between disk and coordinator state.
  - **Mitigation**: coordinator optional, file artifacts remain canonical fallback.
