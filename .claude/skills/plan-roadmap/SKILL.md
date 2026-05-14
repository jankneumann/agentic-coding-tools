---
name: plan-roadmap
description: "Decompose a proposal into prioritized OpenSpec change candidates with a dependency DAG. Scaffolds a proposal first if none exists."
category: Planning
tags: [roadmap, decomposition, planning]
triggers:
  - "plan-roadmap"
  - "plan roadmap"
  - "decompose proposal"
---

# Plan Roadmap

Decompose a long-form markdown proposal into a prioritized set of OpenSpec change candidates, each with a dependency DAG, effort estimate, and acceptance outcomes. Produces a `roadmap.yaml` artifact and optionally scaffolds the approved changes as OpenSpec change directories.

When no proposal yet exists, the skill scaffolds one from the template at `openspec/schemas/roadmap/templates/proposal.md` so the operator (or the agent itself, in `--draft` mode) can fill it in before decomposition.

## Arguments

`$ARGUMENTS` accepts three invocation forms:

1. **Decompose existing proposal** — `<path-to-proposal.md>`
   Decompose the proposal at the given path. The path may be inside or outside `openspec/roadmaps/`.

2. **Scaffold a blank proposal** — `--new <slug> "<short pitch>"`
   Copy the proposal template to `openspec/roadmaps/<slug>/proposal.md`, pre-filling the title and Motivation section from the pitch. Exit with a "now edit and re-run" message. The slug becomes the `roadmap_id`.

3. **Scaffold an LLM-drafted proposal** — `--new <slug> "<short pitch>" --draft`
   Same as form 2, but the agent expands the pitch into a full draft (Capabilities, Constraints, Phases) using its own reasoning rather than leaving placeholders. The operator still reviews before re-running for decomposition.

Optional flags:
- `--workspace <path>` — Override the default output workspace (default: `openspec/roadmaps/<roadmap_id>/`).
- `--force` — Overwrite an existing `roadmap.yaml` at the target. Without this, `/plan-roadmap` aborts on collision to protect operator edits to `status` / `priority`.

## Agent as the LLM

This skill runs inside Claude Code, which already has direct access to a model. **Do not call out to external LLM APIs** (Anthropic SDK, OpenAI, etc.) — the agent IS the LLM consumer. The Python scripts handle deterministic structural work (parsing, table extraction, archive cross-check, schema validation, file I/O); the agent itself does the semantic work (capability classification, dependency inference, draft proposal expansion) directly through its own reasoning.

The legacy `semantic_decomposer.py` and `llm_client.py` modules date from the external-API era and are pending removal. New work should follow the agent-as-LLM pattern documented in the steps below.

## Output

- `openspec/roadmaps/<roadmap_id>/roadmap.yaml` conforming to the roadmap schema
- `openspec/roadmaps/<roadmap_id>/proposal.md` co-located with the roadmap (when scaffolded via `--new`)
- Each item in the roadmap has: `item_id`, `title`, `description`, `effort`, `priority`, `depends_on`, `acceptance_outcomes`
- Dependency DAG is acyclic (validated before output)

### Workspace Layout

```
openspec/roadmaps/
├── <roadmap-id>/             # active workspace (this skill's output)
│   ├── proposal.md
│   ├── roadmap.yaml
│   ├── checkpoint.json       # written later by /autopilot-roadmap
│   ├── learnings/            # written later by /autopilot-roadmap
│   └── learning-log.md
└── archive/
    └── <YYYY-MM-DD>-<roadmap-id>/   # written by /archive-roadmap
```

This layout makes the workspace a self-contained unit and supports multiple concurrent roadmaps per repo without filename collisions — the directory itself is the namespace. Mirrors the OpenSpec `openspec/changes/<change-id>/` convention.

Scaffolded per-item change directories remain at `openspec/changes/<change-id>/` (consumed by `/implement-feature`); they are not nested under the roadmap workspace.

## Proposal Requirements

The decomposer's contract requires the proposal to contain these H2 sections (the template at `openspec/schemas/roadmap/templates/proposal.md` provides the canonical layout):

| Section | Required? | Purpose |
|---|---|---|
| `## Motivation` | Yes | Why this epic exists. Read by reviewers, not by the decomposer. |
| `## Capabilities` | Yes | One H3 per capability. Each H3 becomes a candidate roadmap item. Acceptance outcomes go in a `**Acceptance Outcomes:**` bulleted list under the H3. |
| `## Constraints` | Recommended | Non-functional requirements using "must" / "shall" markers. |
| `## Phases` | Optional | Temporal grouping for dependency inference. Omit if all capabilities are independent. |
| `## Out of Scope` | Recommended | Explicit exclusions to prevent decomposer drift. |

Capability H3 names should use vocabulary the structural extractor recognizes — `Capability:`, `Service:`, `Adapter:`, `Pipeline:`, `Workspace:`, `Handler:`, etc. The full keyword set lives in `decomposer.py::_CAPABILITY_MARKERS`. When in doubt, lead with one of those nouns.

## Steps

### 0. Resolve Invocation Mode

Parse `$ARGUMENTS` to determine which form was used:

- **`--new <slug> "<pitch>"`** without `--draft`: copy the template file to `openspec/roadmaps/<slug>/proposal.md`, replace the `<Epic Title>` placeholder with a slug-derived title, replace the `<motivation prose>` placeholder with the pitch. Print the path and exit with "edit the proposal and re-run `/plan-roadmap openspec/roadmaps/<slug>/proposal.md`."
- **`--new <slug> "<pitch>" --draft`**: same scaffold, but the agent expands the pitch into full Capabilities, Constraints, and Phases sections using its own reasoning, then writes the result. Print the path and exit with "review the draft and re-run for decomposition."
- **`<path>`** (existing proposal): proceed to Step 1.

For `--new` modes: if `openspec/roadmaps/<slug>/` already exists, abort unless `--force` is set.

### 1. Read Proposal and Validate Readiness

Load the markdown proposal from the provided path. Run `validate_proposal()` from `decomposer.py` to check minimum structural requirements (has headings, has at least one capability marker). If validation fails, abort with the error list and a pointer to the template — do not attempt to decompose a malformed proposal.

### 2. Extract Structural Signals (Deterministic)

Run `decompose()` from `decomposer.py` to extract structural signals from the proposal:
- Capability candidates from H2/H3 sections matching `_CAPABILITY_MARKERS`
- Priority table rows
- Phase / milestone boundaries
- Constraint markers
- Archive cross-check (items matching archived OpenSpec change IDs)

These are **inputs to the agent's semantic analysis**, not the final answer. The deterministic pass is well-suited to structurally regular content (tables, fenced code awareness, archive matching) and brittle on prose vocabulary that doesn't match its keyword set.

### 3. Detect Thin Extraction

Call `diagnose_thin_output(proposal_text, len(extracted_items))` from `decomposer.py`. If the helper returns a non-None message, the structural pass produced suspiciously few items relative to the proposal's H2 count — usually a vocabulary mismatch.

**This is a hard stop.** Surface the diagnostic to the operator and ask whether to:
- Edit the proposal to use recognized capability vocabulary (preferred).
- Proceed with agent-driven extraction in Step 4 anyway (the agent reads the full proposal and produces capabilities directly).
- Abort.

Do NOT silently continue with a thin candidate set, and do NOT route around the decomposer by hand-authoring `roadmap.yaml` — that hides the regression.

### 4. Agent-Driven Semantic Extraction

The agent reads the full proposal and produces the canonical capability list using its own reasoning. The deterministic signals from Step 2 are inputs (table rows, archive matches, phase ordering) that the agent reconciles with what it sees in the proposal. The agent is responsible for:
- Identifying every capability the proposal intends, including those the structural pass missed.
- Writing clear `description` and `rationale` for each item.
- Extracting `acceptance_outcomes` from per-capability bullet lists.
- Assigning `effort` (XS/S/M/L/XL) and initial `priority`.

### 5. Generate Dependency DAG

The agent infers dependencies between items based on:
- Explicit ordering from phases/milestones
- Keyword references between items (one item's description mentions another's key terms)
- Constraint propagation (infrastructure items before feature items)
- Scope overlap (when items touch the same files / locks)

Validate the resulting DAG is acyclic before persisting (`Roadmap.has_cycle()` returns False).

### 6. Present Candidates for User Approval

Display the candidate roadmap items with their dependencies, effort estimates, and acceptance outcomes. Allow the operator to approve, modify, or reject individual items before persistence.

### 7. Resolve Workspace Path and Write `roadmap.yaml`

Determine the output location:
- If `--workspace <path>` was supplied, use it (directory → `<path>/roadmap.yaml`, or explicit `.yaml` file path).
- Otherwise, default to `openspec/roadmaps/<roadmap_id>/roadmap.yaml`.

Print the resolved path, then call `save_roadmap(roadmap, path, overwrite=<force_flag>)` from `skills/roadmap-runtime/scripts/models.py`. The helper creates parent directories and raises `FileExistsError` on collision unless `overwrite=True`. On collision, surface the error verbatim and instruct the operator to re-invoke with `--force` or `--workspace`.

If `--new` was used in Step 0, the proposal.md already lives at `openspec/roadmaps/<roadmap_id>/proposal.md` — leave it in place. If decomposing an existing proposal from elsewhere, optionally copy or reference it from the workspace; the `source_proposal` field in `roadmap.yaml` records the original path either way.

### 8. Scaffold Approved Changes as OpenSpec Change Directories

For each approved item, create an OpenSpec change directory under `openspec/changes/` containing:
- `proposal.md` with a `parent_roadmap` field linking back to the roadmap
- `tasks.md` skeleton
- `specs/` directory

These directories always live at `openspec/changes/<change-id>/` — they are not nested under the roadmap workspace, because `/implement-feature` expects that canonical path.

## Lifecycle

```
Ingestion:     pitch / proposal.md  →  roadmap.yaml      (this skill)
Execution:     roadmap.yaml         →  item completion   (/autopilot-roadmap)
Maintenance:   roadmap.yaml         →  roadmap.md        (renderer; check_roadmap_sync)
Archival:      workspace/           →  archive/<date>-<id>/  (/archive-roadmap)
```

Generated sections of any rendered markdown view are wrapped in `<!-- GENERATED: begin/end -->` markers. Human-authored prose outside markers is preserved across re-renders.

## Runtime Reference

Shared models and utilities are in `skills/roadmap-runtime/scripts/`. The decomposer imports `Roadmap`, `RoadmapItem`, `Effort`, `ItemStatus`, `DepEdge`, `Scope`, and related types from the runtime's `models` module.

## Known Stress Test Inputs

- `docs/perplexity-feedback.md` (from `agentic-assistant` repo): 438-line proposal with priority tables, nested sub-sections, inline YAML examples, and mixed narrative. Hand-authored oracle at `openspec/roadmap.yaml` has 22 items (3 archived, 19 candidates). Run regression: `skills/.venv/bin/python -m pytest skills/tests/plan-roadmap/test_decomposer_semantic.py::TestOracleRegression -v`
