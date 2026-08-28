---
name: refine-roadmap
description: "Safely preview and evolve an existing active roadmap item-by-item without overwriting execution state. Use for adding, editing, splitting, reordering, or superseding roadmap items; use plan-roadmap to create a roadmap."
category: Planning
tags: [roadmap, refinement, planning, dag, openspec]
triggers:
  - "refine-roadmap"
  - "refine roadmap"
  - "edit active roadmap"
  - "split roadmap item"
related:
  - plan-roadmap
  - autopilot-roadmap
  - roadmap-runtime
  - archive-roadmap
---

# Refine Roadmap

Safely evolve an existing active `roadmap.yaml` through a previewed transaction. This skill edits individual items and their scheduling relationships while preserving runtime history. It is the maintenance counterpart to `plan-roadmap`:

- `plan-roadmap` creates a roadmap from a proposal and refuses to overwrite it unless forced.
- `refine-roadmap` applies explicit operations to an existing active roadmap and never regenerates the document wholesale.

Do not use this skill to create a roadmap or to modify a workspace under `openspec/roadmaps/archive/`. Use `plan-roadmap` or restore an archived workspace through an explicitly approved recovery workflow instead.

## Arguments

`$ARGUMENTS` identifies an active workspace or its `roadmap.yaml`, followed by the requested refinement. Optional controls:

- `--request <path>` — use a prepared refinement request YAML.
- `--preview-only` — report effects and stop without mutation.

When no request file is supplied, translate the operator's intent into a temporary YAML request using `templates/refinement-request.yaml`. Do not place an ephemeral request inside the repository unless the operator wants it retained as a separate artifact; the applied roadmap records the durable provenance.

## Supported Operations

Each request has non-empty `rationale`, `actor`, `source`, and `operations` fields. Operations execute in listed order.

### Add

```yaml
- op: add
  after: ri-04               # optional; use before OR after
  item:
    item_id: ri-09
    title: Add recovery gate
    description: Reject unsafe resume state.
    rationale: A completed dependency exposed the missing guard.
    effort: S
    depends_on: [ri-04]
    acceptance_outcomes:
      - Invalid resume state fails closed with an actionable error.
```

New items default to `approved` on an approved, in-progress, or blocked roadmap and `candidate` while the roadmap is still planning. `change_id` is optional; when absent it is derived deterministically and collision-safe.

### Edit

```yaml
- op: edit
  item_id: ri-05
  set:
    description: Clarified scope after ri-04 landed.
    effort: M
    depends_on: [ri-04]
```

Edits may change planning fields such as title, description, rationale, effort, priority, dependencies, scope, and acceptance outcomes. They may not change protected identity or lifecycle fields: `item_id`, `change_id`, `status`, `learning_refs`, `failure_reason`, `blocked_by`, or `superseded_by`. Use the dedicated supersede operation for ownership transfer.

### Split

```yaml
- op: split
  item_id: ri-05
  strategy: chain            # chain or parallel
  items:
    - item_id: ri-09
      title: Add detection
      effort: S
      acceptance_outcomes: [Unsafe state is detected.]
    - item_id: ri-10
      title: Add enforcement
      effort: S
      acceptance_outcomes: [Unsafe state is blocked.]
```

The original item remains as `superseded` provenance. Replacement items inherit its upstream dependencies and learning references; downstream dependencies are rewired to the final chain item or every parallel item. Completed, in-progress, failed, skipped, or already superseded items cannot be split. An item named by `checkpoint.json` also cannot be split.

### Reorder

```yaml
- op: reorder
  item_id: ri-08
  before: ri-06              # use before OR after
```

Reordering moves one item, then renumbers item priorities to match the resulting order. The preview shows the resulting execution waves before any write.

### Supersede

```yaml
- op: supersede
  item_id: ri-06
  by:
    - other-roadmap:ri-03
```

Supersession records typed successor refs, marks the original item `superseded`, and rewires local dependents to local or cross-roadmap successors. The successor must resolve during cross-roadmap validation. The same lifecycle and checkpoint protections as split apply.

## Mutation Boundary

All writes and git mutations happen in a managed worktree. If the current checkout is already managed, stay there. Otherwise create a single-agent worktree before authoring a retained request or applying:

```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" detect
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "refine-<roadmap-id>")"
cd "$WORKTREE_PATH"
python3 "<skill-base-dir>/../shared/checkout_policy.py" require-mutation
```

Never use `--force` from `plan-roadmap` to approximate refinement. It replaces the active artifact and can erase statuses, checkpoint alignment, and accumulated provenance.

## Workflow

### 1. Resolve and Inspect

Resolve a workspace argument to `<workspace>/roadmap.yaml`. Read the entire roadmap plus any `checkpoint.json`, `learning-log.md`, `learnings/`, existing `roadmap.md`, active OpenSpec changes, archived OpenSpec changes, and sibling active roadmaps. Confirm the workspace is active and the requested operations do not target protected execution state.

### 2. Author the Transaction Request

Create the smallest explicit operation list that expresses the operator's request. Record why the refinement is needed, who requested or authored it, and where the evidence came from. Prefer a concrete source such as an issue, review, learning entry, or operator request; never store raw prompts, credentials, tokens, or connection strings.

### 3. Preview Without Mutation

Run:

```bash
python3 "<skill-base-dir>/scripts/refiner.py" preview \
  "<workspace>/roadmap.yaml" "<request.yaml>" --repo-root .
```

The preview is read-only. It reports:

- the SHA-256 of the exact roadmap bytes previewed;
- candidate item data and operation summaries;
- newly introduced item and change IDs;
- before/after execution waves;
- dependency edges added and removed;
- schema, item-id, change-id, dependency, DAG, and cross-roadmap errors;
- collisions with active or archived OpenSpec change IDs.

Stop on any error. Show the scheduling, DAG, ownership, and scaffold effects to the operator before apply. A request that already specifies the exact operations counts as approval when the preview introduces no additional effects or warnings; otherwise obtain explicit approval for the revised effects. Honor `--preview-only` by stopping here.

### 4. Apply the Previewed Bytes

Pass the preview's `base_sha256` back as the concurrency guard:

```bash
python3 "<skill-base-dir>/scripts/refiner.py" apply \
  "<workspace>/roadmap.yaml" "<request.yaml>" --repo-root . \
  --expect-base-sha256 "<base-sha256>"
```

Apply recomputes the preview and aborts if `roadmap.yaml` changed in the meantime. It then:

1. Appends a structured refinement record with timestamp, actor, source, rationale, base digest, and operation summaries.
2. Scaffolds OpenSpec directories only for newly added or split items; existing change directories are never rewritten.
3. Updates an existing rendered `roadmap.md` through generated markers while preserving human-authored sections.
4. Runs schema, dependency, DAG, and cross-roadmap validation.
5. Runs `openspec validate --strict --all`.
6. Verifies checkpoints and learning files remain byte-identical.

If any step fails, apply restores the original roadmap and rendered markdown and removes only change directories created by that transaction. Re-preview after resolving the cause.

### 5. Review and Commit Atomically

Inspect `git diff` and `git status`. The expected mutation set is the roadmap, an existing rendered roadmap view if present, and change directories for new items only. Check that checkpoint and learning files are absent from the diff.

Stage only that exact set and create a single atomic commit:

```bash
git add -- "<workspace>/roadmap.yaml" "<workspace>/roadmap.md" <new-change-directories>
git commit -m "feat(roadmap): refine <roadmap-id>"
```

Omit `roadmap.md` or new change paths that do not exist. Do not split the roadmap write and new scaffolds across commits: the repository must never expose a roadmap that references missing changes or changes with no owning item.

### 6. Land the Update

Follow the repository's completion contract: run relevant tests, pull with rebase, push the feature branch, and verify `git status` reports it up to date with its upstream. Work is not complete until push succeeds.

## Deterministic Script Contract

`<skill-base-dir>/scripts/refiner.py` has two subcommands:

- `preview <roadmap> <request> --repo-root <root>` — no repository writes; exit `0` when valid and `1` for candidate validation errors.
- `apply <roadmap> <request> --repo-root <root> --expect-base-sha256 <digest>` — transactional mutation; exit `0` on success and `2` for stale-base, filesystem, or validation failure.

The script contains no LLM calls. Semantic item design stays in the reviewed request; deterministic mechanics and validation stay in Python.

## Common Rationalizations

| Rationalization | Why it is unsafe |
|---|---|
| "It is faster to rerun plan-roadmap with force." | Whole-file generation can erase live statuses, checkpoint alignment, learning refs, and operator edits. |
| "The DAG change is obvious, so preview adds no value." | A local edge edit can change execution waves, create a cross-roadmap cycle, or strand a dependent behind a superseded item. |
| "Existing change scaffolds can be regenerated for consistency." | Active change directories may contain refined specs and implementation plans; rewriting them destroys work outside the roadmap transaction. |
| "A second commit for scaffolds is harmless." | Between commits, the roadmap points at missing changes or the changes have no atomic owner. |

## Red Flags

- The target lives below `openspec/roadmaps/archive/`.
- The apply digest differs from the preview digest.
- A completed or checkpoint-referenced item is being split or superseded.
- The preview reports an active or archived `change_id` collision.
- Checkpoint, learning-log, or pre-existing change files appear in the diff.
- Schema, DAG, cross-roadmap, or strict OpenSpec validation did not run cleanly.
- More than one commit is needed to make the roadmap and new scaffolds mutually valid.

## Verification

1. Confirm preview was read-only and its base digest is the digest used by apply.
2. Confirm before/after execution waves and dependency-edge changes match the approved intent.
3. Confirm existing item statuses, change IDs, learning refs, checkpoint bytes, and learning files are preserved.
4. Confirm every new item has exactly one new OpenSpec change directory and no existing change directory was rewritten.
5. Confirm schema, local DAG, cross-roadmap, duplicate/archive, and `openspec validate --strict --all` checks all pass.
6. Confirm the roadmap contains the appended refinement rationale and provenance record.
7. Confirm the complete update is one atomic commit, pushed to its upstream branch, with a clean and up-to-date worktree.
