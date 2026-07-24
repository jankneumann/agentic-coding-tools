# Project Context Refresh Records

`skills/project-context-runtime` is a non-user-invocable shared library that
gives every project-context refresh caller one durable identity, a truthful
producer-result model, and a byte-deterministic manifest. It is the shared
persistence and schema boundary consumed by the later architecture-refresh,
refresh-orchestration, branch-checkpoint, and main-convergence changes.

This document is the consumer contract. Roadmap item: `ri-06`
(`add-durable-context-refresh-records`).

## Operation lifecycle

An operation is one refresh attempt-set for a repository at an exact revision.

```
pending ──begin_attempt──▶ running ──finalize──▶ succeeded   (terminal)
                             │                └▶ degraded
                             │                └▶ failed
   failed ──begin_attempt──▶ running                │
 degraded ──begin_attempt──▶ running ◀──────────────┘
```

- `create_or_load(repository_id, source_revision)` returns the single record for
  that identity, creating a `pending` one if none exists. It is idempotent:
  duplicate callers receive the same `operation_id` and one record.
- `begin_attempt(operation_id)` moves `pending | failed | degraded` to `running`
  and increments `attempt`. Calling it again while already `running` is a no-op
  (no attempt bump, no write).
- `record_producer_result` / `record_semantic_index` mutate a `running`
  operation under the per-operation lock.
- `finalize(operation_id, outcome, error=…)` sets a terminal state. `succeeded`
  is terminal and cannot be reopened; `failed` requires a sanitized `error`.
- `record_manifest(operation_id, path=…, sha256=…)` records where the
  deterministic manifest was written; it does not change lifecycle state.

## Identity

```
operation_id = "pcr-" + sha256("context-refresh-v1\0" + repository_id
                                + "\0" + source_revision).hexdigest()[:24]
```

The full `(repository_id, source_revision)` tuple is stored and re-verified on
every load. A record whose stored identity no longer hashes to its directory —
or whose `operation_id` does not match its location — raises
`IdentityMismatchError`. Callers must supply a **canonical** repository id; a
different id is a different identity by design.

## Storage boundary

Mutable records live below the resolved **Git common directory**, not the
worktree:

```
<git-common-dir>/project-context/refresh-operations/<operation-id>/
├── operation.json   # mutable ledger — NEVER committed
└── operation.lock   # advisory flock target
```

Because the common directory is shared by all linked worktrees of one clone,
every worktree and later process sees the same operation. Durability is
**clone-local**: another machine cannot query this ledger unless a higher-level
service mirrors it. Records are small; cleanup is a manual, repository-scoped
operation (automatic GC is deferred).

Each mutation: acquire the lock → reload and validate → apply one legal
transition → bump `record_revision` → atomic replace (`temp + fsync + os.replace
+ parent fsync`). Readers never accept a partial or unknown-version document.

## Manifest fields

The committable manifest is a **projection** of a terminal operation containing
only stable fields, serialized as UTF-8 JSON with sorted keys, two-space
indent, and one trailing newline — so the same logical projection is
byte-identical across runs and a rerun replaces nothing.

Included: `schema_version`, `operation_id`, `repository_id`, `source_revision`,
`operation_created_at`, `refresh_status`, per-producer results, aggregated
`repository_artifacts`, aggregated `validations`, the `semantic_index`
reference, and `degraded_fallbacks`.

Excluded: `updated_at`, `attempt`, `record_revision`, lock state, temporary or
absolute paths, and raw exception output.

Sort keys: producers by `producer_id`; artifacts by `(path, change)`;
validations by `(validation_id, status, summary)`; fallbacks by `producer_id`.

## Producer results and truthful status

Every configured producer records exactly one status — `fresh`, `degraded`,
`failed`, or `not-configured` — and is never omitted or misrepresented as
fresh. Non-fresh results require at least one actionable `remediation`;
`degraded` and `not-configured` also require the `fallback` actually used;
`failed` requires a sanitized `error`. Producer ids are unique within an
operation. Artifacts use safe repository-relative POSIX paths and SHA-256
digests (a `deleted` artifact carries a null digest).

## Semantic index is external state

The `semantic_index` reference is an **opaque** durable operation plus registry
reference — never a repository artifact. Any status other than `succeeded`
requires an explicit `fallback`, and a `succeeded` index must have
`indexed_revision == requested_revision`; a mismatch is rejected rather than
served as current. A freshly created operation starts `pending` with an
`exact-search` fallback until an index completes for the exact revision.

## Consumer responsibilities

- Provide a canonical repository id and a full 40- or 64-char Git object id.
- Import only the supported facade (`scripts/__init__.py`); treat `atomic.py`
  as private.
- Never commit `operation.json`; commit only the deterministic manifest, and
  choose its repository-relative target path (this library claims no
  main-writing location).
- Log rich diagnostics to your own protected sink — the durable `SafeError` is
  intentionally bounded (class + summary), with no traceback, stderr,
  environment, or absolute paths.

## Fail-closed recovery

Truncated JSON → `CorruptRecordError`. Unknown `schema_version` →
`SchemaVersionError` (never downgraded or rewritten). Unsafe path →
`UnsafePathError` (never normalized). Duplicate producer id →
`DuplicateProducerError`. Illegal transition → `InvalidTransitionError`. In
every case the runtime refuses rather than inventing a fresh-looking record.

## Compatibility

The three Draft 2020-12 schemas ship in
`skills/project-context-runtime/install_assets/openspec/schemas/` and resolve
their sibling `$ref`s locally with no network fetch. `schema_version` is exactly
`1`; a future schema change must use a new version, and readers must fail closed
on any version they do not recognize.
