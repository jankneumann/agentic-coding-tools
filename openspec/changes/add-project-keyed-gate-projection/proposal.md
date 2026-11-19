# Add project-keyed gate projection

> Parent roadmap: `sandboxed-flow`
> Change ID: `add-project-keyed-gate-projection`
> Effort: L
> Priority: 2

## Summary

Project every pending gate from each enrolled repository (checkpoint.json, loop-state.json, TRUST_POSTURE.md and the approval service) into the coordinator, keyed by project, and expose one listing of everything awaiting the operator. The projection is rebuilt from the repositories and never written back; decisions go through the existing approval gate service.

## Why

A gate that waits for the operator is recorded in one of three places inside
one repository: a parked dispatch attempt in a roadmap's `checkpoint.json`, a
`pending_gate` in a change's `loop-state.json`, or a pending row in the
coordinator's `approval_queue`, which has no project column. Nothing lists
them together. The operator finds out what is waiting by opening each
repository and running `/supervise`. This repository alone holds eight such
gates today (four parked attempts, four loop-state gates), and the supervisor
mirror's `pending_gates` lists none of them.

The roadmap's decision inbox (`add-decision-inbox-view-to-kanban-viz`) and the
approval notifications both need one request that answers "what is waiting for
me, in which project, until when".

## What Changes

- **Coordinator, storage.** Migration `047_gate_projection.sql` adds
  `gate_projection_snapshots`: one row per project holding that project's
  whole pending set. No decision is stored in it.
- **Coordinator, service and routes.** `src/gate_projection.py` and
  `src/gate_projection_routes.py` add four routes:
  - `POST /gates/projection`: replace one project's snapshot.
  - `DELETE /gates/projection`: delete one project's snapshot.
  - `GET /gates/pending`: every pending gate of every enrolled project, and
    the status of each enrolled project.
  - `POST /gates/decide`: decide a listed gate. The route calls
    `ApprovalService.decide_request` and stores nothing itself.
- **Coordinator, enrolment.** `GATE_PROJECTION_PROJECTS` (comma-separated
  `owner/repo`) names the enrolled projects. A snapshot for any other project
  is refused. `GATE_PROJECTION_STALE_SECONDS` (default 86400) sets the age
  after which a snapshot is reported stale. With the variable unset no project
  is enrolled and the listing is empty, so existing deployments do not change.
- **Repository side.** `skills/supervise/scripts/gate_projection.py` reads a
  checkout's gate records and trust posture and prints or pushes the snapshot.
  It writes nothing in the repository.
- **Contract.** `openspec/contracts/agent-coordinator/openapi/gates.yaml`.

## Known limit: which gates can be decided from the listing

The item says decisions go through the existing approval service and no new
decision store is added. A gate can therefore be decided from the listing only
when it has a pending approval request. A gate record carries that link as
`approval_id`.

In this repository today no gate record carries an `approval_id`, and every
gate that waits has the disposition `block`, which is answered at the console
with `cycle_state.py gate-answer`. So with today's data **no gate is decidable
from the listing**: each one is listed with `decision_route: repository` and
the command that answers it. The decide route is built and tested against
approval-backed gates, which the approval-gate skill files for
`notify_with_timeout` gates and for `block` gates filed remotely.

Making every gate decidable from the inbox needs each waiting gate to file an
approval request when it parks. That changes the gate router and autopilot
runner and is not in this change. It is a follow-up the inbox item depends on.

## Assumptions

- The operator sets `GATE_PROJECTION_PROJECTS` on the coordinator and runs the
  collector in each enrolled repository (by hand, from `/supervise cycle`, or
  on a schedule). Nothing in this change schedules it.
- A project is named `owner/repo`, as the review queue already names
  repositories.
- One coordinator API key may push for any enrolled project. Per-project
  credentials are not added.
- The coordinator's clock decides staleness; the collector's `collected_at`
  is shown but not trusted for that.

## Approaches Considered

### A. Each repository pushes a full snapshot (recommended)

A deterministic collector in the repository builds the complete pending set
and sends it; the coordinator replaces that project's row.

- Pros: works with a remote coordinator that cannot read a checkout; rebuild
  is the normal path, so it cannot diverge from an incremental path; one row
  per project and no merge logic.
- Cons: the listing is as fresh as the last push; a repository that stops
  pushing is seen only through the stale window.
- Effort: M

### B. The coordinator pulls from each repository

The coordinator clones or reads each repository through the GitHub API.

- Pros: no step to run in the repository; freshness is the coordinator's.
- Cons: `loop-state.json` and parked attempts on unpushed branches are
  invisible; the coordinator would need repository read credentials for every
  project, which is the access this roadmap is trying to narrow.
- Effort: L

### C. Per-gate upsert and delete events

Each skill that parks or resolves a gate reports that one change.

- Pros: near-real-time.
- Cons: a missed event leaves a gate listed forever or never listed; "delete
  and rebuild yields the same set" then needs approach A anyway; touches every
  gate-writing skill.
- Effort: L

A is chosen. C can be added later as a freshness hint on top of A without
changing the store.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by |
|---|---|---|---|
| Compatibility | Behaviour with `GATE_PROJECTION_PROJECTS` unset | Listing returns no gates and no projects; existing routes unchanged | coordinator unit tests |
| Resilience | An unreadable gate file in a checkout | Reported in `source_errors`; other gates still collected; project shown degraded | collector tests |
| Resilience | Snapshot size | At most 500 gates per project; larger is refused with 422 | service tests |
| Operability | Listing cost | One snapshot-table read plus at most two approval-queue reads, independent of the number of gates | service tests (call counts) |

## Impact

- Affected specs: `agent-coordinator` (three requirements added), `supervise`
  (one requirement added).
- Affected code: `agent-coordinator/src/` (two new modules, `config.py`,
  `coordination_api.py` install line), one migration, one new skills script.
- Not affected: `approval_queue`, `ApprovalService`, gate records, the gate
  router, `TRUST_POSTURE.md`.

## Dependencies

- None

## Acceptance Outcomes

- One coordinator request returns every pending gate across at least two enrolled repositories, each with project, gate type, subject, options and deadline.
- Deleting the projection and rebuilding it from the repositories yields the same pending set.
- A decision made through the listing reaches the owning repository's gate record through the existing approval service, with no new decision store.
- A repository the coordinator cannot reach is reported as degraded, not silently omitted.

## Rationale

Gate state is scattered across per-repository files with no cross-repository view; one inbox needs one listing while Git remains the authoritative record per repository.
