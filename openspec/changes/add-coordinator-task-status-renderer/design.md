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
                │ coordinator: POST /work/submit   │
                │ with issue_type=task, labels,    │
                │ metadata.task_key, depends_on    │
                └─────────────────────────────────┘
```

The renderer never writes to the coordinator. The seeder never reads `tasks.md` apart from parsing it for task definitions to seed.

## Decisions

### D1: Reuse `<!-- GENERATED: begin/end <name> -->` markers from plan-roadmap renderer

The repo already has a managed-block convention in `skills/plan-roadmap/scripts/renderer.py` with helpers `_gen_block()`, `_extract_generated_blocks()`, `_extract_human_sections()`. We import or duplicate (TBD by implementer) those helpers rather than inventing new marker syntax.

**Why:** consistency across managed-block uses in the repo; the helpers are already tested; reviewers familiar with `plan-roadmap` recognize the pattern.

**Block name:** `coordinator:tasks-status`. The colon distinguishes it from existing plan-roadmap block names without breaking the parser (markers match by full name string, not by prefix).

### D2: Both `pre-commit` and `post-merge` hooks

The discovery question established that committer-side drift (caught by pre-commit) and pull-side drift (caught by post-merge) are non-overlapping concerns and that the dominant audience is human PR reviewers reading committed state.

Both hooks fall back to a stale-marker if the coordinator is unreachable, so neither can block git operations. The cost per hook fire is one HTTPS call with a short timeout (≤2s recommended).

**Auto-staging in pre-commit:** the renderer modifies the working tree; pre-commit then runs `git add` against the rendered file before the commit completes. This follows the existing pattern used by `.githooks/pre-commit` for ruff import sorting.

### D3: Seed at `/plan-feature` Gate 2, not lazily

Issues exist in the coordinator from the moment the plan is approved. Alternatives considered:
- **Seed at `/implement-feature` start**: rejected because `tasks.md` between Gate 2 and implementation start would have no coordinator state to render — the renderer would show all stale markers during that window.
- **Lazy on first reference**: rejected as too implicit; a renderer that silently mutates the coordinator on read is hard to reason about.

The seeder is idempotent on `(change_id, task_key)`, so re-running Gate 2 (e.g., after a "Revise tasks" loop) does not create duplicates.

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

### D7: Seeding metadata includes `task_key` and `change_id`, not the tasks.md line number as a primary key

Line numbers in `tasks.md` are unstable across edits. The primary key for an issue in the coordinator is `(change_id, task_key)` — both human-readable, both stable. `metadata.tasks_md_anchor` may record the line number as a best-effort breadcrumb but the renderer SHALL NOT rely on it for correctness.

## Performance

- Renderer worst case: one HTTPS round-trip + ~10–30 issues parsed + file rewrite. Target <500ms on a healthy coordinator; tolerate up to the configured hook timeout (default 5s).
- Pre-commit added latency: equal to renderer latency, only when `tasks.md` is staged. Most commits will not touch `tasks.md`.
- Post-merge added latency: equal to renderer latency, only when a merge touched `tasks.md`.
- Network failure path: short circuit at coordination-bridge timeout (~2s) into stale-marker write.

## Open Questions

1. **Should the renderer also surface `depends_on` chains in the block** (e.g., "T3: blocked on T2")? The spec includes it as part of the status annotation; the implementer may choose to defer this to a v2 if the basic checkbox + claimed_by view solves the immediate pain.
2. **How are work-package labels (`wp:<id>`) reconciled with plan-time seeding** when work-packages.yaml isn't generated until `/plan-feature` Step 8 (after task seeding would naturally fire)? Resolution: defer wp-label assignment to `/implement-feature` start, which can PATCH labels via the issue_service. Seeder at Gate 2 only sets the `change:<id>` label.
3. **Should the renderer write to a `.skip-render` sentinel** to suppress the next hook fire (escape valve for emergencies)? Not in v1; revisit if a real need surfaces.
