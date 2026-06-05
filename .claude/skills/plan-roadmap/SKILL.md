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

The decomposition itself is done by a premium model: the orchestrator dispatches a generator (a Claude subagent by default, or an external vendor such as `gpt-5.5` / `gemini-3.1-pro`) that reads the **entire** proposal against an explicit output contract and returns a `roadmap.yaml`. Python's role is the deterministic backstop — proposal-readiness checks before generation, and schema / dependency / DAG validation afterwards.

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
- `--vendor <claude|codex|gemini>` — Choose the generator. Default `claude` dispatches a Claude subagent via the Agent tool. `codex` / `gemini` route through the shared CLI dispatcher to the external vendor (`gpt-5.5` / `gemini-3.1-pro`).
- `--workspace <path>` — Override the default output workspace (default: `openspec/roadmaps/<roadmap_id>/`).
- `--force` — Overwrite an existing `roadmap.yaml` at the target. Without this, `/plan-roadmap` aborts on collision to protect operator edits to `status` / `priority`.

## Generation and dispatch

The semantic work — reading the proposal and deciding what the items, dependencies, efforts, and acceptance outcomes are — is done by a premium model, never by keyword parsing. The orchestrator (the agent running this skill) **dispatches** that work rather than importing an LLM SDK:

- **Default (`--vendor claude`):** spawn a Claude subagent with the Agent tool, handing it the filled generation prompt. The subagent reads the proposal and returns the `roadmap.yaml` body.
- **External (`--vendor codex|gemini`):** route through `skills/parallel-infrastructure/scripts/review_dispatcher.py` (`ReviewOrchestrator`) using the `alternative` dispatch mode, which shells out to the vendor CLI configured in `agent-coordinator/agents.yaml`. Models resolve to `gpt-5.5` (codex) / `gemini-3.1-pro` (gemini) with the fallbacks declared there.

**No LLM SDK calls inside this skill's Python.** The scripts stay deterministic (readiness check, schema/DAG validation, file I/O). This mirrors the host-assisted invariant enforced for `autopilot-roadmap`: semantic reasoning is delegated to the orchestrator or a dispatched agent, not embedded in `scripts/`.

The generator's instructions and the exact output contract live in `templates/generation-prompt.md`. The orchestrator fills its `{{PROPOSAL_TEXT}}`, `{{SOURCE_PROPOSAL_PATH}}`, and `{{ROADMAP_ID}}` placeholders before dispatch.

## Local CLI Mutation Boundary

`plan-roadmap` writes roadmap workspaces and may scaffold OpenSpec change
directories. In local CLI execution, those writes MUST happen inside a managed
worktree. For `--new <slug>` and decomposition modes, set up the roadmap
worktree before writing:

```bash
CHANGE_ID="roadmap-<slug>"
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID")"
cd "$WORKTREE_PATH"
skills/.venv/bin/python skills/shared/checkout_policy.py require-mutation
```

If the invocation only reads a proposal and returns advice in chat, no worktree
is required.

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

The generator reads the full proposal as prose, so there is **no required vocabulary and no mandatory section layout** — a clearly written proposal is enough. The template at `openspec/schemas/roadmap/templates/proposal.md` is the *recommended* shape because it makes a proposal easier for both humans and the model to follow:

| Section | Recommended | Purpose |
|---|---|---|
| `## Motivation` | Yes | Why this epic exists. Frames the generator's rationale fields. |
| `## Capabilities` | Yes | The substance of the work — the raw material for roadmap items. |
| `## Constraints` | Yes | Non-functional requirements; shape acceptance outcomes and ordering. |
| `## Phases` | Optional | Temporal grouping the generator uses to infer dependencies. |
| `## Out of Scope` | Yes | Explicit exclusions so the generator does not invent items. |

The only hard requirement (checked by `validate_proposal()`) is that the proposal is non-empty and has at least one markdown heading. Everything else is a quality signal, not a gate.

## Steps

### 0. Resolve Invocation Mode

Parse `$ARGUMENTS` to determine which form was used:

- **`--new <slug> "<pitch>"`** without `--draft`: copy the template file to `openspec/roadmaps/<slug>/proposal.md`, replace the `<Epic Title>` placeholder with a slug-derived title, replace the `<motivation prose>` placeholder with the pitch. Print the path and exit with "edit the proposal and re-run `/plan-roadmap openspec/roadmaps/<slug>/proposal.md`."
- **`--new <slug> "<pitch>" --draft`**: same scaffold, but the agent expands the pitch into full Capabilities, Constraints, and Phases sections using its own reasoning, then writes the result. Print the path and exit with "review the draft and re-run for decomposition."
- **`<path>`** (existing proposal): proceed to Step 1.

For `--new` modes: if `openspec/roadmaps/<slug>/` already exists, abort unless `--force` is set.

### 1. Read Proposal and Check Readiness

Load the markdown proposal from the provided path. Run `validate_proposal()` from `decomposer.py` — a lightweight readiness gate that the proposal is non-empty and has at least one heading. If it returns errors, abort with the list and a pointer to the template. This gate intentionally does **not** inspect vocabulary; a well-written proposal in any style passes.

Derive `roadmap_id` (`roadmap-<slug>` from the proposal stem) and the repo-relative `source_proposal` path (use `make_repo_relative()`).

### 2. Build the Generation Request

Load `templates/generation-prompt.md` and fill its placeholders:
- `{{PROPOSAL_TEXT}}` ← the full proposal markdown.
- `{{SOURCE_PROPOSAL_PATH}}` ← the repo-relative proposal path.
- `{{ROADMAP_ID}}` ← the derived roadmap id.

Strip the header section above `--- PROMPT BEGINS ---`; only the prompt body is sent to the generator.

### 3. Dispatch Generation

Dispatch the filled prompt to the chosen generator (see **Generation and dispatch** above):
- `--vendor claude` (default): spawn a Claude subagent via the Agent tool.
- `--vendor codex|gemini`: dispatch through `ReviewOrchestrator` (`alternative` mode) to the external vendor CLI.

The generator returns the `roadmap.yaml` body as raw YAML. Write it to the resolved workspace path (Step 6 decides the final location; you may write to a temp path first for validation).

### 4. Validate the Generated Roadmap (Deterministic)

Run `decomposer.py validate <roadmap.yaml>` (or call `validate_roadmap(data, repo_root)` directly). This checks, in order:
1. JSON-schema conformance (`openspec/schemas/roadmap.schema.json`).
2. `item_id` uniqueness.
3. `depends_on` referential integrity (every referenced id exists; no self-dependency).
4. DAG acyclicity.

**Repair loop.** If validation returns errors, re-dispatch to the generator with the original prompt plus the validator's error list (the "Repair pass" section of the generation prompt). Allow up to **2** repair attempts. If the roadmap still fails after that, stop and surface the remaining errors to the operator — do **not** hand-edit `roadmap.yaml` to force it past validation; a persistent failure signals the proposal or the generator output needs human attention.

### 5. Archive Cross-Check

Run `scan_archive_state(repo_root)` to map existing OpenSpec change-ids to `completed` / `in_progress`. Flag any generated item whose derived change-id matches — these likely duplicate work already done or in flight. Surface matches to the operator in Step 6 rather than silently dropping items.

### 6. Present Candidates for User Approval

Display the candidate roadmap items with their dependencies, effort estimates, acceptance outcomes, and any archive-cross-check flags. Allow the operator to approve, modify, or reject individual items before persistence. Re-validate (Step 4) if the operator edits items.

### 7. Resolve Workspace Path and Write `roadmap.yaml`

Determine the output location:
- If `--workspace <path>` was supplied, use it (directory → `<path>/roadmap.yaml`, or explicit `.yaml` file path).
- Otherwise, default to `openspec/roadmaps/<roadmap_id>/roadmap.yaml`.

Print the resolved path, then call `save_roadmap(roadmap, path, overwrite=<force_flag>)` from `skills/roadmap-runtime/scripts/models.py`. The helper creates parent directories and raises `FileExistsError` on collision unless `overwrite=True`. On collision, surface the error verbatim and instruct the operator to re-invoke with `--force` or `--workspace`.

If `--new` was used in Step 0, the proposal.md already lives at `openspec/roadmaps/<roadmap_id>/proposal.md` — leave it in place. If decomposing an existing proposal from elsewhere, the `source_proposal` field in `roadmap.yaml` records the original path.

### 8. Scaffold Approved Changes as OpenSpec Change Directories

For each approved item, create an OpenSpec change directory under `openspec/changes/` via `scaffold_changes()` from `scaffolder.py`, containing:
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

Shared models and utilities are in `skills/roadmap-runtime/scripts/`. `decomposer.py` imports `Roadmap`, `validate_against_schema`, and `ROADMAP_SCHEMA` from the runtime's `models` module; `scaffolder.py` imports `Roadmap`, `RoadmapItem`, `ItemStatus`. Roadmap persistence (`save_roadmap` / `load_roadmap`) lives in `models`.

## Scripts

| Script | Role |
|---|---|
| `scripts/decomposer.py` | Deterministic validation only: `validate_proposal()` (readiness), `validate_roadmap()` (schema + ids + DAG), `scan_archive_state()`, `make_repo_relative()`, and a `validate` CLI. Contains no keyword extraction and no LLM calls. |
| `scripts/scaffolder.py` | Scaffolds OpenSpec change directories from approved items. |
| `scripts/renderer.py` | Renders `roadmap.yaml` → human-readable `roadmap.md` (maintenance direction). |
| `templates/generation-prompt.md` | The model-facing generation contract dispatched in Step 3. |
