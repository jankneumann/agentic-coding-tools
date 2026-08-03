# Contracts — integrate-main-context-convergence

## Primary contract

`context-convergence-record.schema.json` — the tracked record the main-synchronization
sync point commits for each convergence.

This change introduces no HTTP surface, so the record schema occupies the primary
contract slot, following the convention ri-08, ri-09, and ri-10 used for the same
reason. See `openspec/contracts/README.md` for the promotion rule: this file must be
copied to `openspec/contracts/project-context-refresh/schemas/` **before** the change
is archived, and kept byte-identical with the installed copy under
`skills/project-context-refresh/install_assets/openspec/schemas/`.

## Why a tracked record exists at all

ri-07 writes the durable refresh manifest to `.git-context/context-refresh-manifest.json`
(`orchestrator.py:70`), which is gitignored (`.gitignore:277`) so that a repeat refresh
at the same revision produces no repository diff, and which is per-worktree and freely
cleanable. That file therefore cannot be the thing that lands on `main`.

The convergence record is the git-native form of the same claim: it pins the manifest
by path and `sha256`, names the durable operation identity, and records the three
revisions the handoff must report. See design D9.

| Field group | Purpose |
|---|---|
| `operation_id`, `merged_revision` | The durable identity (D4). A retry that finds this record for the same merged revision does nothing. |
| `refresh_revision`, `convergence_commit` | The revision the producers actually read, and the commit this record landed in. |
| `manifest_path`, `manifest_sha256` | Pins the untracked manifest by content. |
| `refresh_status`, `producers[]` | Per-producer outcome joined with its canonical owner, since `ProducerResult` carries no owner field. |
| `semantic_index` | The deferred/enqueued reference for the final pushed revision (D7). |
| `merged_pull_requests[]` | Which merges this main state came from. |

## Sub-types evaluated

| Sub-type | Applicable | Why |
|---|---|---|
| OpenAPI | no | The convergence step is a skill sequence plus a CLI driver. It introduces no endpoint and does not extend the coordinator's HTTP surface. |
| Database | no | The durable operation store is ri-06's, unchanged. This change adds no table, column, or migration. |
| Events | no | The semantic-index enqueue reuses the existing coordinator/`index_repo` seam; no new event type is defined. |
| Type generation | no | The record is written and read by the same Python driver and by humans reading a JSONL log; there is no language boundary to cross. |

## Contracts consumed, not defined here

- `context-refresh-types.schema.json` — `GitRevision` and `Remediation` are referenced
  by `$ref` rather than restated.
- `context-refresh-operation.schema.json` — the ri-06 operation record. Unchanged by
  this change; the convergence record points at it by `operation_id`.
- `context-refresh-manifest.schema.json` — unchanged. The convergence record pins the
  manifest rather than embedding or replacing it.
- `context-drift-gate.schema.json` — ri-10's gate report. Consumed read-only by the
  dry-run path (D12); its shape is untouched.

## Storage

Records are appended one JSON object per line to
`docs/merge-logs/context-convergence.jsonl`, matching the existing
`docs/merge-logs/metrics.jsonl` convention (`merge-pull-requests/SKILL.md:68`). Each
line validates independently against this schema.
