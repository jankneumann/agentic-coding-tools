---
name: project-context-runtime
description: "Durable, versioned identity, producer-result, and manifest records for project-context refresh callers"
category: Infrastructure
tags: [project-context, refresh, runtime, shared-library]
---

# Project Context Runtime

Shared library providing the durable identity, producer-result, semantic-index
reference, and deterministic manifest records used by every project-context
refresh caller (architecture refresh, the refresh orchestrator, branch-local
checkpoints, and main convergence).

This is an infrastructure skill — not user-invocable. Import from
`<skill-base-dir>/scripts/` after resolving this loaded skill directory, or add
`scripts/` to `sys.path` and import the bare module names.

## What it owns

- `scripts/models.py` — strict, versioned dataclasses, enums, typed
  fail-closed exceptions, deterministic operation-identity derivation, and
  offline JSON-Schema validation.
- `scripts/atomic.py` — crash-safe atomic JSON writes (same-directory temp file,
  fsync, atomic replace, parent fsync) and cross-process advisory file locking.
  Private runtime-core; not part of the supported facade.
- `scripts/store.py` — the `OperationStore`, a Git-common-dir–backed durable
  ledger with per-operation locking and a validated state machine.
- `scripts/manifest.py` — deterministic, byte-stable manifest projection and an
  atomic committable writer.
- `install_assets/openspec/schemas/*.schema.json` — the three versioned Draft
  2020-12 contracts (types, operation, manifest).

## Supported facade

```python
from scripts import (
    OperationStore,      # durable create/resume/transition
    write_manifest,      # deterministic committable projection
    OperationRecord, RefreshManifest, ProducerResult,
    derive_operation_id,
)
```

## Boundaries

- Records are durable per **clone**: the store shares state across linked
  worktrees and later processes, not across machines.
- The mutable `operation.json` ledger is never committed; only the deterministic
  manifest projection is a repository artifact.
- Unknown schema versions, malformed records, unsafe paths, duplicate producer
  identities, and illegal transitions fail closed and are never coerced into a
  fresh-looking record.
- Semantic-index state is an opaque external reference; any status other than
  `succeeded` (with `indexed_revision == requested_revision`) requires an
  explicit fallback.

See `docs/project-context-refresh.md` for the full consumer contract.
