# Add Coordinator Task-Status Renderer

## Why

Markdown checkboxes in `openspec/changes/<change-id>/tasks.md` are not reliably ticked off as work progresses. The observed failure is **display drift**: agents complete tasks (recording the transition in the coordinator) but forget to flip the corresponding `- [ ]` to `- [x]` in the markdown. Human reviewers reading the PR see stale state and lose trust in the artifact; downstream skills (`/cleanup-feature`) that scan checkboxes for "open tasks" pick up false positives.

The underlying execution is fine — the coordinator's `work_queue` table (extended by migration 017 with labels, parent_id, metadata) accurately records task status, assignee, dependencies, and timing. The gap is purely *projection*: nothing renders that authoritative state back into the human-facing markdown.

This proposal closes the gap by treating `tasks.md` as a hybrid document: hand-authored task definitions surrounded by a coordinator-owned status block, regenerated on git hook fire. The agent-discipline failure mode (forgetting to tick boxes) is removed because the human is no longer in the loop for that field.

## What Changes

1. **New skill** `coordinator-task-status-renderer` at `skills/coordinator-task-status-renderer/` with a `scripts/render_tasks_status.py` that reads coordinator issue state for a given change-id and updates a managed block in `tasks.md`.
2. **Seeding in `/plan-feature`** (Gate 2): when the user approves the plan, plan-feature POSTs each task from `tasks.md` to the coordinator as an issue with `labels=["change:<change-id>", "task:<task_key>"]`. Idempotency keys on the `(change:<id>, task:<key>)` label pair. (Rationale: the current `POST /issues/create` API does not accept a `metadata` field; encoding the task key as a label avoids expanding API surface while remaining queryable via the existing `try_issue_list(labels=...)` filter. See D7.)
3. **Hook wiring**: `.githooks/pre-commit` invokes the renderer for any change-id whose `tasks.md` is staged; `.githooks/post-merge` invokes the renderer for any change-id whose `tasks.md` was touched by the merge. Both fall back to a stale-marker on coordinator failure rather than blocking git operations.
4. **Managed block format** in `tasks.md`:
   ```
   <!-- GENERATED: begin coordinator:tasks-status -->
   - [x] T1: implement foo         — done by wp-backend 2026-05-13 (ci/run/4821)
   - [ ] T2: deploy foo            — in_progress, claimed by wp-deploy 2026-05-14
   - [ ] T3: smoke test            — blocked on T2
   <!-- GENERATED: end coordinator:tasks-status -->
   ```
   Reuses the existing marker pattern from `skills/plan-roadmap/scripts/renderer.py`.
5. **Optional coordinator-side convenience endpoint** `GET /issues/by-change/<change-id>` to avoid client-side label filtering. Falls back to existing `list_issues(labels=[...])` if not added in v1.

## What Doesn't Change

- `tasks.md` hand-authored prose, descriptions, and acceptance criteria above and below the managed block are preserved.
- The coordinator's `work_queue` schema — no migrations required. The existing `labels TEXT[]` column carries both `change:<id>` and `task:<key>` labels; no `metadata` write path is required for v1.
- The coordinator's HTTP API surface — `POST /issues/create` and `POST /issues/list` are used as-is. No new fields are added to `IssueCreateRequest` / `IssueListRequest`.
- `/implement-feature`'s per-commit checkbox-flip discipline is retained as a fallback; the renderer simply makes it unnecessary when working correctly.
- `/cleanup-feature`'s open-task scanning logic — managed-block output remains valid GFM checkbox syntax that the existing scanner handles unchanged.

## Approaches Considered

### Approach 1: Managed block inside `tasks.md` (Recommended)

The renderer owns content between `<!-- GENERATED: begin coordinator:tasks-status -->` markers in `tasks.md`. Hand-authored prose lives outside the markers. Pre-commit and post-merge hooks invoke the renderer. Coordinator-down inserts a stale-marker.

**Pros**:
- Single document — humans read one file, no sidecar to chase.
- Reuses the proven marker pattern from `plan-roadmap/scripts/renderer.py` (`_gen_block`, `_extract_human_sections`).
- Reuses `coordination_bridge.try_issue_list()` for the read path — no new HTTP client.
- `.githooks/post-merge` is currently a no-op placeholder — clean insertion with no merge conflict.
- PR diffs surface status changes naturally as part of the existing file's history.
- Compatible with `/cleanup-feature`'s checkbox scanner.

**Cons**:
- Each commit during implementation re-renders the block, creating per-commit churn in `tasks.md` history (~5–15 line diffs).
- Hand-edits inside the managed block are silently clobbered (this is the design intent — it removes the discipline failure mode — but it's a sharp edge if someone is unaware).
- Renderer must auto-stage the modified file in pre-commit (pattern already established by ruff hook in `.githooks/pre-commit`, but still extra state to manage).

**Effort**: **S** (~250 lines net: 150 renderer + 50 seeder + 20 hook wiring + ~30 plan-feature edits, leveraging two major existing components)

### Approach 2: Sidecar `tasks.status.md` file

Renderer writes a separate file `openspec/changes/<change-id>/tasks.status.md` adjacent to `tasks.md`. `tasks.md` stays 100% hand-authored. Hooks unchanged from Approach 1.

**Pros**:
- Zero risk of clobbering hand-edits anywhere in `tasks.md`.
- Cleaner "this is generated" boundary at the file level.
- Easier to add to `.gitignore` later if generated state becomes noise (or to keep in git for PR-review surfacing).

**Cons**:
- Two files to look at — reviewers may miss the sidecar entirely, undermining the "display matches reality" goal.
- PR diffs split across two files; harder to correlate "this commit advanced these tasks."
- `/cleanup-feature` and any other consumer would need to learn about the sidecar to scan correct state.
- Doesn't fix `tasks.md` itself — the document the user actually opens stays stale.

**Effort**: **S** (~200 lines net, fewer hook complexities)

### Approach 3: Auto-updating PR comment

Renderer posts an auto-updating comment on the GitHub PR for each change. Triggered by GH webhook events (PR open, push, review). No managed block in `tasks.md`; no git hooks.

**Pros**:
- Zero churn in `tasks.md` commit history.
- Native GitHub UX — reviewers see status without leaving the PR review tab.
- Renderer state lives in coordinator + GH; no third source of truth in git.
- No risk of clobbering anything.

**Cons**:
- Requires a PR to exist — no visibility during planning or pre-PR implementation phases (significant gap for `/plan-feature` Gate 2 output).
- Requires GH MCP integration and webhook subscription per repo — added operational surface.
- Doesn't help anyone working from the local checkout (operators running `git pull`, agents reading `tasks.md` to decide what to do).
- Outside the local-first workflow ethos — the repo's CLAUDE.md emphasizes git-tracked artifacts.

**Effort**: **M** (~400 lines: GH webhook handler, PR comment management, dedupe of stacked comments, fallback when GH unreachable)

### Selected Approach

**Approach 1: Managed block in `tasks.md`.** Selected at Gate 1 (Direction Approval).

Discovery-question decisions baked in:
- **Trigger points**: Both `pre-commit` and `post-merge` hooks (covers committer-side drift and pull-side drift; non-overlapping concerns).
- **Seeding timing**: At `/plan-feature` Gate 2 approval. Issues exist in the coordinator from the moment the plan is approved.
- **Coordinator-down fallback**: Replace managed block with explicit stale-marker (`> Coordinator unreachable since <timestamp> — status frozen.`). Never block git operations.

## Recommended: Approach 1

Approach 1 wins on three grounds:

1. **It fixes the file the user actually looks at.** The stated problem is "tasks.md doesn't reflect reality." A sidecar (#2) or PR comment (#3) leaves `tasks.md` itself unchanged and untrusted.
2. **It composes with the existing skill ecosystem.** `/plan-feature`, `/implement-feature`, `/cleanup-feature`, and human reviewers all already read `tasks.md`. None of them need to learn about the renderer for the rendered state to flow through.
3. **Build cost is low because of two big reuse wins.** `plan-roadmap/scripts/renderer.py` already implements the managed-block pattern; `coordination_bridge.try_issue_list()` already handles the coordinator HTTP path. The genuinely new code is small (~250 lines), confined to one new skill plus minor edits.

The main risk — silently clobbered hand-edits inside the managed block — is mitigated by clear `<!-- GENERATED: -->` markers and a note in the skill's SKILL.md describing the convention.

## Out of Scope

- Hard validation gating (refuse to advance a task without evidence). The renderer is a *projection*, not an enforcement gate. If the underlying problem proves to be agents fabricating completions rather than forgetting to tick boxes, a separate proposal would add evidence verification — the `result.evidence_uri` convention is wired so a future gate can read it.
- Generalizing the renderer to other files beyond `tasks.md` (e.g., `proposal.md` status sections, `session-log.md` summaries). Out of scope for v1; revisit if multiple managed-block use cases emerge.
- Backfilling existing in-flight changes' issues into the coordinator. New behavior applies to changes created/approved after this lands. Manual backfill is a one-shot script the operator can run if desired.
- Migrating away from the `/implement-feature` per-commit checkbox-flip discipline. The renderer makes it redundant, but removing it is a separate cleanup.
