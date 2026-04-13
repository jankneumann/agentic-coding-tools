# Design: Roadmap-Oriented OpenSpec Planning and Execution

## Overview

This change adds a roadmap orchestration layer above existing single-change OpenSpec workflows.

- `plan-roadmap`: proposal decomposition + roadmap artifact generation
- `autopilot-roadmap`: item execution loop + policy routing + learning feedback
- `roadmap_runtime`: shared artifact validation, checkpointing, and context assembly

## Architecture

### Components

1. **Roadmap Runtime Library**
   - Artifact models and validation
   - Checkpoint manager
   - Learning-log read/write helpers

2. **Plan Roadmap Skill**
   - Decomposition analyzer
   - Candidate DAG builder
   - OpenSpec change scaffold generator

3. **Autopilot Roadmap Skill**
   - Ready-item selector (dependency-aware)
   - Policy engine for usage limits
   - Delegation bridge to existing implementation/review skills
   - Adaptive replanner using learning-log deltas

### State Model

Filesystem under a roadmap workspace:
- `roadmap.yaml` → roadmap items + dependencies + status
- `checkpoint.json` → phase pointer + last successful step
- `learning-log.md` → append-only per-item learnings

Coordinator memory (optional):
- phase summary mirrors artifact state for faster cloud/runtime resume

## Key Decisions

- **D1 Orchestrator-over-rewrite**: Keep existing skills intact and orchestrate them.
- **D2 Filesystem canonical state**: Disk artifacts are source of truth; coordinator state is cache.
- **D3 Policy defaults**: default wait policy to minimize cost surprises; switch policy opt-in.
- **D4 Dependency safety**: roadmap items execute only when dependencies complete.
- **D5 Progressive context loading**: load only current-item artifacts and recent learning entries.

## Alternatives Considered

- **Embed roadmap mode into existing skills**: rejected due to complexity concentration.
- **Coordinator-only implementation first**: rejected due to higher deployment coupling.

## Failure and Recovery Design

1. **Malformed artifacts**: validation fails fast with repair guidance and no partial execution.
2. **Usage-limit block with no alternate vendor**: roadmap moves to blocked state with explicit next action.
3. **Interrupted execution**: checkpoint resume restores to last successful phase.
4. **Dependency mismatch**: execution rejected until dependency completion recorded.

## Verification Strategy

- Unit tests for parser/validator/checkpoint manager and policy engine.
- Integration tests for decomposition-to-execution handoff.
- OpenSpec strict validation before approval gate.
