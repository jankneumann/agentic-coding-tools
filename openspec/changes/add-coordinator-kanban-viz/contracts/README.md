# Contracts — add-coordinator-kanban-viz

## Contract sub-types evaluated

| Sub-type | Applicable? | Why |
|---|---|---|
| OpenAPI (HTTP API) | **Yes** | Three new endpoints on the coordinator (`/sync-points/status`, `/worktrees/active`, `/events/work`) MUST be documented as additions to `openspec/specs/agent-coordinator/openapi.yaml` (or whichever path the existing API spec lives at). The renderer change established that existing `GET /issues?...` and `POST /work/submit` are pre-existing and NOT redocumented here. |
| Database schema | No | No migrations. The two new endpoints read existing columns. The `LISTEN/NOTIFY` channels (`work_queue_change`, `audit_log_append`) are runtime artifacts of triggers added to existing transaction paths in service code, not schema changes. |
| Event payloads | **Yes** | The SSE `transition` and `audit` event payload schemas MUST be documented as machine-checkable JSON schemas. The frontend's TypeScript types are generated from these schemas. |
| Type generation | **Yes** | Frontend TypeScript types for issue/worktree/audit/sync-point shapes are generated from coordinator Pydantic models (existing `pydantic-to-typescript` pattern, or a small custom transform). Generation is wired into the frontend build so schema drift is a build failure. |
| File-format JSON Schema | **Yes** | The `saved-views` JSON schema is checked-in and validated at write time AND at git pre-commit (via the existing JSON-schema lint step in codeviz Phase 0 if present, otherwise a small standalone check). |

The renderer change (`add-coordinator-task-status-renderer`) declared no machine-checkable sub-types because all of its boundaries were CLI invocations. This change adds real network surfaces (HTTP + SSE) and a persisted file format, so the contract surface is broader.

---

## HTTP Endpoint Additions

### `GET /sync-points/status`

**Purpose.** Return the blocker state of the three sync-point skills for the sync-point gate banner.

**Request:**

```
GET /sync-points/status
Authorization: Bearer <coordinator-api-key>
```

No query parameters in v1. (A future `?skills=<csv>` filter is reserved.)

**Response (200 OK):**

```json
[
  {
    "skill": "cleanup-feature",
    "blocked": true,
    "blockers": [
      {"agent_id": "wp-backend", "last_heartbeat_iso": "2026-05-15T10:40:13Z"}
    ],
    "suggested_actions": ["wait", "kick:wp-backend"]
  },
  {
    "skill": "merge-pull-requests",
    "blocked": false,
    "blockers": [],
    "suggested_actions": []
  },
  {
    "skill": "update-specs",
    "blocked": false,
    "blockers": [],
    "suggested_actions": []
  }
]
```

**Ordering.** Response array is alphabetical by `skill`. Deterministic for caching and snapshot tests.

**Reversibility.** `read`. Auto-allowed.

**Implementation note.** Server handler imports `shared.check_no_active_agents()` and iterates the three sync-point skills. The function MUST NOT be reimplemented.

---

### `GET /worktrees/active`

**Purpose.** Return a coordinator-mediated projection of `.git-worktrees/.registry.json`, omitting stale entries (heartbeat older than 1 hour) and surfacing pinned status.

**Request:**

```
GET /worktrees/active
Authorization: Bearer <coordinator-api-key>
```

**Response (200 OK):**

```json
[
  {
    "agent_id": "wp-backend",
    "branch": "openspec/add-coordinator-kanban-viz--wp-backend",
    "worktree_path": ".git-worktrees/add-coordinator-kanban-viz/wp-backend",
    "last_heartbeat_iso": "2026-05-15T10:40:13Z",
    "pinned": false,
    "owner_session": "session-..."
  }
]
```

**Reversibility.** `read`. Auto-allowed.

**Stale threshold.** 1 hour, matching `worktree.py gc` default. Pinned worktrees are returned regardless of heartbeat age (with `pinned: true`) so the UI can label them.

---

### `GET /events/work` (Server-Sent Events)

**Purpose.** Live stream of work-queue transitions and audit events scoped to one or more change-ids.

**Request:**

```
GET /events/work?change_ids=<csv>
Accept: text/event-stream
Authorization: Bearer <coordinator-api-key>
```

**Connection establishment response:**

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

event: snapshot
data: {"work_queue": [...], "active_agents": [...], "subscribed_change_ids": [...]}

(then emits live events as they occur)

event: transition
data: {"work_queue_id": "...", "from": "claimed", "to": "running",
       "agent_id": "wp-backend", "ts": "2026-05-15T10:42:13Z"}

event: audit
data: {"audit_id": "...", "agent_id": "wp-backend", "operation": "edit_file",
       "args_summary": "src/foo.py +42 -8", "ts": "2026-05-15T10:42:14Z"}
```

**Subscription filter.** `change_ids` is a comma-separated list. The server filters server-side using the existing label/permission filter applied by `IssueService.list_issues`. Empty `change_ids` is rejected (HTTP 400) — clients MUST scope their subscription.

**Reconnection.** Standard SSE auto-reconnect. The server emits a fresh `event: snapshot` on each connection (re)establishment.

**Backpressure.** Server caps emission at 100 events/sec/connection; excess is coalesced to a single `event: snapshot`.

**Reversibility.** `read`. Auto-allowed. Audit emission optional (per codeviz reversibility taxonomy for read events).

**Failure mode.** If the underlying Postgres `LISTEN` connection drops, the server closes the SSE stream with a final `event: error data: {"reason": "listen_dropped"}`. The client reconnects and receives a fresh snapshot.

---

## SSE Event Payload Schemas

Machine-checkable JSON schemas under `contracts/schemas/events/`:

### `transition` event payload

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kanban-viz.local/schemas/events/transition.json",
  "type": "object",
  "required": ["work_queue_id", "from", "to", "ts"],
  "properties": {
    "work_queue_id": {"type": "string", "format": "uuid"},
    "from":  {"type": "string", "enum": ["pending", "claimed", "running", "completed", "failed", "cancelled"]},
    "to":    {"type": "string", "enum": ["pending", "claimed", "running", "completed", "failed", "cancelled"]},
    "agent_id": {"type": ["string", "null"]},
    "ts": {"type": "string", "format": "date-time"}
  }
}
```

### `audit` event payload

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kanban-viz.local/schemas/events/audit.json",
  "type": "object",
  "required": ["audit_id", "agent_id", "operation", "ts"],
  "properties": {
    "audit_id": {"type": "string", "format": "uuid"},
    "agent_id": {"type": "string"},
    "operation": {"type": "string"},
    "args_summary": {"type": "string"},
    "ts": {"type": "string", "format": "date-time"}
  }
}
```

### `snapshot` event payload

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kanban-viz.local/schemas/events/snapshot.json",
  "type": "object",
  "required": ["work_queue", "active_agents", "subscribed_change_ids"],
  "properties": {
    "work_queue": {"type": "array", "items": {"$ref": "issue.json"}},
    "active_agents": {"type": "array", "items": {"$ref": "agent.json"}},
    "subscribed_change_ids": {"type": "array", "items": {"type": "string"}}
  }
}
```

`issue.json` and `agent.json` are reused from the existing coordinator OpenAPI types — they are NOT redefined here.

---

## Saved-View JSON File Format

Path: `docs/kanban-viz/saved-views/<slug>.json`

Schema (`contracts/schemas/saved-view.json`):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kanban-viz.local/schemas/saved-view.json",
  "type": "object",
  "required": ["schema_version", "generated_at", "git_sha", "generator", "view"],
  "properties": {
    "schema_version": {"type": "integer", "const": 1},
    "generated_at": {"type": "string", "format": "date-time"},
    "git_sha": {"type": "string", "pattern": "^[0-9a-f]{7,40}$"},
    "generator": {"type": "string"},
    "view": {
      "type": "object",
      "required": ["name", "filters"],
      "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 80},
        "columns": {
          "type": "object",
          "properties": {
            "Backlog": {"type": "object"},
            "In Flight": {"type": "object"},
            "Done": {"type": "object"}
          }
        },
        "filters": {
          "type": "object",
          "properties": {
            "change_ids": {"type": "array", "items": {"type": "string"}},
            "vendors": {"type": "array", "items": {"type": "string", "enum": ["claude", "codex", "gemini", "chatgpt-pro"]}}
          }
        },
        "grouping": {"type": "string", "enum": ["none", "vendor", "change_id"]},
        "sort": {
          "type": "object",
          "properties": {
            "key": {"type": "string"},
            "dir": {"type": "string", "enum": ["asc", "desc"]}
          }
        }
      }
    }
  }
}
```

The header fields (`schema_version`, `generated_at`, `git_sha`, `generator`) match the codeviz mandatory artifact header. The `generator` field SHALL be `kanban-viz@<version>`.

---

## Audit-Event JSON File Format

Path: `docs/kanban-viz/audit/<YYYY-MM-DD>/<run-id>.json`

One file per UI-initiated write action. Event-class artifact per the codeviz storage tier policy.

Schema (`contracts/schemas/audit-event.json`):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://kanban-viz.local/schemas/audit-event.json",
  "type": "object",
  "required": ["schema_version", "generated_at", "git_sha", "generator",
               "run_id", "event_kind", "action", "class", "outcome"],
  "properties": {
    "schema_version": {"type": "integer", "const": 1},
    "generated_at": {"type": "string", "format": "date-time"},
    "git_sha": {"type": "string", "pattern": "^[0-9a-f]{7,40}$"},
    "generator": {"type": "string"},
    "run_id": {"type": "string"},
    "event_kind": {"type": "string", "const": "kanban-viz.ui-action"},
    "action": {
      "type": "string",
      "enum": ["save-view", "drag-to-ready", "force-release-lock", "kick-agent"]
    },
    "class": {
      "type": "string",
      "enum": ["read", "reversible-write", "destructive-write"]
    },
    "outcome": {
      "type": "string",
      "enum": ["confirmed", "declined", "auto-allowed", "failed"]
    },
    "args": {"type": "object"},
    "operator": {"type": "string"},
    "previous_git_sha_of_target": {"type": ["string", "null"]}
  }
}
```

The header fields plus `run_id` and `event_kind` mirror the codeviz event-artifact convention exactly. `event_kind` is the constant `kanban-viz.ui-action` so consumers can scope queries to this artifact family.

---

## Frontend ↔ Coordinator Type Generation

TypeScript types under `apps/kanban-viz/src/generated/coordinator-types.ts` are generated at build time from coordinator Pydantic models. The build SHALL fail if generated types are stale relative to the source models.

Toolchain: `pydantic-to-typescript` (or equivalent). Source: `agent-coordinator/src/{models,schemas}/*.py`. Generated output is git-committed so reviewers see schema changes in PR diffs.

The generated file SHALL include exactly the model surface the frontend uses (issue, agent, audit-row, sync-point-status, worktree). It SHALL NOT include unused models — the generator is configured with an allowlist.

---

## Reservation: FalkorDB schema additions (NOT implemented in this change)

This change does NOT write to FalkorDB. It does declare the work-state node and edge labels reserved for codeviz Phase 0 ingestion to consume:

| Label / Edge | Source row | Codeviz Phase 0 ingestion ownership |
|---|---|---|
| `WorkPackage` (node) | `work_queue` | codeviz |
| `Agent` (node) | `agent_profiles` | codeviz |
| `Vendor` (node) | enum {claude, codex, gemini, chatgpt-pro} | codeviz |
| `Worktree` (node) | `.git-worktrees/.registry.json` | codeviz |
| `Lock` (node) | `file_locks` | codeviz |
| `SyncPoint` (node) | enum {cleanup-feature, merge-pull-requests, update-specs} | codeviz |
| `AuditEvent` (node) | `audit_log` | codeviz |
| `CLAIMED_BY` (edge) | WorkPackage → Agent | codeviz |
| `BLOCKED_ON` (edge) | WorkPackage → WorkPackage | codeviz |
| `LOCKS_FILE` (edge) | Agent → File (codeviz) | codeviz |
| `WORKING_IN` (edge) | Agent → Worktree | codeviz |
| `RAN_BY` (edge) | AuditEvent → Agent | codeviz |
| `BLOCKS_SYNCPOINT` (edge) | Agent → SyncPoint | codeviz |
| `IMPLEMENTS_TASK` (edge) | WorkPackage → Symbol (codeviz) | codeviz |

This reservation is duplicated in `docs/kanban-viz/falkordb-reservation.md` as a linkage artifact so codeviz consumers can find it without traversing OpenSpec changes.

---

## Related coordinator surface (not part of this change)

| Surface | Defined in | Used by |
|---|---|---|
| `GET /issues?labels=<csv>` | `openspec/specs/agent-coordinator/` | Initial board fetch + polling fallback |
| `GET /audit/recent?...` | `openspec/specs/agent-coordinator/` | Polling fallback for swimlanes |
| `POST /agents/<id>/kick` | `openspec/specs/agent-coordinator/` | Sync-point banner kick action |
| `PATCH /issues/<id>/labels` | `openspec/specs/agent-coordinator/` | Drag-to-Ready action |
| `DELETE /locks/<file_path>` | `openspec/specs/agent-coordinator/` | Force-release-lock action |
| `shared.check_no_active_agents()` | `skills/shared/check_no_active_agents.py` | `/sync-points/status` endpoint |
| `coordination_bridge.try_issue_list()` | `skills/coordination-bridge/scripts/coordination_bridge.py` | Compatible read path used by the renderer (this change reuses the underlying `GET /issues?...`) |
| `add-coordinator-task-status-renderer` data contract | `openspec/changes/add-coordinator-task-status-renderer/contracts/README.md` | Issue shape (`metadata.task_key`, `metadata.change_id`, status enum) consumed by frontend types — same contract |
| Mandatory artifact header | `docs/codeviz/artifact-header.md` (codeviz Phase 0) | Saved-view + audit-event files |
| Operation reversibility taxonomy | `openspec/roadmaps/codeviz/proposal.md` lines 69–82 | UI action gating |
| Codeviz storage-tier policy | `openspec/roadmaps/codeviz/proposal.md` lines 49–56 | Saved-view (git) and audit-event (event-artifact) placement |
