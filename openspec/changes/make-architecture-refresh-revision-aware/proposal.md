# Make Architecture Refresh Revision-Aware

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `make-architecture-refresh-revision-aware`
> Effort: M
> Priority: 4

## Why

`refresh-architecture` is the canonical producer for the repository's architecture
graph, summary, diagnostics, parallel zones, views, and report. Consumers currently
cannot prove those artifacts describe the code they are reading:

- freshness is inferred from a six-hour graph mtime even when relevant source changed;
- `affected_tests.py` also trusts graph age instead of source provenance;
- subprocess RPC calls cannot observe a module-local refresh handle created by a
  previous process; and
- wall-clock generation metadata makes unchanged runs produce repository churn.

The roadmap's `add-durable-context-refresh-records` item establishes the shared
`project-context-runtime`, Git-common-dir operation store, atomic writer, and canonical
`ProducerResult` model. This change consumes that capability rather than implementing
a second architecture-only persistence subsystem.

## What Changes

- Add a committed `docs/architecture-analysis/architecture.provenance.json` document
  recording the analyzed source revision, dirty-input state, architecture producer
  version, relevant input fingerprint, generation mode, owned artifacts, and digests.
- Add architecture-specific provenance utilities for deterministic timestamps,
  relevant-input discovery, content hashing, and stable producer output.
- Add generate and read-only check modes. Check mode recomputes architecture identity
  and reports exact stale/missing/mismatched artifacts without writing.
- Stage and validate generated outputs before promotion. Failed generation preserves
  the last known-good committed set.
- Replace wall-clock metadata in repository architecture artifacts with a source
  revision-derived timestamp.
- Add an architecture adapter over `project-context-runtime`: create/load the canonical
  revision operation, record one `producer_id=architecture` `ProducerResult`, and read
  that producer result across processes.
- Keep the existing architecture RPC method names as a compatibility facade. Map
  canonical operation/producer state to legacy `RUNNING|COMPLETED|FAILED|UNKNOWN`
  responses and add revision/fingerprint provenance.
- Retain `graph_mtime` and `max_age_hours` as deprecated compatibility fields, but
  never use them to decide freshness.
- Require matching provenance before affected-test selection trusts the graph.

## Scope

### In Scope

- Architecture producer/check logic, adapter, RPC, tests, and skill guidance.
- Coordinator refresh client/tests for additive response fields.
- One architecture-specific provenance JSON Schema.
- Make/documentation entry points.

### Out of Scope

- Git-common-dir paths, lock implementation, atomic operation persistence, operation
  transitions, generic manifest writing, or canonical `ProducerResult` definitions;
  `add-durable-context-refresh-records` owns them.
- Finalizing the multi-producer operation; ri-07 owns orchestration/final outcome.
- Main convergence (ri-11), semantic indexing, and analyzer/graph-schema replacement.

## Dependencies

- **Requires ri-06:** `add-durable-context-refresh-records`.
- Reuses `skills/project-context-runtime` models, store facade, atomic primitives, and
  installed context-refresh schemas.
- ri-07 consumes this adapter/result; ri-10 consumes check mode; ri-11 invokes it via
  shared context convergence.

## Approaches Considered

### Approach A: Architecture Provenance Adapter over project-context-runtime (Recommended)

Keep architecture-specific deterministic evidence beside the generated artifacts and
use ri-06 for operation identity, locking, persistence, atomic record updates, and
canonical producer results.

**Pros**

- One durable operation model across all context producers.
- Preserves standalone architecture generation and its specialized freshness rules.
- Fixes cross-process RPC status without duplicating persistence contracts.
- Gives ri-07 a directly consumable canonical producer result.

**Cons**

- Requires ri-06 to land first.
- RPC status is an architecture-specific projection, not the whole operation status.
- Architecture freshness still needs its own evidence contract.

**Effort:** M

### Approach B: Architecture-Owned Git-Local Ledger

Add a separate architecture operation schema, lock, record store, and lifecycle below
the Git common directory.

**Pros**

- Could land without ri-06.
- Architecture could define every status detail independently.

**Cons**

- Duplicates the shared runtime's exact ownership.
- Creates conflicting operation identities and retry semantics.
- Forces ri-07 to reconcile two persistence systems.

**Effort:** M

### Approach C: Coordinator-Backed Architecture Operations

Move architecture status into coordinator/Postgres.

**Pros**

- Multi-host visibility.

**Cons**

- Breaks standalone/offline operation.
- Adds deployment and database dependencies outside this item's scope.
- Still bypasses the roadmap's shared runtime.

**Effort:** L

### Selected Approach

Proceed with **Approach A**. The roadmap now explicitly orders ri-04 after ri-06.
Architecture owns provenance, deterministic generation, freshness, and its status
facade; `project-context-runtime` owns all shared operation durability and types.

## Acceptance Outcomes

- Every successful full or quick refresh writes schema-valid architecture provenance
  with exact source SHA, dirty state, producer version, input fingerprint, mode, and
  artifact digests.
- Check mode is content-based and mtime-independent, with precise drift reasons.
- Two runs with identical source/producer/tool identity are byte-identical and create
  no second repository diff.
- The adapter records architecture through ri-06's canonical `ProducerResult` and
  shared operation store; no architecture-specific operation ledger/schema exists.
- Another process can query the architecture producer status through the RPC facade.
- The adapter does not finalize the whole project-context operation.
- Existing coordinator callers retain fail-safe compatibility.
