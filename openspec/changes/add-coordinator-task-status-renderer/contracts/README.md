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
3. Renders a managed block per the format defined below.
4. Writes the rewritten `tasks.md` back to the same path.

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
- `<task_key>`: from `metadata.task_key`. Lines SHALL be sorted by `task_key` ascending lexicographically.
- `<title>`: the issue title.
- `<status annotation>`: format depends on status:
  - `pending` → `pending`
  - `claimed` → `claimed by <assignee>` (with `<assignee>` from `issue.assignee` or `claimed_by`)
  - `running` → `in_progress, claimed by <assignee>`
  - `completed` → `done by <assignee> <ISO-date>` plus `(evidence: <result.evidence_uri>)` if present
  - `failed` → `failed: <error_message>`
  - `cancelled` → `cancelled`
- If `depends_on` contains UUIDs that are not in `completed` status, append ` — blocked on <task_keys>` to non-completed lines.

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

**Purpose.** Parse a change's `tasks.md` and create coordinator issues for each task. Idempotent on `(change_id, task_key)`.

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
2. Calls coordinator: `coordination_bridge.try_issue_list(labels=["change:<change-id>"])` to discover existing issues.
3. For each task key in `tasks.md` not already present in the coordinator (matched by `metadata.task_key`):
   - POSTs `/work/submit` with the issue payload defined below.

**Issue payload:**

```json
{
  "task_type": "issue",
  "issue_type": "task",
  "title": "<task title extracted from tasks.md line>",
  "labels": ["change:<change-id>"],
  "metadata": {
    "change_id": "<change-id>",
    "task_key": "<key from tasks.md>",
    "tasks_md_anchor": <line number, optional best-effort>
  },
  "depends_on": [<UUIDs of issues for upstream task keys, if discoverable>]
}
```

Notes:
- `depends_on` resolution: if a task line declares `**Dependencies**: 1.4, 2.5`, the seeder SHALL look up issues with `metadata.task_key in ["1.4", "2.5"]` and use their UUIDs. If a referenced task is not yet seeded (because seeding runs top-to-bottom), the seeder MAY do two passes: first POST all issues with empty `depends_on`, then PATCH each with the resolved UUIDs.
- Work-package labels (`wp:<id>`) are NOT applied at seed time. They are applied by `/implement-feature` when work-packages.yaml is consumed.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Success. All tasks either created or already present. Coordinator-unreachable case also exits 0 (per D4). |
| 1 | Malformed `tasks.md` (cannot extract task keys), filesystem error, or other internal error. |

**Stdout/stderr:**

- stdout: one line per issue created, format `created <task_key> <issue_uuid>`. One line per existing match, `exists <task_key> <issue_uuid>`. One summary line at end: `seeded <change-id> created=<N> existing=<M>`.
- stderr: warnings (e.g., unresolved dependency reference). Coordinator-unreachable logged here with the count of unseeded tasks.

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
| `GET /issues?labels=<csv>` | `openspec/specs/agent-coordinator/` | Renderer |
| `POST /work/submit` | `openspec/specs/agent-coordinator/` | Seeder |
| `work_queue.labels TEXT[]` | `database/migrations/017_issue_tracking.sql` | Both |
| `work_queue.metadata JSONB` | `database/migrations/017_issue_tracking.sql` | Both |
| `work_queue.depends_on UUID[]` | `database/migrations/001_core_schema.sql` | Both |
| `IssueService.list_issues(labels=...)` post-filter | `agent-coordinator/src/issue_service.py` | Renderer (transitively, via coordination-bridge) |
