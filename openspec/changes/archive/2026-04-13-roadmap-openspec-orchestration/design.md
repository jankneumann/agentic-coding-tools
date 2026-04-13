# Design: Roadmap-Oriented OpenSpec Planning and Execution

## Overview

This change adds a roadmap orchestration layer above existing single-change OpenSpec workflows.

- `plan-roadmap`: proposal decomposition + roadmap artifact generation
- `autopilot-roadmap`: item execution loop + policy routing + learning feedback
- `skills/roadmap-runtime/`: shared artifact validation, checkpointing, and context assembly

## Architecture

### Components

1. **Roadmap Runtime Library** (`skills/roadmap-runtime/scripts/`)
   - Artifact models and schema validation (against `contracts/*.schema.json`)
   - Checkpoint manager (save/restore/advance)
   - Learning-log read/write helpers with sanitization
   - Context assembly: bounded loading from root index + selective entry reads

2. **Plan Roadmap Skill** (`skills/plan-roadmap/`)
   - Decomposition analyzer
   - Candidate DAG builder with item size validation (merge undersized, split oversized)
   - OpenSpec change scaffold generator

3. **Autopilot Roadmap Skill** (`skills/autopilot-roadmap/`)
   - Ready-item selector (dependency-aware)
   - Policy engine for usage limits with cascading vendor failover
   - Delegation bridge to existing implementation/review skills
   - Adaptive replanner using learning-log deltas

### Artifact Location Model

Roadmap artifacts live under the roadmap's own OpenSpec change directory. Child changes created by decomposition are separate OpenSpec changes that reference the parent roadmap.

```
openspec/changes/<roadmap-change-id>/
  roadmap.yaml              # Roadmap items, DAG, status, policy
  checkpoint.json           # Resumable execution state
  learning-log.md           # Root index: one-line summaries per item
  learnings/                # Per-item detailed learning entries
    <item-id>.md            # Frontmatter (learning-log.schema.json) + narrative body
  proposal.md               # Standard OpenSpec proposal
  design.md                 # This file
  tasks.md                  # Implementation tasks
  work-packages.yaml        # Work package definitions
  contracts/                # Schema definitions
  specs/                    # Spec deltas
```

**Parent-child references:**
- Each child `openspec/changes/<child-change-id>/proposal.md` includes a `parent_roadmap` field linking back to the roadmap change-id and item-id
- `roadmap.yaml` items include a `change_id` field populated once the child change is scaffolded
- This bidirectional link enables cleanup (archive roadmap when all children complete) and traceability (navigate from child back to roadmap context)

**Worktree scope:** Skills operating on a roadmap item need read access to both the roadmap workspace (`openspec/changes/<roadmap-change-id>/`) and the child change being executed (`openspec/changes/<child-change-id>/`). The `read_allow` scope for implementation packages includes both paths.

### State Model

Filesystem under the roadmap change directory:
- `roadmap.yaml` → roadmap items + dependencies + status (schema: `contracts/roadmap.schema.json`)
- `checkpoint.json` → phase pointer + last successful step (schema: `contracts/checkpoint.schema.json`)
- `learning-log.md` → root index document with one-line per-item summaries
- `learnings/<item-id>.md` → detailed per-item learning entries (schema: `contracts/learning-log.schema.json`)

Coordinator memory (optional):
- phase summary mirrors artifact state for faster cloud/runtime resume

### Learning Log: Progressive Disclosure Model

The learning log is structured for **bounded context assembly**:

1. **Root index** (`learning-log.md`): One line per completed item — item-id, status, and a one-sentence summary. This file stays small regardless of roadmap length.
2. **Per-item entries** (`learnings/<item-id>.md`): YAML frontmatter with structured data (decisions, blockers, deviations, recommendations) plus a markdown body for narrative context.
3. **Context loading protocol**: Before executing item N, `autopilot-roadmap` reads the root index, identifies relevant prior items (direct dependencies + most recent 3 entries), and loads only those entries. This caps context assembly at O(k) where k is the dependency fan-in + recency window, not O(n) where n is total completed items.

**Compaction**: When the root index exceeds 50 entries, a compaction pass summarizes older entries into a `learnings/_archive.md` summary document and removes individual entry files that are no longer referenced by pending items.

### Shared Runtime Location

The shared roadmap runtime library lives at `skills/roadmap-runtime/scripts/`, following the established pattern of `skills/parallel-infrastructure/scripts/` for shared cross-skill code. Both `plan-roadmap` and `autopilot-roadmap` import from this shared location rather than duplicating runtime code in their own directories.

```
skills/
  roadmap-runtime/          # Shared library (like parallel-infrastructure/)
    scripts/
      __init__.py
      models.py             # Artifact dataclasses + validation
      checkpoint.py         # Checkpoint manager
      learning.py           # Learning-log read/write/index
      sanitizer.py          # Redaction/sanitization utilities
      context.py            # Bounded context assembly
      tests/
        test_models.py
        test_checkpoint.py
        test_learning.py
        test_sanitizer.py
        test_context.py
    SKILL.md                # Metadata-only (no user-facing workflow)
  plan-roadmap/             # User-facing decomposition skill
    scripts/
      decomposer.py         # Proposal decomposition engine
      scaffolder.py         # OpenSpec change scaffold generator
      tests/
    SKILL.md
  autopilot-roadmap/        # User-facing execution skill
    scripts/
      orchestrator.py       # Roadmap execution loop
      policy.py             # Vendor scheduling policy engine
      replanner.py          # Adaptive item reprioritization
      tests/
    SKILL.md
```

## Key Decisions

- **D1 Orchestrator-over-rewrite**: Keep existing skills intact and orchestrate them.
- **D2 Filesystem canonical state**: Disk artifacts are source of truth; coordinator state is cache.
- **D3 Policy defaults**: default wait policy to minimize cost surprises; switch policy opt-in.
- **D4 Dependency safety**: roadmap items execute only when dependencies complete.
- **D5 Progressive context loading**: load only current-item artifacts and recent learning entries. Bounded by dependency fan-in + recency window, not total item count.
- **D6 Shared runtime location**: `skills/roadmap-runtime/` follows `skills/parallel-infrastructure/` pattern. Consumer skills import, not duplicate.
- **D7 Learning log progressive disclosure**: Root index + per-item entries in `learnings/` subfolder. Compaction at 50-entry threshold.
- **D8 Artifact sanitization**: All artifact writers must sanitize before persisting. Never store credentials, tokens, raw prompts, or env var values.

## Alternatives Considered

- **Embed roadmap mode into existing skills**: rejected due to complexity concentration.
- **Coordinator-only implementation first**: rejected due to higher deployment coupling.
- **Shared runtime in consumer directories**: rejected — breaks established `skills/parallel-infrastructure/` pattern and encourages duplication.
- **Flat append-only learning log**: rejected — unbounded growth makes context assembly expensive for long roadmaps.

## Failure and Recovery Design

1. **Malformed artifacts**: validation fails fast with repair guidance and no partial execution.
2. **Usage-limit block with no alternate vendor**: roadmap moves to blocked state with explicit next action.
3. **Interrupted execution**: checkpoint resume restores to last successful phase.
4. **Dependency mismatch**: execution rejected until dependency completion recorded.
5. **Item implementation failure**: item marked `failed` in roadmap.yaml with reason; dependent items transition to `blocked` or `replan_required`; learning entry records the failure for future items.
6. **Cascading vendor failures**: after a vendor switch, if the alternate also fails, the system applies policy evaluation recursively across remaining eligible vendors up to `max_switch_attempts_per_item`. When attempts are exhausted, the item transitions to `blocked` with required operator action.

## Verification Strategy

- Unit tests for parser/validator/checkpoint manager, policy engine, and sanitizer.
- Integration tests for decomposition-to-execution handoff.
- Learning-log compaction and bounded context loading tests.
- OpenSpec strict validation before approval gate.
