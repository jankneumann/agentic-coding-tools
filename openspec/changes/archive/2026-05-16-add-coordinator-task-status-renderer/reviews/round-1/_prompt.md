# PLAN_REVIEW — round 1

You are reviewing the OpenSpec change `add-coordinator-task-status-renderer`.
This change introduces a new skill that renders coordinator-recorded task
state into a managed block inside `openspec/changes/<id>/tasks.md`, plus a
seeder invoked at `/plan-feature` Gate 2 and pre-commit/post-merge hooks.

## Context — previous self-review (PLAN_ITERATE) already addressed
1. Seeder uses labels (`change:<id>` + `task:<key>`) for identity — no metadata field
2. HTTP endpoint corrected to `/issues/create` (not `/work/submit`)
3. Single-pass topological seeding with cycle detection (D8)
4. Renderer SHALL NOT import private symbols from plan-roadmap — duplicates ~20 LOC
5. Markers-absent + coordinator-unreachable single-write contract (D9)
6. Hermetic hook-test fixture (tmp_path git repo + renderer-stub env var)

## What to review
Read all plan artifacts in the directory and evaluate:
- Correctness: do design decisions hold? Are spec scenarios consistent with each other?
- Completeness: are there missing edge cases (race conditions, partial failures, format ambiguity)?
- Feasibility: is each work-package executable as specified in 60–180 minutes?
- Testability: does each scenario have a clear assertion strategy?
- Scope: anything in here that should be deferred to follow-ups?
- Adherence to repo conventions (CLAUDE.md, skill layout, OpenSpec workflow, coordination_bridge naming)

## Artifacts

### proposal.md
```
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

```

### design.md
```
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

```

### tasks.md
```
# Tasks — add-coordinator-task-status-renderer

> **Bootstrap note:** this change's own `tasks.md` will not have a renderer-managed block during implementation (the renderer doesn't exist yet). Implementers should follow existing `/implement-feature` discipline (per-commit checkbox flips) for this change. Future changes will get the managed block automatically from Gate 2 forward.

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 Document renderer CLI invocation contract in `contracts/README.md`
  **Spec scenarios**: coordinator-task-status-renderer.1 (block reflects state), .4 (markers absent)
  **Design decisions**: D6 (per-change-id invocation)
  **Dependencies**: None
  **Size**: S

- [ ] 1.2 Document seeder CLI invocation contract in `contracts/README.md`
  **Spec scenarios**: coordinator-task-status-renderer.7 (seeding), .8 (idempotency), .9 (coordinator-unreachable seeding)
  **Design decisions**: D3 (seed at Gate 2), D7 (task_key as primary key)
  **Dependencies**: 1.1
  **Size**: S

- [ ] 1.3 Document managed-block format and marker name in `contracts/README.md`
  **Spec scenarios**: coordinator-task-status-renderer.1, .2 (hand-content preservation)
  **Design decisions**: D1 (reuse plan-roadmap markers)
  **Dependencies**: 1.1
  **Size**: XS

- [ ] 1.4 Checkpoint: run `openspec validate add-coordinator-task-status-renderer --strict`, review contracts/README.md against spec scenarios
  **Dependencies**: 1.1, 1.2, 1.3

## Phase 2 — Renderer skill (wp-renderer-skill)

- [ ] 2.1 Write test: managed-block insertion when absent
  **Spec scenarios**: coordinator-task-status-renderer.4 (markers absent — renderer inserts)
  **Contracts**: contracts/README.md (managed-block format)
  **Design decisions**: D1
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.2 Write test: managed-block replacement preserves hand-content
  **Spec scenarios**: coordinator-task-status-renderer.2 (hand-authored content preserved)
  **Contracts**: contracts/README.md
  **Design decisions**: D1
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.3 Write test: renderer is idempotent on re-run
  **Spec scenarios**: coordinator-task-status-renderer.3 (re-render idempotent)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.4 Write test: stale-marker inserted on coordinator failure
  **Spec scenarios**: coordinator-task-status-renderer.5 (stale marker), .6 (recovery)
  **Design decisions**: D4 (stale-marker fallback)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.4a Write test: markers absent AND coordinator unreachable on first invocation — single-write inserts markers with stale-marker content
  **Spec scenarios**: "Markers absent AND coordinator unreachable on first invocation"
  **Design decisions**: D9
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.5 Checkpoint: run `pytest skills/tests/coordinator-task-status-renderer/test_render*.py` — confirm tests RED
  **Dependencies**: 2.1, 2.2, 2.3, 2.4, 2.4a

- [ ] 2.6 Implement `skills/coordinator-task-status-renderer/scripts/render_tasks_status.py` using `try_issue_list` and locally-duplicated marker helpers (do NOT import the underscore-prefixed `_gen_block` / `_extract_generated_blocks` from `plan-roadmap/scripts/renderer.py` — duplicate them; do NOT use `_extract_human_sections`, write a marker-aware prefix/suffix splitter instead, per D1)
  **Spec scenarios**: coordinator-task-status-renderer.1, .2, .3, .4, .4a (markers absent + coordinator down), .5, .6
  **Design decisions**: D1, D4, D5 (labels-based filtering), D6, D7 (extract task_key from `task:<key>` label), D9 (markers absent + unreachable single-write)
  **Dependencies**: 2.5
  **Size**: M

- [ ] 2.7 Confirm tests 2.1–2.4 are GREEN
  **Dependencies**: 2.6
  **Size**: XS

- [ ] 2.8 Write test: seeder POSTs correct labels and metadata per task
  **Spec scenarios**: coordinator-task-status-renderer.7 (issues created)
  **Contracts**: contracts/README.md (seeder CLI)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.9 Write test: seeder is idempotent on `(change:<id>, task:<key>)` label pair (matches by querying `try_issue_list(labels=["change:<id>"])` and reading the `task:<key>` label off each returned issue)
  **Spec scenarios**: coordinator-task-status-renderer.8 (re-run after partial seeding)
  **Design decisions**: D3, D7
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.9a Write test: seeder topologically orders POSTs by `**Dependencies**:` and aborts with exit 1 on cycle
  **Spec scenarios**: "Seeding aborts on dependency cycle"
  **Design decisions**: D8
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.10 Write test: seeder logs warning but exits success when coordinator unreachable
  **Spec scenarios**: coordinator-task-status-renderer.9 (unreachable at Gate 2)
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Size**: S

- [ ] 2.11 Checkpoint: confirm seeder tests RED
  **Dependencies**: 2.8, 2.9, 2.9a, 2.10

- [ ] 2.12 Implement `skills/coordinator-task-status-renderer/scripts/seed_tasks_from_md.py` using `try_issue_create` (per contracts/README — POSTs `labels=["change:<id>", "task:<key>"]` plus `depends_on=[UUIDs]`; does NOT pass `metadata` because `IssueCreateRequest` does not accept it; topological order per D8)
  **Spec scenarios**: coordinator-task-status-renderer.7, .8, .9, "Seeding aborts on dependency cycle"
  **Design decisions**: D3, D7, D8
  **Dependencies**: 2.11
  **Size**: M

- [ ] 2.13 Confirm tests 2.8–2.9a, 2.10 are GREEN
  **Dependencies**: 2.12
  **Size**: XS

- [ ] 2.14 Write `skills/coordinator-task-status-renderer/SKILL.md` with frontmatter (`user_invocable: false`, triggers, related skills)
  **Spec scenarios**: coordinator-task-status-renderer.10 (skill auto-installed), .11 (tests excluded)
  **Dependencies**: 2.7, 2.13
  **Size**: S

- [ ] 2.15 Checkpoint: run `bash skills/install.sh --mode rsync --deps none --python-tools none` and verify skill appears in `.claude/skills/` and `.agents/skills/`; confirm `skills/tests/` is excluded
  **Dependencies**: 2.14

## Phase 3 — Plan-feature integration (wp-plan-feature-integration)

- [ ] 3.1 Write test: `/plan-feature` Gate 2 approval triggers seeder for the change-id
  **Spec scenarios**: coordinator-task-status-renderer.7
  **Contracts**: contracts/README.md (seeder CLI)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 3.2 Write test: Gate 2 re-approval does not duplicate issues
  **Spec scenarios**: coordinator-task-status-renderer.8
  **Dependencies**: 1.4
  **Size**: S

- [ ] 3.3 Checkpoint: confirm plan-feature integration tests RED
  **Dependencies**: 3.1, 3.2

- [ ] 3.4 Edit `skills/plan-feature/SKILL.md` Step 12 to invoke seeder on "Approve" selection
  **Spec scenarios**: coordinator-task-status-renderer.7, .8
  **Design decisions**: D3
  **Dependencies**: 3.3
  **Size**: S

- [ ] 3.5 Confirm tests 3.1–3.2 are GREEN
  **Dependencies**: 3.4
  **Size**: XS

## Phase 4 — Hook wiring (wp-hooks)

> **Hook test strategy.** Hook tests SHALL use pytest with a `tmp_path` git fixture: initialize a throwaway git repo, set `core.hooksPath` to the repo's `.githooks/`, stage a synthetic `openspec/changes/<id>/tasks.md`, and run `git commit` (or `git merge` for post-merge). The renderer SHALL be stubbed via a `COORDINATOR_TASK_STATUS_RENDERER` env var pointing at a fake script that records its invocation argv to a temp file. This keeps tests hermetic — no real coordinator HTTP calls, no real `python3` invocation of the actual renderer — and lets the hook layer be tested independently of the renderer. The renderer's own tests (Phase 2) cover the rendering logic.

- [ ] 4.1 Write test: pre-commit invokes renderer when `openspec/changes/<id>/tasks.md` is staged
  **Spec scenarios**: coordinator-task-status-renderer.12 (pre-commit fires on staged tasks.md)
  **Design decisions**: D2 (both hooks)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.2 Write test: pre-commit re-stages the rendered file
  **Spec scenarios**: coordinator-task-status-renderer.12
  **Design decisions**: D2 (auto-staging follows ruff pattern)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.3 Write test: pre-commit skips renderer when no tasks.md staged
  **Spec scenarios**: coordinator-task-status-renderer.13 (unrelated commit untouched)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.4 Checkpoint: confirm pre-commit tests RED
  **Dependencies**: 4.1, 4.2, 4.3

- [ ] 4.5 Edit `.githooks/pre-commit` to detect staged tasks.md paths, invoke renderer, re-stage
  **Spec scenarios**: coordinator-task-status-renderer.12, .13, .14 (renderer failure non-blocking)
  **Design decisions**: D2
  **Dependencies**: 4.4
  **Size**: S

- [ ] 4.6 Confirm pre-commit tests 4.1–4.3 are GREEN
  **Dependencies**: 4.5
  **Size**: XS

- [ ] 4.7 Write test: post-merge invokes renderer when merge touched tasks.md
  **Spec scenarios**: coordinator-task-status-renderer.15 (post-merge fires on merged tasks.md)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.8 Write test: post-merge skips renderer when merge did not touch tasks.md
  **Spec scenarios**: coordinator-task-status-renderer.16 (post-merge no-touch case)
  **Dependencies**: 1.4
  **Size**: S

- [ ] 4.9 Checkpoint: confirm post-merge tests RED
  **Dependencies**: 4.7, 4.8

- [ ] 4.10 Edit `.githooks/post-merge` (currently no-op stub) to detect merged tasks.md paths and invoke renderer
  **Spec scenarios**: coordinator-task-status-renderer.15, .16
  **Design decisions**: D2
  **Dependencies**: 4.9
  **Size**: S

- [ ] 4.11 Confirm post-merge tests 4.7–4.8 are GREEN
  **Dependencies**: 4.10
  **Size**: XS

## Phase 5 — Integration and documentation (wp-integration)

- [ ] 5.1 Write end-to-end test: seed via plan-feature → modify coordinator state → commit triggers render → tasks.md reflects current state
  **Spec scenarios**: composite (all coordinator-task-status-renderer scenarios in a single flow)
  **Dependencies**: 2.15, 3.5, 4.6, 4.11
  **Size**: M

- [ ] 5.2 Confirm end-to-end test GREEN
  **Dependencies**: 5.1
  **Size**: XS

- [ ] 5.3 Update `docs/skills-catalogue.md` with `coordinator-task-status-renderer` entry
  **Dependencies**: 5.2
  **Size**: XS

- [ ] 5.4 Update `CLAUDE.md` "Workflow" section if appropriate (note that tasks.md status blocks are coordinator-rendered)
  **Dependencies**: 5.2
  **Size**: XS

- [ ] 5.5 Final checkpoint: run full skill test suite, verify `openspec validate add-coordinator-task-status-renderer --strict` passes, run `python3 skills/validate-packages/scripts/validate_work_packages.py openspec/changes/add-coordinator-task-status-renderer/work-packages.yaml`
  **Dependencies**: 5.3, 5.4

```

### work-packages.yaml
```
schema_version: 1

feature:
  id: add-coordinator-task-status-renderer
  title: "Coordinator-owned task-status managed block in tasks.md"
  plan_revision: 1
  created_by: claude-opus-4-7
  created_at: "2026-05-14T12:00:00Z"

contracts:
  revision: 1
  openapi:
    primary: "contracts/README.md"
    files:
      - "contracts/README.md"

defaults:
  priority: 5
  lock_ttl_minutes: 120
  timeout_minutes: 60
  retry_budget: 1
  verification_tier_required: "B"
  min_trust_level: 2

packages:

  # ───────────────────────────────────────────────────────────────────
  # Phase 1 — Contracts (gates everything else)
  # ───────────────────────────────────────────────────────────────────

  - package_id: wp-contracts
    title: "Define CLI contracts for renderer + seeder, and managed-block format"
    task_type: contracts
    description: |
      Author contracts/README.md documenting:
        - render_tasks_status.py CLI invocation (args, exit codes, stdout format)
        - seed_tasks_from_md.py CLI invocation (args, idempotency rules)
        - Managed-block markers and emitted content format
        - Stale-marker format
      Covers tasks 1.1–1.4.
      Spec scenarios: coordinator-task-status-renderer.1, .2, .4, .7, .8, .9
      Design decisions: D1, D3, D5, D6, D7
    role: python-engineer
    priority: 1
    depends_on: []
    timeout_minutes: 45
    retry_budget: 1
    min_trust_level: 2
    locks:
      files:
        - "openspec/changes/add-coordinator-task-status-renderer/contracts/README.md"
      keys:
        - "feature:add-coordinator-task-status-renderer:contracts"
      ttl_minutes: 60
      reason: "Authoring CLI + managed-block contracts"
    scope:
      write_allow:
        - "openspec/changes/add-coordinator-task-status-renderer/contracts/**"
      read_allow:
        - "openspec/**"
        - "skills/plan-roadmap/scripts/renderer.py"
        - "skills/coordination-bridge/scripts/coordination_bridge.py"
        - "agent-coordinator/src/issue_service.py"
        - "agent-coordinator/database/migrations/017_issue_tracking.sql"
    worktree:
      name: "wp-contracts"
      mode: "isolated"
    verification:
      tier_required: "C"
      steps:
        - name: "validate-openspec"
          kind: "command"
          command: "openspec validate add-coordinator-task-status-renderer --strict"
          expect_exit_code: 0
          evidence:
            artifacts: []
            result_keys:
              - "openspec_validate_exit_code"
    outputs:
      result_keys:
        - "contracts_revision"

  # ───────────────────────────────────────────────────────────────────
  # Phase 2 — Renderer skill (parallel after wp-contracts)
  # ───────────────────────────────────────────────────────────────────

  - package_id: wp-renderer-skill
    title: "Build coordinator-task-status-renderer skill: renderer + seeder + tests"
    task_type: implement
    description: |
      Implements the new skill at skills/coordinator-task-status-renderer/:
        - scripts/render_tasks_status.py — reads coordinator via try_issue_list,
          extracts task_key from each issue's `task:<key>` label (NOT metadata),
          renders the managed block. Locally duplicates the `_gen_block` and
          `_extract_generated_blocks` helpers from plan-roadmap rather than
          importing private symbols. Writes single-pass when markers absent
          AND coordinator unreachable (D9).
        - scripts/seed_tasks_from_md.py — parses tasks.md and `**Dependencies**:`
          annotations, topologically sorts task keys, and POSTs via
          try_issue_create with `labels=["change:<id>", "task:<key>"]` plus
          `depends_on=[UUIDs]`. Does NOT pass `metadata` (current
          IssueCreateRequest does not accept it; carrying identity in labels
          per D7). Idempotency check reads `task:<key>` labels off existing
          issues returned by `try_issue_list(labels=["change:<id>"])`.
          Exits 1 on dependency cycle (D8).
        - SKILL.md with frontmatter (user_invocable: false).
      Tests at skills/tests/coordinator-task-status-renderer/.
      Covers tasks 2.1–2.15 (including 2.4a, 2.9a).
      Spec scenarios: coordinator-task-status-renderer.1, .2, .3, .4, "Markers absent AND coordinator unreachable on first invocation", .5, .6, .7, .8, "Seeding aborts on dependency cycle", .9, .10, .11
      Design decisions: D1, D3, D4, D5, D6, D7, D8, D9
    role: python-engineer
    priority: 2
    depends_on:
      - wp-contracts
    timeout_minutes: 180
    retry_budget: 1
    min_trust_level: 2
    locks:
      files:
        - "skills/coordinator-task-status-renderer/SKILL.md"
        - "skills/coordinator-task-status-renderer/scripts/render_tasks_status.py"
        - "skills/coordinator-task-status-renderer/scripts/seed_tasks_from_md.py"
      keys:
        - "feature:add-coordinator-task-status-renderer:renderer"
        - "feature:add-coordinator-task-status-renderer:tests"
      ttl_minutes: 240
      reason: "Implementing renderer skill scripts and unit tests"
    scope:
      write_allow:
        - "skills/coordinator-task-status-renderer/**"
        - "skills/tests/coordinator-task-status-renderer/**"
      read_allow:
        - "skills/plan-roadmap/scripts/renderer.py"
        - "skills/coordination-bridge/**"
        - "skills/install.sh"
        - "skills/pyproject.toml"
        - "openspec/changes/add-coordinator-task-status-renderer/**"
        - "agent-coordinator/src/issue_service.py"
        - "agent-coordinator/src/work_queue.py"
    worktree:
      name: "wp-renderer-skill"
      mode: "isolated"
    verification:
      tier_required: "B"
      steps:
        - name: "run-unit-tests"
          kind: "command"
          command: "skills/.venv/bin/python -m pytest skills/tests/coordinator-task-status-renderer/ -v"
          expect_exit_code: 0
          evidence:
            artifacts:
              - "skills/tests/coordinator-task-status-renderer/.pytest_cache/"
            result_keys:
              - "renderer_tests_passed"
              - "seeder_tests_passed"
        - name: "install-skill"
          kind: "command"
          command: "bash skills/install.sh --mode rsync --deps none --python-tools none"
          expect_exit_code: 0
          evidence:
            artifacts:
              - ".claude/skills/coordinator-task-status-renderer/SKILL.md"
              - ".agents/skills/coordinator-task-status-renderer/SKILL.md"
            result_keys:
              - "skill_installed"
    outputs:
      result_keys:
        - "renderer_tests_passed"
        - "seeder_tests_passed"
        - "skill_installed"

  # ───────────────────────────────────────────────────────────────────
  # Phase 3 — Plan-feature integration (parallel after wp-contracts)
  # ───────────────────────────────────────────────────────────────────

  - package_id: wp-plan-feature-integration
    title: "Wire seeder into /plan-feature Gate 2 approval step"
    task_type: implement
    description: |
      Edits skills/plan-feature/SKILL.md Step 12 (Gate 2 — Plan Approval) so the
      "Approve" outcome invokes seed_tasks_from_md.py with the change-id.
      Adds skills/tests/plan-feature/test_gate2_invokes_seeder.py asserting the
      seeder is called on approval and skipped on revise/reject paths.
      Covers tasks 3.1–3.5.
      Spec scenarios: coordinator-task-status-renderer.7, .8
      Design decisions: D3
    role: skill-author
    priority: 3
    depends_on:
      - wp-contracts
    timeout_minutes: 60
    retry_budget: 1
    min_trust_level: 2
    locks:
      files:
        - "skills/plan-feature/SKILL.md"
        - "skills/tests/plan-feature/test_gate2_invokes_seeder.py"
      keys:
        - "feature:add-coordinator-task-status-renderer:wiring"
      ttl_minutes: 120
      reason: "Wiring Gate 2 seeder invocation"
    scope:
      write_allow:
        - "skills/plan-feature/SKILL.md"
        - "skills/tests/plan-feature/test_gate2_invokes_seeder.py"
      read_allow:
        - "skills/plan-feature/**"
        - "skills/coordinator-task-status-renderer/**"
        - "skills/coordination-bridge/**"
        - "openspec/changes/add-coordinator-task-status-renderer/**"
    worktree:
      name: "wp-plan-feature-integration"
      mode: "isolated"
    verification:
      tier_required: "B"
      steps:
        - name: "plan-feature-integration-test"
          kind: "command"
          command: "skills/.venv/bin/python -m pytest skills/tests/plan-feature/test_gate2_invokes_seeder.py -v"
          expect_exit_code: 0
          evidence:
            artifacts: []
            result_keys:
              - "plan_feature_integration_passed"
    outputs:
      result_keys:
        - "plan_feature_integration_passed"

  # ───────────────────────────────────────────────────────────────────
  # Phase 4 — Git hooks (parallel after wp-contracts)
  # ───────────────────────────────────────────────────────────────────

  - package_id: wp-hooks
    title: "Wire renderer into .githooks/pre-commit and .githooks/post-merge"
    task_type: implement
    description: |
      Edits .githooks/pre-commit to detect staged openspec/changes/<id>/tasks.md
      paths, invoke render_tasks_status.py for each, and re-stage the rendered
      file (following the existing ruff-import-sort pattern in this file).
      Edits .githooks/post-merge (currently a no-op stub from the beads removal)
      to detect tasks.md files touched by the merge and invoke the renderer.
      Adds skills/tests/githooks/ tests for both hooks using a hermetic
      tmp_path git fixture with a fake renderer stub (see Phase 4 hook test
      strategy note in tasks.md). The hook SHALL respect a
      COORDINATOR_TASK_STATUS_RENDERER env var pointing at an alternate
      script path so tests can substitute the renderer without invoking
      the real coordinator.
      Covers tasks 4.1–4.11.
      Spec scenarios: coordinator-task-status-renderer.12, .13, .14, .15, .16
      Design decisions: D2, D4
    role: shell-engineer
    priority: 4
    depends_on:
      - wp-contracts
    timeout_minutes: 90
    retry_budget: 1
    min_trust_level: 2
    locks:
      files:
        - ".githooks/pre-commit"
        - ".githooks/post-merge"
      keys:
        - "feature:add-coordinator-task-status-renderer:precommit"
        - "feature:add-coordinator-task-status-renderer:postmerge"
      ttl_minutes: 120
      reason: "Editing repo git hooks"
    scope:
      write_allow:
        - ".githooks/pre-commit"
        - ".githooks/post-merge"
        - "skills/tests/githooks/**"
      read_allow:
        - ".githooks/**"
        - "skills/coordinator-task-status-renderer/**"
        - "openspec/changes/add-coordinator-task-status-renderer/**"
    worktree:
      name: "wp-hooks"
      mode: "isolated"
    verification:
      tier_required: "B"
      steps:
        - name: "hook-integration-tests"
          kind: "command"
          command: "skills/.venv/bin/python -m pytest skills/tests/githooks/ -v"
          expect_exit_code: 0
          evidence:
            artifacts: []
            result_keys:
              - "githooks_tests_passed"
    outputs:
      result_keys:
        - "githooks_tests_passed"

  # ───────────────────────────────────────────────────────────────────
  # Phase 5 — Integration (after all implementation packages)
  # ───────────────────────────────────────────────────────────────────

  - package_id: wp-integration
    title: "End-to-end test, docs catalogue, final validation"
    task_type: integrate
    description: |
      Adds end-to-end test at skills/tests/integration/test_coord_task_status_e2e.py
      exercising: seeder run for a fixture change-id → modify coordinator state →
      invoke renderer → assert tasks.md managed block reflects current state.
      Updates docs/skills-catalogue.md with the new skill entry.
      Adds a brief note to CLAUDE.md if the skill list there is currently
      authoritative (otherwise skip).
      Covers tasks 5.1–5.5.
      Spec scenarios: composite e2e
      Design decisions: D1–D7
    role: python-engineer
    priority: 5
    depends_on:
      - wp-renderer-skill
      - wp-plan-feature-integration
      - wp-hooks
    timeout_minutes: 90
    retry_budget: 1
    min_trust_level: 2
    locks:
      files:
        - "skills/tests/integration/test_coord_task_status_e2e.py"
        - "docs/skills-catalogue.md"
        - "CLAUDE.md"
      keys:
        - "feature:add-coordinator-task-status-renderer:docs"
        - "feature:add-coordinator-task-status-renderer:integration"
      ttl_minutes: 120
      reason: "End-to-end validation and docs"
    scope:
      write_allow:
        - "skills/tests/integration/test_coord_task_status_e2e.py"
        - "docs/skills-catalogue.md"
        - "CLAUDE.md"
      read_allow:
        - "skills/**"
        - "openspec/changes/add-coordinator-task-status-renderer/**"
        - ".githooks/**"
        - "agent-coordinator/**"
    worktree:
      name: "wp-integration"
      mode: "isolated"
    verification:
      tier_required: "A"
      steps:
        - name: "e2e-test"
          kind: "command"
          command: "skills/.venv/bin/python -m pytest skills/tests/integration/test_coord_task_status_e2e.py -v"
          expect_exit_code: 0
          evidence:
            artifacts: []
            result_keys:
              - "e2e_passed"
        - name: "validate-packages"
          kind: "command"
          command: "skills/.venv/bin/python skills/validate-packages/scripts/validate_work_packages.py openspec/changes/add-coordinator-task-status-renderer/work-packages.yaml"
          expect_exit_code: 0
          evidence:
            artifacts: []
            result_keys:
              - "work_packages_valid"
        - name: "final-openspec-validate"
          kind: "command"
          command: "openspec validate add-coordinator-task-status-renderer --strict"
          expect_exit_code: 0
          evidence:
            artifacts: []
            result_keys:
              - "openspec_final_valid"
    outputs:
      result_keys:
        - "e2e_passed"
        - "work_packages_valid"
        - "openspec_final_valid"

```

### specs/coordinator-task-status-renderer/spec.md
```
## ADDED Requirements

### Requirement: Coordinator-Owned Status Block in tasks.md

The system SHALL provide a `coordinator-task-status-renderer` skill that regenerates a designated managed block inside `openspec/changes/<change-id>/tasks.md` from coordinator-recorded task state.

The managed block SHALL be delimited by HTML comments using the existing repo convention:

```
<!-- GENERATED: begin coordinator:tasks-status -->
...
<!-- GENERATED: end coordinator:tasks-status -->
```

The renderer SHALL replace only content between these markers and SHALL leave content outside the markers (hand-authored task definitions, prose, acceptance criteria) untouched.

The renderer SHALL be invoked with a single argument: the `<change-id>` of the OpenSpec change whose `tasks.md` it should update.

#### Scenario: Block content reflects current coordinator state

**WHEN** the renderer runs against a change-id whose coordinator issues exist
**THEN** each issue labeled `change:<change-id>` AND carrying a `task:<task_key>` label SHALL appear as one line in the managed block
**AND** each line SHALL be valid GFM checkbox syntax (`- [ ]` for non-closed status, `- [x]` for `closed` with `close_reason` matching `completed|done`)
**AND** each line SHALL include the task key extracted from the `task:<task_key>` label, the issue title, and a status annotation showing the assignee (if set) and the completion timestamp (if set)
**AND** lines SHALL be sorted by task key in ascending natural-numeric order (so `1.2` precedes `1.10`)
**AND** issues lacking a `task:<task_key>` label SHALL be skipped and a single-line warning per skipped issue SHALL be written to stderr

#### Scenario: Hand-authored content outside the block is preserved

**WHEN** the renderer runs against a `tasks.md` that contains hand-authored prose above and below the managed-block markers
**THEN** the renderer SHALL produce a file whose content above the `begin` marker and below the `end` marker is byte-identical to the input
**AND** no other regions of the file SHALL be modified

#### Scenario: Re-render is idempotent when state has not advanced

**WHEN** the renderer runs twice against the same change-id with no intervening coordinator state changes
**THEN** the second invocation SHALL produce a file byte-identical to the first invocation's output
**AND** `git diff` SHALL show no changes after the second invocation

#### Scenario: Managed-block markers absent — renderer inserts them

**WHEN** the renderer runs against a `tasks.md` that does not yet contain the managed-block markers
**THEN** the renderer SHALL append the managed block at the end of the file
**AND** the appended block SHALL begin with `<!-- GENERATED: begin coordinator:tasks-status -->` and end with `<!-- GENERATED: end coordinator:tasks-status -->`

#### Scenario: Markers absent AND coordinator unreachable on first invocation

**WHEN** the renderer runs against a `tasks.md` that does not yet contain the managed-block markers AND the coordinator HTTP call (via `coordination_bridge.try_issue_list`) fails or returns an error
**THEN** the renderer SHALL append the managed block at the end of the file with the stale-marker as its content (a single line `> Coordinator unreachable at <ISO-8601 timestamp> — status frozen.`)
**AND** the appended block SHALL begin with `<!-- GENERATED: begin coordinator:tasks-status -->` and end with `<!-- GENERATED: end coordinator:tasks-status -->`
**AND** the renderer SHALL exit with status 0

---

### Requirement: Coordinator-Unreachable Fallback

When the coordinator API cannot be reached, the renderer SHALL replace the managed block with an explicit stale-marker rather than blocking the calling operation or leaving the previous block unchanged.

#### Scenario: Coordinator HTTP call fails — block shows stale marker

**WHEN** the renderer is invoked and the coordinator API call (via `coordination_bridge.try_issue_list`) fails or returns an error
**THEN** the renderer SHALL replace the managed block with a single-line indicator: `> Coordinator unreachable at <ISO-8601 timestamp> — status frozen.`
**AND** the renderer SHALL exit with status 0 (success — the hook must not block)
**AND** the renderer SHALL log a single-line warning to stderr identifying the change-id and the failure mode

#### Scenario: Coordinator recovers — block repaints on next invocation

**WHEN** a prior invocation inserted the stale marker, the coordinator becomes reachable, and the renderer is invoked again
**THEN** the stale marker SHALL be replaced by the freshly rendered task list
**AND** the rendered content SHALL match the format defined in "Coordinator-Owned Status Block in tasks.md"

---

### Requirement: Pre-commit Hook Integration

The repository's `.githooks/pre-commit` hook SHALL invoke the renderer for any change-id whose `tasks.md` is among the staged files in the pending commit, and SHALL re-stage the file after rendering so that the committed `tasks.md` reflects current coordinator state.

#### Scenario: Staged tasks.md triggers renderer

**WHEN** a developer runs `git commit` after staging `openspec/changes/<change-id>/tasks.md`
**THEN** the pre-commit hook SHALL invoke the renderer with `<change-id>`
**AND** the hook SHALL run `git add` against the rendered file before the commit completes

#### Scenario: Unrelated commit does not trigger renderer

**WHEN** a developer runs `git commit` against staged files that do not include any `openspec/changes/<change-id>/tasks.md` path
**THEN** the pre-commit hook SHALL NOT invoke the renderer for any change-id
**AND** the commit SHALL proceed without additional latency from coordinator HTTP calls

#### Scenario: Renderer failure does not block commit

**WHEN** the renderer exits with a non-zero status (e.g., from a non-coordinator error such as malformed `tasks.md`)
**THEN** the pre-commit hook SHALL log a warning identifying the change-id
**AND** the commit SHALL proceed without re-staging the file

---

### Requirement: Post-merge Hook Integration

The repository's `.githooks/post-merge` hook SHALL invoke the renderer for any change-id whose `tasks.md` was modified by the merge operation that triggered the hook.

#### Scenario: Pull updates a tasks.md — renderer fires

**WHEN** a developer runs `git pull` or `git merge` and the merge result touches `openspec/changes/<change-id>/tasks.md`
**THEN** the post-merge hook SHALL invoke the renderer with `<change-id>`
**AND** the rendered file SHALL be written to the working tree but SHALL NOT be auto-committed

#### Scenario: Pull touches no tasks.md — renderer skipped

**WHEN** a `git pull` produces a merge whose changed files do not include any `openspec/changes/<change-id>/tasks.md` path
**THEN** the post-merge hook SHALL NOT invoke the renderer
**AND** no coordinator HTTP calls SHALL be made

---

### Requirement: Seeding at /plan-feature Gate 2

The `/plan-feature` skill SHALL POST a coordinator issue for each task in `tasks.md` when the user approves the plan at Gate 2 (Plan Approval).

Each issue SHALL be created with:
- `issue_type = "task"`
- `labels = ["change:<change-id>", "task:<task_key>"]` where `<task_key>` is the task identifier appearing in `tasks.md` (e.g., `1.1`, `T1`, `2.6`)
- `depends_on = [<UUIDs of issues for upstream tasks>]` derived from `**Dependencies**:` annotations in `tasks.md`, resolved in topological order during a single pass (see design D8)

Notes:
- The seeder SHALL NOT pass a `metadata` field; the current `POST /issues/create` API does not accept one (see contracts/README "Related coordinator surface" note). Task identity lives in the `task:<task_key>` label.
- The work-package label (`wp:<id>`) is NOT applied at seed time. `/implement-feature` applies it later via `try_issue_update(labels=...)` once `work-packages.yaml` is generated.

The seeding step SHALL be idempotent: re-invoking it for the same change-id SHALL NOT create duplicate issues. Duplicate detection SHALL key on the `(change:<change-id>, task:<task_key>)` label pair found by querying `try_issue_list(labels=["change:<change-id>"])` and inspecting each returned issue's labels.

#### Scenario: Plan approved — issues created in coordinator

**WHEN** the user selects "Approve — proceed to implementation" at `/plan-feature` Gate 2
**THEN** `/plan-feature` SHALL POST one coordinator issue per task listed in `tasks.md`
**AND** each issue SHALL carry the labels and metadata specified above
**AND** the initial status of each issue SHALL be `pending`

#### Scenario: Re-run after partial seeding

**WHEN** `/plan-feature` Gate 2 is re-approved for a change-id that already has some coordinator issues labeled `change:<change-id>`
**THEN** `/plan-feature` SHALL detect existing issues by inspecting their labels for the `task:<task_key>` pair
**AND** SHALL create issues only for task_keys not already present
**AND** SHALL NOT modify or delete existing issues

#### Scenario: Seeding aborts on dependency cycle

**WHEN** `/plan-feature` invokes the seeder against a `tasks.md` whose `**Dependencies**:` annotations form a cycle (e.g., T1 depends on T2 and T2 depends on T1)
**THEN** the seeder SHALL exit with status 1
**AND** SHALL log a single-line error to stderr identifying the cycle members
**AND** SHALL NOT create any coordinator issues for the change-id in that invocation

#### Scenario: Coordinator unreachable at Gate 2 — seeding is non-blocking

**WHEN** the user approves at Gate 2 and the coordinator API is unreachable
**THEN** `/plan-feature` SHALL log a warning identifying the change-id and the unseeded task_keys
**AND** `/plan-feature` SHALL exit successfully without creating issues
**AND** the next invocation of the renderer (via hook) SHALL display the coordinator-unreachable stale marker until issues can be created

---

### Requirement: Skill Packaging

The renderer SHALL be packaged as a new skill at `skills/coordinator-task-status-renderer/` with `user_invocable: false` (it is invoked by hooks and other skills, not by the user directly).

The skill SHALL include:
- `SKILL.md` with frontmatter conforming to the repo's existing schema
- `scripts/render_tasks_status.py` — the main renderer entry point
- `scripts/seed_tasks_from_md.py` — the seeder invoked by `/plan-feature`

#### Scenario: Skill is auto-installed by skills/install.sh

**WHEN** `skills/install.sh` runs against the repo
**THEN** the new skill SHALL appear under `.claude/skills/coordinator-task-status-renderer/` and `.agents/skills/coordinator-task-status-renderer/`
**AND** the installed `SKILL.md` SHALL contain valid frontmatter with `user_invocable: false`

#### Scenario: Tests live outside the shipped skill directory

**WHEN** `skills/install.sh` runs
**THEN** any tests under `skills/tests/coordinator-task-status-renderer/` SHALL NOT be copied into the runtime skill directories
**AND** tests SHALL be runnable via `skills/.venv/bin/python -m pytest skills/tests/coordinator-task-status-renderer/`

```

### contracts/README.md
```
# Contracts — add-coordinator-task-status-renderer

## Contract sub-types evaluated

| Sub-type | Applicable? | Why |
|---|---|---|
| OpenAPI (HTTP API) | No | No new endpoints are added to the coordinator. The renderer reads via the existing `GET /issues?labels=...` path (already specified in `agent-coordinator` spec). The optional `GET /issues/by-change/<id>` convenience endpoint is deferred to a follow-up (D5). |
| Database schema | No | No migrations required. Uses the existing `work_queue` columns added by migration `017_issue_tracking.sql`: `labels TEXT[]`, `metadata JSONB`, plus core status/depends_on columns. |
| Event payloads | No | No new pg_notify events or LISTEN/NOTIFY channels are introduced. The renderer is pull-driven (HTTP poll on hook fire), not push-driven. |
| Type generation | No | No OpenAPI schemas → no generated models/types needed. Skill scripts work with plain dicts returned by `coordination_bridge.try_issue_list`. |

Because no machine-checkable sub-type applies, this README is the contract artifact. It documents the CLI invocation contracts for the two scripts the skill ships, which are real coordination boundaries (hooks call the renderer; `/plan-feature` calls the seeder) but are not in the OpenAPI/DB/event taxonomy.

---

## CLI Contract: `render_tasks_status.py`

**Purpose.** Read coordinator task state for a given OpenSpec change-id and update the managed block in that change's `tasks.md` from coordinator state.

**Invocation:**

```
python3 skills/coordinator-task-status-renderer/scripts/render_tasks_status.py <change-id> [--repo-root <path>]
```

| Argument | Type | Required | Description |
|---|---|---|---|
| `<change-id>` | positional, string | yes | OpenSpec change identifier (e.g., `add-coordinator-task-status-renderer`). Matches a directory under `openspec/changes/`. |
| `--repo-root <path>` | option, string | no | Absolute path to repo root. Defaults to `git rev-parse --show-toplevel`. |

**Effects:**

1. Reads `<repo-root>/openspec/changes/<change-id>/tasks.md`.
2. Calls coordinator: `coordination_bridge.try_issue_list(labels=["change:<change-id>"])`.
3. For each returned issue, extracts the `task_key` from its `task:<key>` label (the renderer ignores `metadata.task_key` — see D7).
4. Renders a managed block per the format defined below.
5. Writes the rewritten `tasks.md` back to the same path. The renderer SHALL NOT touch the git index; auto-staging is the hook's responsibility.

**Behavior when both the coordinator is unreachable AND the markers are absent:**

The renderer SHALL append the managed-block markers to the end of the file with the stale-marker as the content, in a single write — guaranteeing the markers exist for the next successful invocation to repaint (see D9).

**Managed-block markers:**

```
<!-- GENERATED: begin coordinator:tasks-status -->
...rendered content...
<!-- GENERATED: end coordinator:tasks-status -->
```

Marker name is exactly `coordinator:tasks-status`. The colon is part of the name.

**Rendered-content format (normal case):**

```
- [<x or space>] <task_key>: <title> — <status annotation>
```

Where:
- `<x or space>`: `x` if issue status is `completed`, otherwise space.
- `<task_key>`: extracted from the issue's `task:<key>` label (strip the `task:` prefix). Issues without a `task:<key>` label SHALL be skipped (logged to stderr). Lines SHALL be sorted by `<task_key>` ascending lexicographically using natural-numeric order for dotted keys (e.g., `1.2` before `1.10`, `2.1` before `10.1`).
- `<title>`: the issue title.
- `<status annotation>`: format depends on the coordinator's friendly status:
  - `pending` → `pending`
  - `in_progress` → `in_progress, claimed by <assignee>` (with `<assignee>` from `issue.assignee`; if unset, render `claimed`)
  - `closed` (with `close_reason` matching `completed|done`) → `done by <assignee> <ISO-date>`
  - `closed` (other reasons) → `closed: <close_reason>`
  - `failed` → `failed: <close_reason>`
- If `depends_on` contains UUIDs whose referenced issues are not closed, append ` — blocked on <task_keys>` to non-closed lines (look up each UUID's `task:<key>` label from the same list response — no extra HTTP round-trips required).
- Evidence URIs are NOT surfaced in v1 (the `IssueService` does not currently expose a `result.evidence_uri` field on the GET path). Deferred to a follow-up.

**Rendered-content format (stale fallback):**

```
> Coordinator unreachable at <ISO-8601 timestamp> — status frozen.
```

Single line; replaces any prior managed-block content.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Success. Block rendered (either from coordinator data or as stale-marker). |
| 1 | Internal renderer error (malformed tasks.md, filesystem error). Hooks SHALL log and continue without re-staging. |

The renderer SHALL NOT exit non-zero on coordinator failure — that path triggers the stale-marker write and returns 0.

**Stdout/stderr:**

- stdout: one line per change-id processed, format `rendered <change-id> issues=<N>` or `stale-marker <change-id> reason=<short>`.
- stderr: warnings only (e.g., coordinator timeout, malformed metadata on an issue). Errors that would normally raise are logged here too.

---

## CLI Contract: `seed_tasks_from_md.py`

**Purpose.** Parse a change's `tasks.md` and create coordinator issues for each task. Idempotent on the `(change:<id>, task:<key>)` label pair.

**Invocation:**

```
python3 skills/coordinator-task-status-renderer/scripts/seed_tasks_from_md.py <change-id> [--repo-root <path>] [--dry-run]
```

| Argument | Type | Required | Description |
|---|---|---|---|
| `<change-id>` | positional, string | yes | OpenSpec change identifier. |
| `--repo-root <path>` | option, string | no | Defaults to `git rev-parse --show-toplevel`. |
| `--dry-run` | flag | no | Print planned issue payloads to stdout; make no coordinator calls. |

**Effects:**

1. Parses `<repo-root>/openspec/changes/<change-id>/tasks.md` for `- [ ]` or `- [x]` lines bearing a task key (e.g., `T1`, `1.1`, `2.6`).
2. Parses `**Dependencies**:` annotations beneath each task to build a dependency DAG over task keys.
3. Topologically sorts task keys; aborts with exit 1 if a cycle is detected.
4. Calls coordinator: `coordination_bridge.try_issue_list(labels=["change:<change-id>"])` to discover existing issues. Builds a map `existing_task_keys -> issue_uuid` by reading the `task:<key>` label from each returned issue.
5. For each task key in topological order, if no existing issue carries the `task:<key>` label:
   - POSTs via `coordination_bridge.try_issue_create(...)` with the payload defined below.
   - Records the returned UUID into the `existing_task_keys` map so downstream tasks can reference it in their `depends_on`.

**Issue payload (passed as kwargs to `try_issue_create`):**

```python
try_issue_create(
    title="<task title extracted from tasks.md line>",
    issue_type="task",
    labels=["change:<change-id>", "task:<task_key>"],
    depends_on=[<UUIDs of upstream issues, resolved from earlier POSTs in this run or pre-existing issues>],
)
```

Notes:
- Underlying HTTP path is `POST /issues/create` (see `IssueCreateRequest` in `agent-coordinator/src/coordination_api.py`). This is **not** `/work/submit`.
- The seeder does NOT pass `metadata`. The current `IssueCreateRequest` schema does not accept it; the `task:<key>` label is the durable carrier of task identity (see D7).
- `depends_on` resolution uses single-pass topological seeding (D8). The `POST /issues/update` API does not accept `depends_on`, so we cannot retro-PATCH; this constraint requires us to know all upstream UUIDs at POST time.
- Forward references (a task declares a dependency on a key that does not appear in `tasks.md`) are logged to stderr and dropped from `depends_on` (non-fatal).
- Work-package labels (`wp:<id>`) are NOT applied at seed time. They are applied by `/implement-feature` when work-packages.yaml is consumed (via `try_issue_update(labels=[...])`).

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Success. All tasks either created or already present. Coordinator-unreachable case also exits 0 (per D4). |
| 1 | Malformed `tasks.md` (cannot extract task keys), dependency cycle detected (per D8), filesystem error, or other internal error. |

**Stdout/stderr:**

- stdout: one line per issue created, format `created <task_key> <issue_uuid>`. One line per existing match, `exists <task_key> <issue_uuid>`. One summary line at end: `seeded <change-id> created=<N> existing=<M>`.
- stderr: warnings (e.g., unresolved/forward dependency reference). Coordinator-unreachable logged here with the count of unseeded tasks.

---

## Managed-Block Format (reference)

This is the canonical specification of the markers and content the renderer emits. Repeated here for ease of reference; the authoritative source is the spec at `specs/coordinator-task-status-renderer/spec.md` (requirement "Coordinator-Owned Status Block in tasks.md").

```markdown
<!-- GENERATED: begin coordinator:tasks-status -->
- [x] 1.1: Document renderer CLI invocation contract — done by wp-contracts 2026-05-15 (evidence: ci/run/4821)
- [x] 1.2: Document seeder CLI invocation contract — done by wp-contracts 2026-05-15
- [ ] 2.1: Write test: managed-block insertion when absent — claimed by wp-renderer-skill 2026-05-15
- [ ] 2.2: Write test: managed-block replacement preserves hand-content — pending — blocked on 2.1
<!-- GENERATED: end coordinator:tasks-status -->
```

The renderer SHALL emit valid GFM checkboxes (`- [ ]` or `- [x]`) so that downstream consumers (notably `/cleanup-feature`'s open-task scanner) can read the block with their existing parsers.

---

## Related coordinator surface (not part of this change)

These existing coordinator endpoints/columns are read by this change but defined elsewhere. Listed for traceability:

| Surface | Defined in | Used by |
|---|---|---|
| `POST /issues/list` (with `labels=[...]` filter) | `agent-coordinator/src/coordination_api.py` (`IssueListRequest`) | Renderer, Seeder (idempotency check) |
| `POST /issues/create` | `agent-coordinator/src/coordination_api.py` (`IssueCreateRequest`) | Seeder |
| `POST /issues/update` | `agent-coordinator/src/coordination_api.py` (`IssueUpdateRequest`) | Future: `/implement-feature` wp-label PATCH |
| `work_queue.labels TEXT[]` (with GIN index) | `database/migrations/017_issue_tracking.sql` | Both (carries `change:<id>`, `task:<key>`) |
| `work_queue.depends_on UUID[]` | `database/migrations/001_core_schema.sql` | Both |
| `IssueService.list_issues(labels=...)` post-filter | `agent-coordinator/src/issue_service.py` | Renderer (transitively, via coordination-bridge) |
| Helpers `try_issue_create`, `try_issue_list`, `try_issue_update` | `skills/coordination-bridge/scripts/coordination_bridge.py` | Both |

**Note on `metadata` JSONB:** the `work_queue.metadata` column exists (added by migration 017) but is **not writable through the current `POST /issues/create` HTTP API** — `IssueCreateRequest` has no `metadata` field, and `IssueService.create()` only populates `metadata.body` from `description`. This is why this change carries task identity via labels rather than metadata (see D7). Expanding the API to accept arbitrary metadata is a separate concern.

```

## Output format
Return a single JSON object with a top-level `findings` array.
Each finding MUST have these fields:
  - id: short stable identifier
  - type: one of [correctness, completeness, feasibility, testability, scope, consistency, security, performance]
  - criticality: one of [critical, high, medium, low]
  - description: one-paragraph explanation
  - file_path: artifact path the finding pertains to (relative to repo root)
  - line_range: optional [start, end] line numbers when applicable
  - disposition: one of [fix, accept, escalate, regenerate]
  - suggestion: optional one-paragraph suggested change

Mark a finding `critical` or `high` ONLY if it would cause implementation
to fail, break a downstream consumer, or violate a stated invariant.
Issues that are nice-to-have or stylistic are `medium` or `low`.

If you find no blocking issues, return `{"findings": []}` and explain in
a separate `notes` field at the top level.