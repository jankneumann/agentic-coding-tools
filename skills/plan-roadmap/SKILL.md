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

`$ARGUMENTS` accepts four invocation forms:

1. **Decompose existing proposal** — `<path-to-proposal.md>`
   Decompose the proposal at the given path. The path may be inside or outside `openspec/roadmaps/`.

2. **Scaffold a blank proposal** — `--new <slug> "<short pitch>"`
   Copy the proposal template to `openspec/roadmaps/<slug>/proposal.md`, pre-filling the title and Motivation section from the pitch. Exit with a "now edit and re-run" message. The slug becomes the `roadmap_id`.

3. **Scaffold an LLM-drafted proposal** — `--new <slug> "<short pitch>" --draft`
   Same as form 2, but the agent expands the pitch into a full draft (Capabilities, Constraints, Phases) using its own reasoning rather than leaving placeholders. The operator still reviews before re-running for decomposition.

4. **Re-decompose after a failure** — `--replan <roadmap-id>`
   Re-plan only the subgraph an `/autopilot-roadmap` failure invalidated. Driven by
   `<workspace>/replan-request.json`, which that skill writes when its `replan_required`
   gate proceeds; without the request file this form is refused. See **Replan Mode**.

Optional flags:
- `--vendor <claude|codex|gemini>` — Choose the generator. Default `claude` dispatches a Claude subagent via the Agent tool. `codex` / `gemini` route through the shared CLI dispatcher to the external vendor (`gpt-5.5` / `gemini-3.1-pro`).
- `--workspace <path>` — Override the default output workspace (default: `openspec/roadmaps/<roadmap_id>/`).
- `--force` — Overwrite an existing `roadmap.yaml` at the target. Without this, `/plan-roadmap` aborts on collision to protect operator edits to `status` / `priority`.

## Generation and dispatch

The semantic work — reading the proposal and deciding what the items, dependencies, efforts, and acceptance outcomes are — is done by a premium model, never by keyword parsing. The orchestrator (the agent running this skill) **dispatches** that work rather than importing an LLM SDK:

- **Default (`--vendor claude`):** spawn a Claude subagent with the Agent tool, handing it the filled generation prompt. The subagent reads the proposal and returns the `roadmap.yaml` body.
- **External (`--vendor codex|gemini`):** route through `<skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py` (`ReviewOrchestrator`) using the `alternative` dispatch mode. Vendor configuration comes from `AGENTS_YAML` when provided, with public/provider-local fallbacks documented by that sibling skill.

**No LLM SDK calls inside this skill's Python.** The scripts stay deterministic (readiness check, schema/DAG validation, file I/O). This mirrors the host-assisted invariant enforced for `autopilot-roadmap`: semantic reasoning is delegated to the orchestrator or a dispatched agent, not embedded in `<skill-base-dir>/scripts/`.

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
python3 "<skill-base-dir>/../shared/checkout_policy.py" require-mutation
```

If the invocation only reads a proposal and returns advice in chat, no worktree
is required. `--replan` rewrites `roadmap.yaml`, so it is a mutation mode: set up the
worktree the same way before R2.

## Output

- `openspec/roadmaps/<roadmap_id>/roadmap.yaml` conforming to the roadmap schema
- `openspec/roadmaps/<roadmap_id>/proposal.md` co-located with the roadmap (when scaffolded via `--new`)
- Each item in the roadmap has: `item_id`, `title`, `description`, `effort`, `priority`, `depends_on`, `acceptance_outcomes`, and a derived `change_id`
- Dependency DAG is acyclic (validated before output)
- One `openspec/changes/<change-id>/` per approved item, each a preliminary sketch that passes `openspec validate --strict` (see Step 8)

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
- **`--replan <roadmap-id>`**: skip Steps 1–8 entirely and follow **Replan Mode** below. A replan re-decomposes part of an existing roadmap; it never regenerates the whole file.
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

**Populate `change_id` before saving.** The generation contract does not ask the model for `change_id` and the schema leaves it optional, so a generated roadmap carries none. Call `populate_change_ids(roadmap)` from `<skill-base-dir>/scripts/scaffolder.py` first — it derives each id deterministically using the same function `scaffold_change()` uses, so the id recorded in `roadmap.yaml` is always the id of the directory later created for that item. It is idempotent and preserves any id an operator set by hand.

Print the resolved path, then call `save_roadmap(roadmap, path, overwrite=<force_flag>)` from `<skill-base-dir>/../roadmap-runtime/scripts/models.py`. The helper creates parent directories and raises `FileExistsError` on collision unless `overwrite=True`. On collision, surface the error verbatim and instruct the operator to re-invoke with `--force` or `--workspace`.

If `--new` was used in Step 0, the proposal.md already lives at `openspec/roadmaps/<roadmap_id>/proposal.md` — leave it in place. If decomposing an existing proposal from elsewhere, the `source_proposal` field in `roadmap.yaml` records the original path.

### 8. Scaffold Approved Changes as OpenSpec Change Directories

For each approved item, create an OpenSpec change directory under `openspec/changes/` via `scaffold_changes(roadmap, repo_root)` from `<skill-base-dir>/scripts/scaffolder.py`. Each contains:

- `proposal.md` with a `parent_roadmap` field linking back to the roadmap
- `tasks.md` skeleton
- `specs/<change-id>/spec.md` — a spec delta sketched from the item's `acceptance_outcomes`, one `### Requirement:` per item and one `#### Scenario:` per outcome

**The scaffold must validate.** `openspec validate --strict` rejects a change with no delta carrying a `#### Scenario:` block, and Git does not track empty directories — so a `specs/` directory with nothing written into it arrives at CI as a change with no specs at all. CI runs `openspec validate --strict --all` on every push, so an N-item roadmap that scaffolds without deltas lands N failures. Verify with `openspec validate --strict --all` before committing a freshly scaffolded roadmap.

What the scaffold produces is a **preliminary sketch, not a finished plan**. The `WHEN` clauses are generic because the roadmap does not yet know each item's trigger. That is the intended shape: the OpenSpec setup exists and validates from day one, and each item's plan is refined by `/plan-feature` and `/iterate-on-plan` when it is picked up — using what the item's completed dependencies taught.

Change directories always live at `openspec/changes/<change-id>/`, never nested under the roadmap workspace, because `/implement-feature` expects that canonical path. `scaffold_change(roadmap, repo_root, item_id)` scaffolds a single item for re-scaffolding or repair.

## Replan Mode

`--replan <roadmap-id>` is the consumer of the handoff `/autopilot-roadmap` writes
when its `replan_required` gate proceeds. The two deterministic ends are scripts; the
re-decomposition in the middle is the model's work, exactly as in Step 3.

### R1. Emit the scope (deterministic)

```bash
python3 "<skill-base-dir>/scripts/decomposer.py" replan-scope <roadmap-id> [--repo-root <path>]
```

Accepts either a workspace directory or a bare `<roadmap-id>` (resolved under
`openspec/roadmaps/`). It reads `<workspace>/replan-request.json` and prints JSON:

- `seed_items` — the items the request parked in `replan_required`
- `scope_items` — the seeds plus their transitive non-preserved dependents: **the only
  items you may rewrite**
- `preserved_items` — everything the replan must copy through untouched
- `items[]` — title, status, effort, `depends_on`, and `change_id` per scoped item
- `failed_item_id`, `failure_reason`, `learning_entry`, `source_proposal`

`completed`, `superseded`, and `in_progress` are *preserved statuses* (as is any item
carrying a `superseded_by` edge, whatever its status): they are excluded
from the scope **and act as traversal barriers**, so the walk stops at them rather than
sweeping their dependents in. Work already done, already migrated, or in flight under
another agent is never re-planned out from under it.

Exit 2 with a message naming the file when `replan-request.json` is absent — a replan
with no request has no trigger and nothing to bound it.

### R2. Re-decompose the subgraph (host-executed)

Dispatch the re-decomposition the same way Step 3 does (`--vendor` applies), with a
prompt bounded to the emitted scope:

- **Read** the `source_proposal` and the failed item's `learning_entry` — the learning
  entry is *why* this replan exists; a re-decomposition that ignores it will reproduce
  the same failure.
- **Rewrite only `scope_items`.** Items may be split, merged, re-scoped, re-ordered, or
  dropped within that set.
- **Leave `preserved_items` byte-identical**, and never touch `learnings/` or
  `learning-log.md` — the failure record is the input to this replan and the audit
  trail for the next one.
- Edit `roadmap.yaml` in place. Do not regenerate the file: `status`, `priority`, and
  operator edits outside the scope must survive.

### R3. Close it out (deterministic)

```bash
python3 "<skill-base-dir>/scripts/decomposer.py" replan-finish <roadmap-id> [--repo-root <path>]
```

Flips every remaining `status: replan_required` to `approved`, validates the roadmap
(schema, ids, DAG — Step 4's checks), and deletes `replan-request.json`. On validation
failure it **restores the original `roadmap.yaml` and keeps the request file**, so a
broken replan stays retryable rather than consuming its own trigger; fix the
re-decomposition and re-run R2–R3.

Re-scaffold any newly created item's change directory with `scaffold_change(roadmap,
repo_root, item_id)` (Step 8) once `replan-finish` reports OK.

## Lifecycle

```
Ingestion:     pitch / proposal.md  →  roadmap.yaml      (this skill)
Replan:        replan-request.json  →  re-scoped items   (this skill, --replan)
Refinement:    active roadmap       →  safe item edits   (/refine-roadmap)
Execution:     roadmap.yaml         →  item completion   (/autopilot-roadmap)
Maintenance:   roadmap.yaml         →  roadmap.md        (renderer; check_roadmap_sync)
Archival:      workspace/           →  archive/<date>-<id>/  (/archive-roadmap)
```

Generated sections of any rendered markdown view are wrapped in `<!-- GENERATED: begin/end -->` markers. Human-authored prose outside markers is preserved across re-renders.

## Runtime Reference

Shared models and utilities are in `<skill-base-dir>/../roadmap-runtime/scripts/`. `decomposer.py` imports `Roadmap`, `validate_against_schema`, and `ROADMAP_SCHEMA` from the runtime's `models` module; `scaffolder.py` imports `Roadmap`, `RoadmapItem`, `ItemStatus`. Roadmap persistence (`save_roadmap` / `load_roadmap`) lives in `models`.

## Scripts

| Script | Role |
|---|---|
| `<skill-base-dir>/scripts/decomposer.py` | Deterministic validation only: `validate_proposal()` (readiness), `validate_roadmap()` (schema + ids + DAG), `scan_archive_state()`, `make_repo_relative()`, and the `validate` / `validate-repo` / `replan-scope` / `replan-finish` CLIs. Contains no keyword extraction and no LLM calls. |
| `<skill-base-dir>/scripts/scaffolder.py` | `populate_change_ids(roadmap)` — derives and persists each item's `change_id`; called in Step 7 before `save_roadmap`. `scaffold_changes(roadmap, repo_root)` — scaffolds every approved item into a change directory that validates (Step 8). `scaffold_change(..., item_id)` — the single-item form, for re-scaffolding or repair. |
| `<skill-base-dir>/scripts/renderer.py` | Renders `roadmap.yaml` → human-readable `roadmap.md` (maintenance direction). |
| `templates/generation-prompt.md` | The model-facing generation contract dispatched in Step 3. |
