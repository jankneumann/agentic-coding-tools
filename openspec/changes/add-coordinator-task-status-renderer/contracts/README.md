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
python3 skills/coordinator-task-status-renderer/scripts/render_tasks_status.py <change-id> [--repo-root <path>] [--timeout-seconds <N>]
```

| Argument | Type | Required | Description |
|---|---|---|---|
| `<change-id>` | positional, string | yes | OpenSpec change identifier (e.g., `add-coordinator-task-status-renderer`). Matches a directory under `openspec/changes/`. |
| `--repo-root <path>` | option, string | no | Absolute path to repo root. Defaults to `git rev-parse --show-toplevel`. |
| `--timeout-seconds <N>` | option, integer | no | Max wall-clock time for the coordinator HTTP call. On timeout the renderer follows the stale-marker fallback path. Default: `5`. |

**Effects:**

1. Reads `<repo-root>/openspec/changes/<change-id>/tasks.md`.
2. Calls coordinator: `coordination_bridge.try_issue_list(labels=["change:<change-id>"], limit=100)`. (NOTE: at v1 the coordinator's `IssueService.list_issues` post-filters by `labels` after PostgREST returns up to `limit` rows. `MAX_PAGE_SIZE=100` is the hard cap. At OpenSpec v1 scale — ~10–30 tasks per active change, low total active-change count — `limit=100` is sufficient. Scaling beyond a single active change at a time requires the server-side label-push follow-up listed in proposal "Out of Scope".)
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
- `<x or space>`: `x` if `issue.status == "completed"`, otherwise space. The coordinator's stored status vocabulary (returned by `Issue.to_dict()`) is exactly `pending | claimed | running | completed | failed | cancelled`. (`closed` is a *friendly* alias used by some clients but never appears on the GET path.)
- `<task_key>`: extracted from the issue's `task:<key>` label (strip the `task:` prefix). Issues without a `task:<key>` label SHALL be skipped (logged to stderr). Lines SHALL be sorted by `<task_key>` ascending using the natural-numeric comparator defined below.
- `<title>`: the issue title.
- `<status annotation>`: format keys directly off `issue.status`:
  - `pending` → `pending`
  - `claimed` → `claimed by <assignee>` (with `<assignee>` from `issue.assignee`; if unset, render `claimed`)
  - `running` → `in_progress, claimed by <assignee>` (or just `in_progress` if `assignee` is unset)
  - `completed` → `done by <assignee> <YYYY-MM-DD>` (date derived from `issue.completed_at` truncated to UTC date; omit `by <assignee>` if `assignee` is unset)
  - `failed` → `failed: <close_reason>` (`close_reason` from `issue.close_reason`; render `failed` if unset)
  - `cancelled` → `cancelled: <close_reason>` (or `cancelled` if unset)
- If `depends_on` contains UUIDs whose referenced issues are not yet `completed`, append ` — blocked on <comma-separated task_keys>` to those lines. Task keys are extracted from the `task:<key>` label of each referenced issue (resolved from the same list response — no extra HTTP round-trips). Comma-separated, natural-numeric-sorted, no trailing comma.
- Evidence URIs are NOT surfaced in v1 (the `IssueService` does not currently expose a `result.evidence_uri` field on the GET path). Deferred to a follow-up.

**Natural-numeric comparator (canonical, must be deterministic across runs):**

Given two task keys `a` and `b`, compare as follows:
1. Tokenize each key on `.` into segments.
2. For each segment, split into a leading-digit run and a trailing-suffix string. The leading digits parse as integer (missing → `-1`); the trailing suffix is compared lexicographically (case-sensitive).
3. Segment comparison: integer part first; if tied, suffix lexicographically.
4. Key comparison: zip-compare segments; shorter key (fewer segments) sorts before longer when all shared segments are equal (so `1.1` < `1.1.1`).
5. Letter-prefixed keys (those whose first character is alphabetic, e.g., `T1`) are bucketed AFTER all-numeric keys, and within the letter bucket compared as `(prefix_string_lex, trailing_digits_as_int, trailing_suffix_lex)`.
6. Stable tie-breaker: if the comparator returns equal, fall back to the issue's UUID lexicographic order (guarantees deterministic output).

Examples (sorted order): `1.1`, `1.2`, `1.10`, `2.4`, `2.4a`, `2.9`, `2.9a`, `T1`, `T10`.

A renderer unit test SHALL exercise these exact keys to lock the comparator down.

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
- [x] 1.1: Document renderer CLI invocation contract — done by wp-contracts 2026-05-15
- [x] 1.2: Document seeder CLI invocation contract — done by wp-contracts 2026-05-15
- [ ] 2.1: Write test: managed-block insertion when absent — claimed by wp-renderer-skill
- [ ] 2.2: Write test: managed-block replacement preserves hand-content — pending — blocked on 2.1
<!-- GENERATED: end coordinator:tasks-status -->
```

The renderer SHALL emit valid GFM checkboxes (`- [ ]` or `- [x]`) so that downstream consumers (notably `/cleanup-feature`'s open-task scanner) can read the block with their existing parsers.

---

## Hook Contract (renderer invocation by git hooks)

The pre-commit and post-merge hooks are part of this change's CLI surface. They are tested as black-box subprocess invocations and therefore have a documented contract:

**Renderer-path resolution.** Both hooks resolve the renderer script path in this order:

1. `$COORDINATOR_TASK_STATUS_RENDERER` if set (test seam and emergency override).
2. `<repo-root>/skills/coordinator-task-status-renderer/scripts/render_tasks_status.py` (the canonical install path).

**Invocation.** Hooks invoke the renderer once per affected change-id with `python3 <resolved-path> <change-id>`. No additional arguments are passed by the hook itself (operators wanting non-default `--timeout-seconds` set it via shell defaults outside the hook).

**Failure behavior.** If the renderer exits non-zero:
- Pre-commit: the hook logs `[pre-commit] renderer failed for <change-id> (exit=<N>); skipping re-stage`, does NOT run `git add` on the file, and allows the commit to proceed.
- Post-merge: the hook logs an equivalent warning and continues.

**Path detection.** Hooks detect affected `tasks.md` paths via:
- Pre-commit: `git diff --cached --name-only -z` filtered through a regex matching `openspec/changes/<id>/tasks.md`.
- Post-merge: `git diff --name-only -z ORIG_HEAD HEAD` (or `MERGE_HEAD HEAD` in the merge-commit case) with the same regex.

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
