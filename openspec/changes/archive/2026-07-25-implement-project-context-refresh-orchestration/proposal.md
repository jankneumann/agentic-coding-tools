# Implement project context refresh orchestration

> Parent roadmap: `project-context-refresh-lifecycle`
> Change ID: `implement-project-context-refresh-orchestration`
> Effort: L
> Priority: 7

## Why

ri-01…ri-06 delivered every piece of a durable, revision-addressed context refresh —
the runtime store and manifest (ri-06), four deterministic producers (ri-05), the
architecture producer (ri-04), and the semantic index (ri-02) — but nothing runs them
together. Merge and branch workflows need **one idempotent operation** that refreshes
all project context for a revision and emits a single durable manifest, so downstream
gates (ri-10/ri-11) and impact declarations (ri-08/ri-09) can reuse one lifecycle.

## What Changes

- Add a `refresh-project-context` orchestrator (a module + CLI in the existing
  `project-context-refresh` skill, plus `make` targets) that:
  - opens/reuses the one canonical ri-06 operation for a `(repository, revision)`;
  - runs the four ri-05 deterministic producers and the ri-04 architecture producer,
    recording each canonical `ProducerResult` **before** touching the semantic index;
  - attempts the ri-02 semantic index last, recording a `SemanticIndexReference` —
    degraded (never fatal) when Postgres/the service is unavailable;
  - finalizes into SUCCEEDED / DEGRADED / FAILED and writes the durable manifest.
- Keep every producer independently runnable (`--producer <id>`) with its owner
  preserved in the manifest.
- **Configured-only**: the "capability" producer named in the source proposal has no
  canonical owner and is NOT built here — it is recorded as a follow-up roadmap item.

## Dependencies

- `ri-02` (semantic index) · `ri-04` (architecture producer) · `ri-05` (deterministic
  producers) · `ri-06` (runtime store + manifest) — all landed on `main`.

## Acceptance Outcomes

- One command runs all configured context producers for a specified repository
  revision and emits a valid refresh manifest.
- A second run for the same revision produces no repository diff and reuses or
  verifies the same semantic-index operation.
- Failure or degradation of semantic indexing does not corrupt or discard successful
  deterministic producer output.
- Each producer remains independently runnable and its refresh result identifies its
  canonical owner.
- No refresh path independently writes main outside an authorized sync-point
  operation.

## Out of Scope / Follow-ups

- A `capability` context producer (named in the source proposal, no canonical owner
  today) — filed as follow-up coordinator issue `dced1d51` (candidate change
  `add-capability-context-producer`). The orchestrator iterates the registry, so it
  will pick the producer up automatically once one is registered.
- CI/merge drift gates over the manifest (ri-10/ri-11) and work-package impact
  declarations (ri-08/ri-09).

## Rationale

One idempotent operation must coordinate all project context so merge and branch
workflows can reuse a single lifecycle without re-implementing producer ownership.
