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

Optional flags:
- `--workspace <path>` - Override the default output location. If `<path>` is a directory, the roadmap is written to `<path>/roadmap.yaml`; if `<path>` ends in `.yaml`, it is used as the explicit file path.
- `--force` - Overwrite an existing `roadmap.yaml` at the target location. Without this flag, `/plan-roadmap` aborts on collision to protect operator edits (`status`, `priority`, etc.).

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

### Output Location

The default workspace is `openspec/roadmaps/<roadmap_id>/roadmap.yaml`, where `<roadmap_id>` is derived from the proposal during decomposition (Pass 2). The parent directory is created automatically.

This convention lets `/autopilot-roadmap <workspace>` consume the result without manual relocation, and supports multiple concurrent roadmaps (one per epic) in the same repo without filename collisions — the workspace directory itself is the namespace.

**Collision behavior**: if `roadmap.yaml` already exists at the target, `/plan-roadmap` aborts with guidance to either pass `--force` (overwrite) or `--workspace <path>` (redirect). This protects operator edits to item `status` / `priority` from being silently clobbered when re-running the skill on the same proposal.

**Caveat**: because `<roadmap_id>` is set during decomposition, the final destination path is only known after Pass 2 completes. The skill prints the resolved path before writing.

Scaffolded per-item change directories remain at `openspec/changes/<change-id>/` (consumed by `/implement-feature`); they are not nested under the roadmap workspace.

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

### 6. Resolve Workspace Path and Write `roadmap.yaml`

Determine the output location:
- If `--workspace <path>` was supplied, use it (directory → `<path>/roadmap.yaml`, or explicit `.yaml` file path).
- Otherwise, default to `openspec/roadmaps/<roadmap_id>/roadmap.yaml` (relative to repo root).

Print the resolved path, then call `save_roadmap(roadmap, path, overwrite=<force_flag>)` from `skills/roadmap-runtime/scripts/models.py`. The helper creates parent directories and raises `FileExistsError` on collision unless `overwrite=True`. On collision, surface the error verbatim and instruct the user to re-invoke with `--force` or `--workspace`.

### 7. Scaffold Approved Changes as OpenSpec Change Directories

For each approved item, create an OpenSpec change directory under `openspec/changes/` containing:
- `proposal.md` with a `parent_roadmap` field linking back to the roadmap
- `tasks.md` skeleton
- `specs/` directory

These directories always live at `openspec/changes/<change-id>/` — they are not nested under the roadmap workspace, because `/implement-feature` expects that canonical path.

## Two-Pass Architecture

The decomposer supports two execution modes, selected automatically based on LLM client availability:

### Structural-only mode (no LLM)

When no LLM vendor is configured (no `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GOOGLE_API_KEY` in environment), the decomposer uses deterministic parsing only. This is the original behavior, enhanced with:
- Fenced code block awareness (headings inside code blocks are ignored)
- Priority table extraction (each table row becomes a candidate)
- Sub-section propagation (H4/H5 children inherit parent capability classification)
- Clean ID generation (kebab-case, no `ri-` prefix)
- Archive cross-check (items matching archived change IDs get `status: completed`)

### Semantic mode (LLM available)

When an LLM vendor is available, the decomposer uses a four-pass architecture:

1. **Pass 1 — Structural scan**: Enhanced deterministic parsing builds a candidate pool of text blocks.
2. **Pass 2 — Semantic classification**: Single batch LLM call classifies each candidate as yes/no/merge, extracts clean IDs, descriptions, and acceptance outcomes.
3. **Pass 3 — Two-tier dependency inference**:
   - **Tier A** (deterministic): When both items declare `scope` (write_allow, read_allow, lock_keys), edges are added based on glob/lock overlap.
   - **Tier B-0** (cheap pruning): Skip LLM dispatch for obviously-independent pairs.
   - **Tier B** (LLM analyst): Batched LLM calls infer functional dependencies with conservative policy (unclear/low-confidence → keep edge).
4. **Pass 4 — Validation**: Archive cross-check, confidence-aware cycle breaking, path normalization.

Every dependency edge carries `source` (deterministic/llm/split/explicit), `rationale`, and optional `confidence` for auditability via the `DepEdge` dataclass.

## Roadmap Renderer

The renderer provides the maintenance direction of the lifecycle:

```
Ingestion:    proposal.md  →  roadmap.yaml   (decomposer)
Maintenance:  roadmap.yaml →  roadmap.md     (renderer)
```

Generated sections are wrapped in `<!-- GENERATED: begin/end -->` markers. Human-authored prose (introduction, guiding principles, cross-cutting themes, out-of-scope notes) outside markers is preserved across re-renders.

Use `check_roadmap_sync(yaml_path, md_path)` to verify the markdown is up-to-date with the YAML (CI check mode).

## Known Stress Test Inputs

- `docs/perplexity-feedback.md` (from `agentic-assistant` repo): 438-line proposal with priority tables (§5), nested sub-sections (§3.x, §7.x), inline YAML examples, and mixed narrative. The hand-authored oracle at `openspec/roadmap.yaml` has 22 items (3 archived, 19 candidates). Run regression tests: `skills/.venv/bin/python -m pytest skills/tests/plan-roadmap/test_decomposer_semantic.py::TestOracleRegression -v`

## Runtime Reference

Shared models and utilities are in `skills/roadmap-runtime/scripts/`. The decomposer imports `Roadmap`, `RoadmapItem`, `Effort`, `ItemStatus`, `DepEdge`, `Scope`, and related types from the runtime's `models` module.
