---
name: prototype-feature
description: Dispatch N parallel variant agents to produce competing working skeletons from an approved proposal, score them via cheap validation phases, and capture human pick-and-choose feedback for convergence-aware refinement
category: Git Workflow
tags: [openspec, prototyping, divergence, parallel, planning]
triggers:
  - "prototype feature"
  - "prototype this"
  - "dispatch variants"
  - "prototype-feature"
---

# Prototype Feature

Dispatch N parallel variant agents (default 3) that each produce a working skeleton from an already-approved OpenSpec proposal, score the skeletons via cheap `/validate-feature` phases, and capture per-aspect human pick-and-choose feedback so `/iterate-on-plan --prototype-context` can synthesize the best combination back into `design.md` and `tasks.md`.

This skill is the **divergence stage on the generation side of the approval gate** — the same way `/parallel-review-plan` and `/parallel-review-implementation` apply divergence to review.

## Arguments

`$ARGUMENTS` — `<change-id>` (required) plus optional flags:

- `--variants N` — number of competing skeletons to dispatch. Default `3`. Bounded `2 ≤ N ≤ 6`. Out-of-range values fail fast.
- `--angles "a,b,c"` — comma-separated angle prompts (default `simplest,extensible,pragmatic` per D5). The count of angles MUST equal `--variants` exactly. When `--variants ≠ 3` and `--angles` is omitted, the skill fails fast (silent guessing of fewer-than-3 angles is ambiguous).

## Prerequisites

- Approved OpenSpec proposal at `openspec/changes/<change-id>/` (proposal.md + design.md + specs/ + tasks.md). The skill never auto-triggers — it's only invoked explicitly by the operator or via `/iterate-on-plan`'s advisory `workflow.prototype-recommended` finding.
- Worktree infrastructure (`skills/worktree/scripts/worktree.py`) supports `--branch-prefix prototype` (added by wp-worktree).
- VariantDescriptor schema and `synthesize_variants()` available in `skills/parallel-infrastructure/scripts/variant_descriptor.py`.

## Coordinator Integration (Optional)

Use `docs/coordination-detection-template.md` as the shared detection preamble. When `CAN_QUEUE_WORK=true`, the skill emits per-variant work items so other operators can observe progress. Without coordinator the dispatch is direct via Task() agents.

## Steps

### 1. Validate inputs and resolve plan

Call `dispatch_variants.plan_variants(change_id, variants, angles)`. The function enforces D2 (count bounds) and D5 (angle-count matching). On `VariantPlanError`, abort before any worktree creation — no partial state should leak.

```python
from dispatch_variants import plan_variants
plan = plan_variants(
    change_id=CHANGE_ID,
    variants=int(args.variants or 3),
    angles=args.angles.split(",") if args.angles else None,
)
```

The returned `VariantPlan` carries a `VariantSpec(variant_id, angle, branch, worktree_relpath)` per variant — every downstream step consumes this structure.

**Spec scenarios covered**: `PrototypeFeatureSkill.default-variant-dispatch`, `custom-variant-count-and-angles`, `variant-count-out-of-bounds`.

### 2. Resolve vendor diversity policy (best-effort, never hard-block)

Query `vendor_health.check_all_vendors()`. Sort the healthy vendors by their order in the report (which the report itself sorts by health). Pass them to `dispatch_variants.resolve_vendor_assignment(plan, available_vendors)`.

```python
from vendor_health import check_all_vendors
from dispatch_variants import resolve_vendor_assignment

report = check_all_vendors()
healthy = [v.agent_id for v in report.vendors if v.healthy]
assignment = resolve_vendor_assignment(plan, healthy)
```

Per D3:
- ≥ N distinct healthy vendors → one variant per vendor; `assignment.fallback == False`.
- 1 ≤ distinct < N → all variants share the most-available vendor; `assignment.fallback == True`. Inject temperature + seed variation in the per-variant prompts so style still diverges.
- 0 vendors → `VariantPlanError`. Operator must wait for at least one vendor to recover.

`assignment.per_variant` (variant_id → vendor) and `assignment.fallback` are persisted onto each VariantDescriptor in step 5.

**Spec scenarios covered**: `VendorDiversityPolicy.sufficient`, `insufficient`, `recorded`.

### 3. Set up isolated worktrees (one per variant)

For each `VariantSpec`, call `worktree.py setup` with the new prototype prefix:

```bash
python3 skills/worktree/scripts/worktree.py setup "${CHANGE_ID}" \
  --agent-id "${VARIANT_ID}" \
  --branch-prefix prototype \
  --no-bootstrap
```

This produces (per wp-worktree):
- Branch: `prototype/<change-id>/v<n>` (note `/` separator, not `--`)
- Worktree: `.git-worktrees/<change-id>/v<n>/`
- Auto-pinned in the registry so the 24h GC timer can't reclaim it before `/cleanup-feature` runs

Variant agents NEVER write to the feature branch or to each other's branches — the worktree boundary enforces isolation.

**Spec scenarios covered**: `PrototypeFeatureSkill.isolated-worktree-per-variant`.

### 4. Dispatch variant agents in parallel

For each variant, dispatch a Task() agent rooted in its worktree:

```
Task(
  subagent_type="general-purpose",
  description=f"Variant {variant_id}: {angle} angle",
  prompt=f"""You are variant {variant_id} for OpenSpec change {change_id}.

## Angle (your design value)
{angle_prompt_from_angles_yaml}

## Context
- proposal.md, design.md, specs/, tasks.md from the approved proposal
- worktree: {worktree_relpath}
- branch: {branch}  (you commit here; never touch other branches)

## Goal
Produce a *working skeleton* that demonstrates how your angle would
shape the implementation. Skeletons need not be feature-complete — they
must compile/run cheaply enough that ``/validate-feature --phase smoke,spec``
can score them.

## Constraints
- Do not modify openspec/changes/{change_id}/ — the proposal is fixed.
- Commit incrementally with conventional messages.
- Stop after producing the skeleton; do NOT iterate based on test failures
  unless the failure is a syntactic mistake in your own code.
""",
  run_in_background=True,
)
```

Wait for all N agents to complete (or report failure). Failures are recorded, not raised — D7 says even a partially-failed dispatch should still feed pick-and-choose with the surviving variants.

### 5. Score each variant via /validate-feature smoke + spec

Per D6, scoring uses existing validation phases. For each variant:

```bash
cd .git-worktrees/${CHANGE_ID}/${VARIANT_ID}
/validate-feature ${CHANGE_ID} --phase smoke,spec
```

Capture the per-phase `pass`/`fail` and the `covered`/`total`/`missing` numbers. A failed smoke phase IS a valid scoring outcome — record it and continue.

**Spec scenarios covered**: `VariantScoring.smoke-and-spec`, `skeleton-fails-to-deploy`.

### 6. Gather human pick-and-choose feedback

Per D7, present the four-aspect choice via `AskUserQuestion` with `multiSelect=true`:

```
AskUserQuestion(
  questions=[
    {
      "question": "Which variants' data model should carry forward?",
      "options": [{"label": v.variant_id, ...} for v in plan.variants]
                + [{"label": "rewrite", ...}],
      "multiSelect": True,
      "header": "data_model",
    },
    # ... same shape for api / tests / layout ...
  ]
)
```

Convert the operator's selections into a `human_picks` dict per variant:

```python
human_picks = {
  "data_model": variant_id in selected_for_data_model,
  "api":        variant_id in selected_for_api,
  "tests":      variant_id in selected_for_tests,
  "layout":     variant_id in selected_for_layout,
}
```

Optionally collect a free-form `synthesis_hint` per variant (e.g. "prefer v1 data model but steal v3 test naming") — this carries forward into `synthesis_notes` in the synthesis plan.

**Spec scenarios covered**: `PrototypeFindingsArtifact.human-pick-and-choose`.

### 7. Build descriptors and write prototype-findings.md

For each variant, assemble the descriptor and persist:

```python
from collect_outcomes import build_descriptor, write_findings_file

descriptors = [
    build_descriptor(
        variant_id=spec.variant_id,
        angle=spec.angle,
        vendor=assignment.per_variant[spec.variant_id],
        change_id=CHANGE_ID,
        scoring=scoring_results[spec.variant_id],
        human_picks=human_picks_by_variant[spec.variant_id],
        vendor_fallback=assignment.fallback,
        synthesis_hint=hints_by_variant.get(spec.variant_id),
    )
    for spec in plan.variants
]
write_findings_file(
    change_dir=Path("openspec/changes") / CHANGE_ID,
    descriptors=descriptors,
)
```

The output file `openspec/changes/<change-id>/prototype-findings.md` carries:
- A human-readable section per variant (angle, vendor, branch, scores, picks)
- A fenced JSON block per variant conforming to `contracts/schemas/variant-descriptor.schema.json` for machine consumption by `/iterate-on-plan --prototype-context`

**Spec scenarios covered**: `PrototypeFindingsArtifact.findings-artifact-produced`.

### 8. Hand off to convergence

Print the next-step pointer:

```
Next: /iterate-on-plan <change-id> --prototype-context <change-id>
```

`/iterate-on-plan --prototype-context` reads `prototype-findings.md`, loads each variant's branch diff against `main`, and emits `convergence.*` findings to refine `design.md` and `tasks.md` before `/implement-feature` runs.

The `prototype/<change-id>/v*` branches and worktrees are kept (auto-pinned) until `/cleanup-feature` deletes them as part of feature cleanup (per D4).

## Outputs

- `openspec/changes/<change-id>/prototype-findings.md` — single source of truth for variant outcomes + human picks
- `prototype/<change-id>/v<n>` branches (one per variant)
- `.git-worktrees/<change-id>/v<n>/` worktrees (auto-pinned, kept for `/cleanup-feature`)

## Failure Modes

- **Bad inputs (count out of bounds, angle-count mismatch)** → `VariantPlanError` before any worktree creation.
- **Zero vendors available** → fail fast; never silently dispatch to nothing.
- **One variant fails to commit a skeleton** → recorded with `automated_scores.smoke.pass=False` and excluded from `assignment.per_variant` rendering, but the surviving variants still proceed to scoring + human pick-and-choose. Synthesis runs on whoever made it.
- **Operator declines pick-and-choose** → no findings file is written; existing prototype branches remain (cleanup will remove them at feature close).
