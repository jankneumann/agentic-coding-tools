# Design: add-project-keyed-gate-projection

## Context

Gate state lives in Git, per repository. The coordinator is a remote service
with a Postgres database and no access to any checkout. The approval service
(`src/approval.py`, table `approval_queue`) already stores decisions; its rows
have no project.

## Decisions

### D1. Push a full snapshot per project

The repository-side collector sends the project's complete pending set. The
coordinator replaces the project's row. There is no per-gate write path.
Rebuilding after a delete is the same call as any other refresh, which is why
the rebuilt set equals the earlier one whenever the repository has not
changed. Rejected: coordinator pull (needs repository credentials, cannot see
unpushed state) and per-gate events (a missed event is permanent).

### D2. One row per project, gates in a JSONB object

`gate_projection_snapshots(project PK, collected_at, received_at, payload
JSONB, digest)`. `payload` is `{"gates": [...], "source_errors": [...]}`: an
object, because the Postgres client encodes a dict for a JSONB column and its
handling of a bare list is not something this change should depend on.
Replace is "update the row, insert if none was updated"; the `DatabaseClient`
protocol has no upsert and no RPC is added. Two concurrent first pushes for
one project can collide on the primary key; the second caller retries the
update once.

### D3. Enrolment is coordinator configuration

`GATE_PROJECTION_PROJECTS` lists enrolled projects, following
`REVIEW_ALLOWED_REPOS`. It serves two purposes: it refuses snapshots from
projects nobody enrolled, and it is the list against which a missing snapshot
is detected. Without an enrolment list, a repository that never pushed could
not be reported at all. Rows for projects no longer enrolled are ignored by
the listing and left in place.

### D4. Degraded is computed at read time

An enrolled project's status is `ok` or `degraded`, with a reason:

- `no_snapshot`: no row.
- `stale`: `received_at` is older than `GATE_PROJECTION_STALE_SECONDS`, by the
  coordinator's clock.
- `source_errors`: the collector could not read at least one gate source.

A degraded project's last known gates are still listed, each marked
`project_status: degraded`. Hiding them would be the silent omission the
acceptance outcome forbids.

"The coordinator cannot reach a repository" is read as "the coordinator has no
current snapshot from it". The coordinator never dials a repository, so
staleness is the only signal available.

### D5. A gate's identity is a digest of where it lives

`gate_id` is the first 16 hex digits of SHA-256 over project, source, roadmap
id, item id, change id, gate and dispatch id. It is stable across collections
of an unchanged repository and needs no counter. The listing addresses a gate
by `(project, gate_id)`.

### D6. What counts as pending

- A dispatch attempt in `openspec/roadmaps/*/checkpoint.json` with
  `status: parked` and a non-null `parked.gate`.
- A non-null `pending_gate` in `openspec/changes/*/loop-state.json`, whatever
  the loop's phase. The phase is carried so a reader can see a gate left on a
  finished loop.

A gate record whose latest outcome is `blocked` with no parked attempt is not
listed. It records that a gate refused, not that something is waiting, and
listing it would show history as work. Archived changes
(`openspec/changes/archive/`) are not scanned.

### D7. The approval service is joined at read time, never copied

A snapshot gate may carry `approval_id`. The listing reads
`ApprovalService.list_pending` once and then:

| Gate's `approval_id` | Listed as |
|---|---|
| names a pending request | `decision_route: approval_service`, options `approved`/`denied`, deadline = the request's `expires_at` |
| names a request that is decided or expired | omitted; counted in the project's `decided_awaiting_sync` |
| absent, or names no request | `decision_route: repository`, options `approved`/`rejected`, with `answer_hint` |

Pending approval requests that no snapshot references are listed with
`project: null` and `source: approval_service`, so nothing in the approval
queue is hidden by the projection.

### D8. Decide delegates and refuses what it cannot route

`POST /gates/decide` finds the gate in the project's snapshot. With a pending
approval it calls `ApprovalService.decide_request` and returns its result.
Otherwise it answers `409` with the `answer_hint`. It never writes to the
projection: the decided gate disappears from the listing through D7 and then
from the snapshot at the repository's next push. The owning repository learns
the decision the way it already does, by polling the approval request
(`approval_gate.check_filed`).

`decided_by` follows the existing `/approvals/{id}/decide` route. Binding it
to the authenticated principal belongs to `owner-routed-escalation`.

### D9. The collector does not use a new bridge helper

It calls `CoordinatorHttpClient.request` directly. A `try_*` helper would add
a capability flag, a probe and a generated-bindings entry for one caller.

### D10. Disposition comes from the posture, not from the gate record

The collector reads `TRUST_POSTURE.md` with `load_posture` and attaches the
gate's current disposition, timeout and default action. An absent posture
means every gate blocks, as the parser already rules. An invalid posture is a
`source_errors` entry and the dispositions are sent as `block`.

## Non-goals

- Filing approval requests for gates that today wait at the console.
- Scheduling the collector.
- Notifications, the inbox view, per-principal filtering.
- A project column on `approval_queue`.

## Risks

- **Nothing is decidable today.** See the proposal's "Known limit".
- **Staleness is the only reachability signal.** A repository that pushed an
  hour ago and has since gained a gate looks `ok`. The stale window bounds how
  long, and the listing shows `received_at` per project.
- **One key pushes for every enrolled project.** A holder of the key can
  replace another project's snapshot. It cannot decide anything it could not
  already decide through `/approvals/{id}/decide`.
- **Not deployed here.** The migration and routes are verified by unit tests;
  no container runtime is available where this change is built.
