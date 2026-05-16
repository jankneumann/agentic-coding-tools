# PLAN_ITERATE Handoff — plan-iterate-a3f2c891

**Phase:** PLAN_ITERATE (iteration 0)
**Date:** 2026-05-15
**Author:** architect sub-agent (Opus 4.7)

## Summary

Refined the plan after a deep read against the actual coordinator HTTP API and skill code. Most artifacts had a single load-bearing assumption that did not survive contact with reality: that the seeder could write `metadata.task_key` and `metadata.change_id` through `POST /issues/create`. The current `IssueCreateRequest` (`agent-coordinator/src/coordination_api.py:90`) has no `metadata` field, and `IssueService.create()` only populates `metadata.body` from `description`. Two other API mismatches (`POST /work/submit` is actually `POST /issues/create`; `try_issue_update` has no `depends_on`) had to be reconciled.

The fix is a v1 design that carries task identity in **labels** (`task:<task_key>` alongside `change:<change-id>`) rather than metadata. This keeps the proposal's promise of "no migrations, no new endpoints" and lets the existing GIN index + `try_issue_list(labels=...)` filter handle idempotency lookups.

## What changed

### proposal.md
- Item 2 (seeding): swapped `metadata={task_key, change_id}` for `labels=["change:<id>", "task:<key>"]`. Added rationale referencing D7.
- "What Doesn't Change": clarified that the labels column alone is sufficient and that no `metadata` write path is required for v1.

### design.md
- **D1**: clarified that the renderer SHALL duplicate `_gen_block` / `_extract_generated_blocks` locally rather than reach into private symbols. Explicitly excluded `_extract_human_sections` from plan-roadmap because it's hardcoded to roadmap section names — the renderer needs a simpler "everything outside markers" splitter.
- **D7**: rewrote to make labels (not metadata) the identity carrier, with a long rationale block showing why the current API forces this choice. Listed the reserved label namespaces (`change:`, `task:`, `wp:`).
- **D8** (new): single-pass topological seeding. The two-pass POST-then-PATCH-`depends_on` strategy is infeasible because `IssueUpdateRequest` does not accept `depends_on`.
- **D9** (new): when both markers absent AND coordinator unreachable, a single write appends the markers with the stale-marker inside — guarantees the markers exist for the next successful invocation.
- Open Questions: added Q4 — renderer SHALL NOT touch git index (auto-staging is the hook's job).

### specs/coordinator-task-status-renderer/spec.md
- "Block content reflects current coordinator state": rewrote to extract `task_key` from the `task:<key>` label, dropped `metadata.task_key`, switched from "completed status" to "closed status with close_reason match", switched to natural-numeric sort, added the skip-and-warn behavior for issues lacking a `task:<key>` label.
- "Markers absent AND coordinator unreachable on first invocation" (new scenario): formalizes D9.
- "Seeding at /plan-feature Gate 2" requirement: swapped metadata fields for labels, added the `IssueCreateRequest` note.
- "Re-run after partial seeding": label-based idempotency check.
- "Seeding aborts on dependency cycle" (new scenario): formalizes D8 failure mode.

### contracts/README.md
- Renderer effects step 3 (new): extract task_key from `task:<key>` label.
- Renderer effects step 5: explicit "SHALL NOT touch the git index".
- Rendered-content format: replaced status enumeration with current friendly-status mapping (`pending|in_progress|closed|failed`), deferred evidence URI surfacing to follow-up, switched to natural-numeric sort.
- Seeder section: rewrote effects + payload around `try_issue_create` kwargs and topological seeding. Dropped the two-pass PATCH note (infeasible).
- Related coordinator surface table: replaced incorrect `/work/submit` row with correct `/issues/create`, `/issues/list`, `/issues/update` rows. Added an explicit footnote explaining that `work_queue.metadata` exists but is not writable via the current API.

### tasks.md
- 2.4a (new): test for markers absent + coordinator down single-write.
- 2.6: clarified marker-helper duplication strategy and label-based task_key extraction.
- 2.9: idempotency now keyed on `task:<key>` label.
- 2.9a (new): test for topological seeding + cycle detection.
- 2.12: implementation note pointing at `try_issue_create` kwargs and D7/D8.
- Phase 4 header note: added hermetic hook-test strategy (tmp_path git fixture with renderer stub via env var override).

### work-packages.yaml
- `wp-renderer-skill` description: spelled out the label-based identity, the local marker-helper duplication, and the single-pass topological seeding. Updated spec-scenario list to include the new scenarios.
- `wp-hooks` description: added the `COORDINATOR_TASK_STATUS_RENDERER` env var hook-stub pattern.

## What surprised me

1. **`IssueCreateRequest` has no `metadata` field.** This single fact invalidated the original seeder design. The plan looked plausible from spec/design alone but did not survive a check against the source code.
2. **`plan-roadmap.renderer._extract_human_sections` is roadmap-shaped, not generic.** The design said "import or duplicate (TBD)" — but importing would have actively misled the implementer, because the function would silently drop hand-authored prose in tasks.md that doesn't live under `## Cross-Cutting Themes` / `## Out of Scope`. Caught early.
3. **`try_issue_update` doesn't accept `depends_on`.** This forced the seeder to a single-pass topological design — actually a simpler implementation than the original two-pass plan.
4. **Endpoint name `/work/submit` was carried forward from old beads-era prose.** The actual endpoint for issues has been `/issues/create` for a while. Reviewers reading the design would have been confused.

## What was NOT changed (intentional)

- The bootstrap note in `tasks.md` (this change's own tasks.md can't have a managed block because the renderer doesn't exist yet) — left intact per the phase task instructions.
- D2 (both hooks), D3 (seed at Gate 2), D4 (stale-marker fallback), D5 (label filtering, no `/issues/by-change/<id>` endpoint), D6 (per-change-id invocation) — sound as written; no edits needed.
- The work-package DAG: still `wp-contracts → {wp-renderer-skill, wp-plan-feature-integration, wp-hooks} → wp-integration`. The lock-key map has no collisions across the parallel-after-contracts packages; their `write_allow` scopes are disjoint.
- Outcome of the openspec validate: PASSES `--strict`.

## Concerns / follow-ups

- **`metadata.tasks_md_anchor`** (line-number breadcrumb): mentioned in the original spec; deferred to a follow-up because writing it requires the same API expansion as `metadata.task_key`. If the operator wants this, a separate proposal should add `metadata` to `IssueCreateRequest` + `try_issue_create`.
- **Evidence URI surfacing in the rendered block**: deferred. `IssueService.show()` doesn't expose `result.evidence_uri` cleanly; revisit once that path exists.
- **Natural-numeric vs lexicographic sort**: switched to natural-numeric because lexicographic puts `1.10` before `1.2`. The plan-roadmap renderer uses its own ordering; ours is independent.

## Validation

```
openspec validate add-coordinator-task-status-renderer --strict
# → "Change 'add-coordinator-task-status-renderer' is valid"
```

## Disposition

`complete` — refinements settle. No further changes anticipated on a second pass unless the operator decides to expand API surface (which would be a separate proposal).
