# Contracts — phase-scoped-worktree-lifecycle

This directory defines the repository-owned boundaries selected for this change.
The contracts describe persisted data and the local CLI; they do not make the
coordinator, GitHub metadata, or a local worktree a second source of truth.

## Applicability

| Contract type | Applicable? | Artifact / reason |
|---|---:|---|
| JSON Schema | Yes | `schemas/worktree-registry-v2.schema.json` covers strict schema-v2 writes and backward-compatible v1 reads. `schemas/worktree-process-evidence.schema.json` defines non-authoritative local PID/start/host evidence for conservative expired takeover. `schemas/autopilot-run-recovery.schema.json` defines the external lifecycle-recovery envelope used to recreate a disposed continuous checkout. `schemas/pr-delivery-classification.schema.json` records deterministic PR-stage evidence. `schemas/merge-plan-delivery-fields.schema.json` defines the immutable classification snapshot and mutable routing fields added to each durable merge-plan node. |
| CLI contract | Yes | `cli/worktree-lifecycle.yaml` defines locked, owner-checked lease and retention commands, compatibility aliases, defaults, output, and exit behavior. |
| OpenAPI | No | Lease authority remains in the repository registry and must work without coordinator or network access. Coordinator API/UI work only projects this state; it does not introduce an authoritative HTTP mutation surface in this change. |
| Database schema | No | No database is added or changed. Registry state remains in `.git-worktrees/.registry.json`; the durable merge plan remains a file-tier artifact when the coordinator tier is unavailable. |
| Event contract | No | Heartbeat renewal and phase transitions are direct local operations. This change does not add an event bus or a new externally consumed event payload. |
| Generated types | No | Python consumers validate/parse these small contracts directly. Generated models would add another synchronization surface without a cross-language consumer. |

## Contract purposes

### Worktree registry

`schemas/worktree-registry-v2.schema.json` is a read contract with two disjoint
accepted shapes:

- schema v2, selected by `schema_version: 2`, is the only shape new mutations
  write. Retention and activity are independent. `retained` protects against GC;
  only an unexpired `activity_lease` blocks a sync point.
- schema v1, selected by `version: 1`, preserves compatibility with the current
  registry. A v1 `pinned: true` is interpreted as retention, not perpetual
  activity. A fresh legacy `last_heartbeat` may remain transitional activity
  evidence during migration.

The reader must validate or report the source document before rewriting it. A
locked mutation rewrites the complete registry as v2 via atomic replacement.
Expiry only changes activity interpretation; it never authorizes deletion of a
dirty worktree or state not proven durable on the entry's stored remote/ref.

JSON Schema cannot compare timestamps. Producers additionally enforce:

1. `acquired_at <= last_heartbeat < expires_at` for a live lease.
2. `(change_id, agent_id)` is unique across entries.
3. The exact `(activity_lease.owner, lease_id, controller_instance_id)` triple is
   the only identity allowed to renew or release that lease, except explicit
   owner/session recovery outside ordinary workflow commands.
4. Replacement after expiry uses a new lease and controller id; a stale process
   retaining an older identity cannot renew, release, dispose, integrate,
   commit, or push.
5. Every successful renew sets `expires_at` to the renewal time plus the
   requested/default TTL; the default TTL is 1,800 seconds and normal renewal
   cadence is 300 seconds.
6. Dirty, dirty-submodule, or remote-unreachable state enters
   `recovery_required` quarantine and cannot be adopted by an ordinary acquire.
7. Fresh automatic setup publishes entry generation, exact durability target,
   process evidence, and initial lease in one lifecycle transaction. Any
   separately observed unleased or legacy entry receives
   the full adoption assessment rather than immediate acquisition.
8. Takeover refreshes the stored target outside the global lock, then revalidates
   generation/target under lock before evaluating checkout cleanliness,
   submodules, HEAD reachability, and exact-entry process evidence. Unsafe or
   indeterminate state is quarantined instead of acquired.

Fresh v1 heartbeat normalization populates every required v2 lease field:
`owner=legacy:<change-id>:<agent-id-or-parent>`,
`lease_id=legacy-v1:<sha256(change-id|agent-id-or-parent|created-at)>`,
`controller_instance_id=null`, `session_id=null`, `phase=LEGACY`, `reason=legacy-heartbeat-migration`,
`lifecycle_mode=manual`, `acquired_at=min(created_at,last_heartbeat)`, the
original heartbeat, `expires_at=last_heartbeat+3600s`, and `ttl_seconds=3600`.
The legacy heartbeat command performs this mapping only while the source entry
is v1; after canonicalization it requires the explicit synthetic owner and
lease id and follows the normal renew contract.

Process evidence is stored atomically at a digest of the versioned,
length-prefixed `(change_id, agent_id-or-null, lease_id)` identity and validates
against `schemas/worktree-process-evidence.schema.json`. The controller records
the entry identity, lease id and owner, PID, platform process-start token,
host/boot identity, controller-instance id, and timestamps before making a new
automatic lease visible, then refreshes `last_seen_at` with lease renewal. On the same host, an
existing PID with the exact start token is a live old writer; an absent PID or
start-token mismatch is stale evidence, including PID reuse. Missing,
unreadable, cross-host, or unsupported evidence is indeterminate. Live or
indeterminate evidence quarantines an expired checkout; only stale same-host
evidence permits the remaining clean/durable checks. Evidence never grants
ownership. Every evidence operation validates entry, owner, lease, and
controller fields. Clean disposal removes its matching record; quarantine
release preserves it and records the key plus former identity in
`recovery_context` until safe adoption or teardown. A stale orphan record may
be GC'd.

### Autopilot run recovery

`schemas/autopilot-run-recovery.schema.json` validates the minimal envelope at
`.git-worktrees/.autopilot-runs/<run-id>/recovery.json`. The existing committed
feature-branch `loop-state.json` remains canonical workflow state. The envelope
records enough branch, durable-ref, HEAD, canonical-state digest, phase, and
finalization evidence to recreate a removed checkout and verify the restored
loop state before a new controller acquires ownership. It never stores a
reusable controller identity and never grants permission to resume by itself.

### PR delivery classification

`schemas/pr-delivery-classification.schema.json` is the complete classifier
result persisted by discovery and copied into a merge-plan node. `delivery_stage`
is derived primarily from the PR changed-file partition and the governing
OpenSpec state on the base branch. The `OpenSpec-Delivery` PR-body marker and
branch hint are corroborating evidence only. Origin, GitHub author, author
vendor, and delivery stage remain independent fields.

A result is `ambiguous` when required primary diff/base/head evidence is
incomplete or conflicts. A missing optional marker is only a warning; a
conflicting, duplicate, or invalid marker is ambiguous. The schema requires at
least one operator-visible ambiguity reason and separately preserves warnings,
marker status, base/head SHAs, acquisition status, and author-vendor evidence.
Producers additionally enforce the exhaustive truth table from the spec and
that unpartitioned paths cannot yield a non-ambiguous stage.

### Durable merge-plan fields

`schemas/merge-plan-delivery-fields.schema.json` is an extracted node view used
to extend the `add-merge-plan-orchestration` node contract:

- `definition.delivery_classification` is the immutable discovery snapshot.
- `state.latest_delivery_classification` is the refreshed classification at
  the current base/head SHAs.
- `state.delivery_routing` is live state and may be updated after an explicit
  operator override or reclassification.

The routing matrix is schema-enforced: proposal delivery gets planning-only
review, strict OpenSpec validation, and preserves the active change;
implementation and mixed delivery get plan-plus-code review, full validation,
and archival after merge; ambiguous delivery is blocked. An operator override
is permitted only for the latest ambiguous classification and must record actor,
timestamp, rationale, inspected base and head SHAs, ruleset version, algorithm
`pr-delivery-v1+jcs-sha256`, and a SHA-256 digest of the canonical inspected classification. It
changes the effective stage without rewriting the original classification
evidence. Producer checks require
classifier-sourced routing to equal `state.latest_delivery_classification`, and
operator disposition records actor, rationale, selected stage, and timestamp,
with `selected_stage == effective_stage`. Execution honors an override only
while latest classification remains ambiguous and its SHAs, ruleset version,
algorithm, digest, and selected/effective stage match. Any mismatch discards
it; a newly clear result uses classifier routing, otherwise ambiguous routing
remains blocked. The shared digest helper uses RFC 8785 JCS over every
classification field except `classified_at`, after sorting all set-valued arrays
by strict UTF-8 byte order, with no Unicode normalization and a checked-in fixed
hash fixture.
This change implements file-tier persistence; coordinator APIs/UI project those
fields but do not activate the overlapping change's deferred coordinator
system-of-record.

## Compatibility and promotion

The schemas are change-local planning contracts. Implementation must update the
active `add-merge-plan-orchestration` contract so its node `definition` and
`state` use these fields, then promote any contract that remains a durable
cross-change boundary under `openspec/contracts/` before this change is
archived. Tests must validate representative v1/v2 registries, all four delivery
stages, marker disagreement, and every routing branch against these schemas.
