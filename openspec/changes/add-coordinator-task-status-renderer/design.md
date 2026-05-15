# Design — Coordinator Task-Status Renderer

## Goals and non-goals

**Goal.** Make `openspec/changes/<change-id>/tasks.md` reliably reflect coordinator-recorded task state, removing the manual-checkbox-flip failure mode without changing how humans author tasks.md content.

**Non-goal.** Enforcement. The renderer is a *projection*, not a gate. If an agent fabricates a `complete_work` call, the renderer dutifully renders the false state. Hard gating with evidence verification is a separate proposal.

## Architecture at a glance

```
┌──────────────────────────────────────────────────────────────┐
│ git events                                                    │
│   pre-commit (staged tasks.md)   post-merge (merged tasks.md) │
└────────────────────┬─────────────────────┬───────────────────┘
                     ▼                     ▼
                ┌─────────────────────────────────┐
                │ skills/coordinator-task-status- │
                │ renderer/scripts/                │
                │   render_tasks_status.py         │
                └────────────┬────────────────────┘
                             │
                             ▼  (read)
                ┌─────────────────────────────────┐
                │ skills/coordination-bridge/      │
                │ scripts/coordination_bridge.py:  │
                │   try_issue_list(labels=...)     │
                └────────────┬────────────────────┘
                             │
                             ▼  (HTTPS)
                ┌─────────────────────────────────┐
                │ agent-coordinator HTTP API       │
                │   GET /issues?labels=change:...  │
                │   (existing endpoint)            │
                └─────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ /plan-feature Gate 2 (Plan Approval)                          │
└────────────────────┬─────────────────────────────────────────┘
                     ▼
                ┌─────────────────────────────────┐
                │ skills/coordinator-task-status- │
                │ renderer/scripts/                │
                │   seed_tasks_from_md.py          │
                └────────────┬────────────────────┘
                             │
                             ▼  (write)
                ┌─────────────────────────────────┐
                │ coordinator: POST /issues/create │
                │ with issue_type=task,            │
                │ labels=[change:<id>,task:<key>], │
                │ depends_on=[UUIDs]               │
                └─────────────────────────────────┘
```

The renderer never writes to the coordinator. The seeder never reads `tasks.md` apart from parsing it for task definitions to seed.

## Decisions

### D1: Reuse `<!-- GENERATED: begin/end <name> -->` markers from plan-roadmap renderer

The repo already has a managed-block convention in `skills/plan-roadmap/scripts/renderer.py`. The marker regexes (`_GEN_BEGIN_RE`, `_GEN_END_RE`) and the helpers `_gen_block()` and `_extract_generated_blocks()` are reusable in spirit but are module-private (underscore-prefixed) and not exported.

**Decision:** the renderer SHALL duplicate the marker constants and the two helpers `_gen_block` and `_extract_generated_blocks` locally rather than reach into a private import. The cost is ~20 lines of duplicated code; the benefit is no cross-skill coupling on private symbols.

**Specifically NOT reused:** `_extract_human_sections` from plan-roadmap is hardcoded to roadmap-specific section names (`## Cross-Cutting Themes`, `## Out of Scope`). It is unsuitable for `tasks.md`. The renderer SHALL implement its own "preserve everything outside markers" extraction as a simple two-piece split: `(prefix_before_begin_marker, suffix_after_end_marker)`. No section-awareness is needed because the renderer never touches content outside the markers.

**Why:** consistency across managed-block uses in the repo; the marker syntax is unambiguous (`<!-- GENERATED: begin <name> -->`), and reviewers familiar with `plan-roadmap` recognize the pattern.

**Block name:** `coordinator:tasks-status`. The colon distinguishes it from existing plan-roadmap block names without breaking the parser (markers match by full name string, not by prefix).

### D2: Both `pre-commit` and `post-merge` hooks

The discovery question established that committer-side drift (caught by pre-commit) and pull-side drift (caught by post-merge) are non-overlapping concerns and that the dominant audience is human PR reviewers reading committed state.

Both hooks fall back to a stale-marker if the coordinator is unreachable, so neither can block git operations. The cost per hook fire is one HTTPS call with a short timeout (≤2s recommended).

**Auto-staging in pre-commit:** the renderer modifies the working tree; pre-commit then runs `git add` against the rendered file before the commit completes. This follows the existing pattern used by `.githooks/pre-commit` for ruff import sorting.

### D3: Seed at `/plan-feature` Gate 2, not lazily

Issues exist in the coordinator from the moment the plan is approved. Alternatives considered:
- **Seed at `/implement-feature` start**: rejected because `tasks.md` between Gate 2 and implementation start would have no coordinator state to render — the renderer would show all stale markers during that window.
- **Lazy on first reference**: rejected as too implicit; a renderer that silently mutates the coordinator on read is hard to reason about.

The seeder is idempotent on `(change:<id>, task:<key>)` labels, so re-running Gate 2 (e.g., after a "Revise tasks" loop) does not create duplicates. Idempotency check: query `try_issue_list(labels=["change:<id>"])`, build the set of existing `task:<key>` labels, and only POST for task keys not already present.

### D4: Stale-marker fallback rather than silent skip or hard fail

The discovery question selected this over the alternatives because:
- **Silent skip**: leaves the last-rendered state visible with no indication of staleness — defeats the trust-restoration goal.
- **Hard fail**: couples local git operations to remote coordinator uptime — unacceptable UX hit.

The stale marker is a single-line block:
```
> Coordinator unreachable at 2026-05-14T10:42Z — status frozen.
```
It is visible in `tasks.md` and in PR diffs, surfacing the outage to reviewers without disrupting operations. The next successful renderer invocation overwrites it cleanly.

### D5: Labels-based filtering rather than a dedicated `GET /issues/by-change/<id>` endpoint

The existing `IssueService.list_issues(labels=["change:<id>"])` path is sufficient at OpenSpec scale (typically 10–30 tasks per change). A convenience endpoint would save a label-filter step on the client but adds API surface. Defer to a follow-up if the label-filter pattern becomes a hotspot.

### D6: Renderer is invoked per-change-id, not globally

Each hook invocation scopes the render to the specific change-id(s) whose `tasks.md` is staged/merged. The hook is responsible for detecting which paths changed; the renderer takes a single change-id argument.

**Why:** keeps the renderer single-purpose; lets hooks run multiple invocations in parallel if multiple change tasks.md files are staged in one commit.

### D7: Identity is carried by labels (`change:<id>`, `task:<key>`), not by `metadata.*`

Line numbers in `tasks.md` are unstable across edits, so they cannot serve as identity. The compound identity for an issue is the pair of labels `("change:<change-id>", "task:<task_key>")` — both human-readable, both stable, both queryable through the existing `try_issue_list(labels=...)` filter.

**Why labels and not `metadata`:** The current `POST /issues/create` API (`IssueCreateRequest` at `agent-coordinator/src/coordination_api.py:90`) accepts only `title|description|issue_type|priority|labels|parent_id|assignee|depends_on`. There is no `metadata` field on the request, and the service derives `metadata` from `description` only. Adding a `metadata` write path would require:
- Extending `IssueCreateRequest` with a `metadata` field
- Extending `IssueService.create()` to merge incoming metadata into the JSONB write
- Adding a `metadata` parameter to `coordination_bridge.try_issue_create`
- A new metadata-filtering query path (JSONB containment) for idempotency lookup

That is enough surface to warrant a separate proposal. Encoding `task:<key>` as a label uses the existing labels indexed GIN index and the existing label-filter idempotency path. The `tasks_md_anchor` breadcrumb is therefore deferred to a follow-up.

**Reserved label namespaces** used by this change:
- `change:<change-id>` — owns the change-id identity of the issue.
- `task:<task_key>` — owns the per-change task identity.
- `wp:<work-package-id>` — applied later by `/implement-feature`, not by the seeder.

No other consumer in the repo currently uses the `task:` label prefix; this proposal claims it.

## Performance

- Renderer worst case: one HTTPS round-trip + ~10–30 issues parsed + file rewrite. Target <500ms on a healthy coordinator; tolerate up to the configured hook timeout (default 5s).
- Pre-commit added latency: equal to renderer latency, only when `tasks.md` is staged. Most commits will not touch `tasks.md`.
- Post-merge added latency: equal to renderer latency, only when a merge touched `tasks.md`.
- Network failure path: short circuit at coordination-bridge timeout (~2s) into stale-marker write.

### D8: Dependency-ordered single-pass seeding

The spec requires `depends_on = [<UUIDs of issues for upstream tasks>]`. UUIDs are assigned on creation, so the seeder must know upstream UUIDs at the moment it POSTs a downstream issue. Two strategies were considered:

- **Two-pass (POST all, then PATCH depends_on):** rejected because the current `POST /issues/update` API (`IssueUpdateRequest`) accepts only `title|description|status|priority|labels|assignee|issue_type` — there is **no** `depends_on` field on update. Adding one is out of scope.
- **Single-pass in topological order:** the seeder parses all task `**Dependencies**:` annotations from `tasks.md`, builds a DAG, topologically sorts, then POSTs from root to leaf. Each POST can include the already-resolved upstream UUIDs in its `depends_on`. **Selected.**

The seeder SHALL fail loudly (exit 1) if the dependency graph parsed from `tasks.md` contains a cycle. Forward references to task keys that do not appear in the file SHALL be logged as warnings and dropped from `depends_on` (not fatal).

### D9: Behavior when coordinator is unreachable AND markers are absent

When the renderer is invoked against a `tasks.md` that has no managed-block markers and the coordinator HTTP call fails, the renderer SHALL append the managed-block markers to the end of the file with the stale-marker as the content, in a single write:

```
<!-- GENERATED: begin coordinator:tasks-status -->
> Coordinator unreachable at <ISO-8601 timestamp> — status frozen.
<!-- GENERATED: end coordinator:tasks-status -->
```

This guarantees the markers exist for the next successful invocation to repaint, even if the first run hit an outage.

## Open Questions

1. **Should the renderer also surface `depends_on` chains in the block** (e.g., "T3: blocked on T2")? The spec includes it as part of the status annotation; the implementer may choose to defer this to a v2 if the basic checkbox + claimed_by view solves the immediate pain.
2. **How are work-package labels (`wp:<id>`) reconciled with plan-time seeding** when work-packages.yaml isn't generated until `/plan-feature` Step 8 (after task seeding would naturally fire)? Resolution: defer wp-label assignment to `/implement-feature` start, which can PATCH labels via `try_issue_update(labels=...)`. Seeder at Gate 2 only sets the `change:<id>` and `task:<key>` labels. (Note: `try_issue_update` does support label updates — see `coordination_bridge.py:976`.)
3. **Should the renderer write to a `.skip-render` sentinel** to suppress the next hook fire (escape valve for emergencies)? Not in v1; revisit if a real need surfaces.
4. **Should the renderer block work-tree state outside `tasks.md`?** No. The renderer SHALL only read+write `openspec/changes/<change-id>/tasks.md`. It SHALL NOT touch the index, other files, or git state. Auto-staging is the *hook's* responsibility (D2), not the renderer's.
