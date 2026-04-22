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

## Execution modes

The skill has two modes. **Mode A (host-assisted) is the default when invoked from Claude Code** — it uses the orchestrating agent itself to perform semantic curation, so no external LLM API key is required. Mode B (headless) calls an external vendor via `llm_client.py` and is only used by batch/CI callers like `autopilot-roadmap`.

| | Mode A — host-assisted | Mode B — headless |
|---|---|---|
| Who does semantic reasoning | The Claude Code agent running the skill | External LLM vendor (Anthropic / OpenAI / Google) |
| API key required | No | Yes (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`) |
| Billing | Single session | Double-billed (session + external API) |
| Entry point | `curator.py structural` + agent turn + `curator.py finalize` | `semantic_decomposer.decompose_semantic()` |
| Typical caller | `/plan-roadmap` from an interactive session | `autopilot-roadmap`, CI batch jobs |

## Steps (Mode A — host-assisted, default)

### 1. Run structural pass

```bash
skills/.venv/bin/python skills/plan-roadmap/scripts/curator.py structural \
  --proposal docs/proposals/<slug>.md \
  --out-dir openspec/.plan-roadmap-tmp/<slug>/
```

Writes two files into the out-dir:
- `roadmap.draft.yaml` — structural-pass Roadmap (often noisy: narrative sections captured as items, generic acceptance outcomes, unsized effort, empty dependencies).
- `curation-request.json` — per-item heuristic flags (`likely-narrative`, `generic-acceptance`, `phase-header`, …) plus the agent instructions and a suggested response path. Conforms to `skills/plan-roadmap/contracts/curation-request.schema.json`.

### 2. Curate (agent turn)

Read `curation-request.json` and write `curation-response.json` conforming to `skills/plan-roadmap/contracts/curation-response.schema.json`. For each candidate, choose `keep` (with optional overrides for `new_id`, `title`, `effort`, `priority`, `depends_on`), `drop`, or `merge` (with `merge_into`). Include a one-line `rationale` per decision.

`depends_on` entries may reference the original_id of another candidate or the new_id declared in another keep decision; IDs are normalized on apply.

### 3. Run finalize

```bash
skills/.venv/bin/python skills/plan-roadmap/scripts/curator.py finalize \
  --draft openspec/.plan-roadmap-tmp/<slug>/roadmap.draft.yaml \
  --decisions openspec/.plan-roadmap-tmp/<slug>/curation-response.json \
  --out openspec/roadmap.yaml
```

Applies decisions, re-validates the DAG (re-breaks cycles, drops dangling edges, renames IDs consistently), and writes the final schema-clean `roadmap.yaml`.

### 4. Present candidates for user approval

Display the curated roadmap items with dependencies, effort, and acceptance outcomes. The user can approve, modify, or reject individual items.

### 5. Scaffold approved changes as OpenSpec change directories

For each approved item, create an OpenSpec change directory under `openspec/changes/` containing:
- `proposal.md` with a `parent_roadmap` field linking back to the roadmap
- `tasks.md` skeleton
- `specs/` directory

## Mode B — headless (batch / autopilot only)

When no interactive agent is orchestrating, fall back to calling an external LLM vendor via `llm_client.py`. The entry point is `semantic_decomposer.decompose_semantic()`, which runs a four-pass architecture:

1. **Pass 1 — Structural scan**: Enhanced deterministic parsing builds a candidate pool of text blocks.
2. **Pass 2 — Semantic classification**: Single batch LLM call classifies each candidate as yes/no/merge, extracts clean IDs, descriptions, and acceptance outcomes.
3. **Pass 3 — Two-tier dependency inference**:
   - **Tier A** (deterministic): When both items declare `scope` (write_allow, read_allow, lock_keys), edges are added based on glob/lock overlap.
   - **Tier B-0** (cheap pruning): Skip LLM dispatch for obviously-independent pairs.
   - **Tier B** (LLM analyst): Batched LLM calls infer functional dependencies with conservative policy (unclear/low-confidence → keep edge).
4. **Pass 4 — Validation**: Archive cross-check, confidence-aware cycle breaking, path normalization.

Every dependency edge carries `source` (deterministic/llm/split/explicit), `rationale`, and optional `confidence` for auditability via the `DepEdge` dataclass.

## Structural parser capabilities (shared by both modes)

The structural pass (`decomposer.decompose`) supports:
- Fenced code block awareness (headings inside code blocks are ignored)
- Priority table extraction (each table row becomes a candidate)
- Sub-section propagation (H4/H5 children inherit parent capability classification)
- Clean ID generation (kebab-case, no `ri-` prefix)
- Archive cross-check (items matching archived change IDs get `status: completed`)

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
