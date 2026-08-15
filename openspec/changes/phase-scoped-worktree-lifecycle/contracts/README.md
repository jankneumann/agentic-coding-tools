# Contracts — phase-scoped-worktree-lifecycle

This directory defines the repository-owned boundaries selected for this change.
The contracts describe persisted data and the local CLI; they do not make the
coordinator, GitHub metadata, or a local worktree a second source of truth.

## Applicability

| Contract type | Applicable? | Artifact / reason |
|---|---:|---|
| JSON Schema | Yes | `schemas/worktree-registry-v2.schema.json` covers strict schema-v2 writes and backward-compatible v1 reads. `schemas/pr-delivery-classification.schema.json` records deterministic PR-stage evidence. `schemas/merge-plan-delivery-fields.schema.json` defines the immutable classification snapshot and mutable routing fields added to each durable merge-plan node. |
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
dirty worktree or an unmerged branch.

JSON Schema cannot compare timestamps. Producers additionally enforce:

1. `acquired_at <= last_heartbeat < expires_at` for a live lease.
2. `(change_id, agent_id)` is unique across entries.
3. `activity_lease.owner` is the only identity allowed to renew or release that
   lease, except explicit operator recovery outside ordinary workflow commands.
4. Every successful renew sets `expires_at` to the renewal time plus the
   requested/default TTL; the default TTL is 1,800 seconds and normal renewal
   cadence is 300 seconds.

### PR delivery classification

`schemas/pr-delivery-classification.schema.json` is the complete classifier
result persisted by discovery and copied into a merge-plan node. `delivery_stage`
is derived primarily from the PR changed-file partition and the governing
OpenSpec state on the base branch. The `OpenSpec-Delivery` PR-body marker and
branch hint are corroborating evidence only. Origin, GitHub author, author
vendor, and delivery stage remain independent fields.

A result is `ambiguous` when evidence is incomplete or conflicts. The schema
requires at least one operator-visible ambiguity reason. Producers additionally
enforce that a contradictory body marker, an unpartitioned implementation-like
file, or OpenSpec-only changes inconsistent with base task state cannot yield a
non-ambiguous stage.

### Durable merge-plan fields

`schemas/merge-plan-delivery-fields.schema.json` is an extracted node view used
to extend the `add-merge-plan-orchestration` node contract:

- `definition.delivery_classification` is the immutable analysis snapshot.
- `state.delivery_routing` is live state and may be updated after an explicit
  operator override or base-branch revalidation.

The routing matrix is schema-enforced: proposal delivery gets planning-only
review, strict OpenSpec validation, and preserves the active change;
implementation and mixed delivery get plan-plus-code review, full validation,
and archival after merge; ambiguous delivery is blocked. An operator override
must record actor, timestamp, and rationale and changes the effective stage
without rewriting the original classification evidence.

## Compatibility and promotion

The schemas are change-local planning contracts. Implementation must update the
active `add-merge-plan-orchestration` contract so its node `definition` and
`state` use these fields, then promote any contract that remains a durable
cross-change boundary under `openspec/contracts/` before this change is
archived. Tests must validate representative v1/v2 registries, all four delivery
stages, marker disagreement, and every routing branch against these schemas.
