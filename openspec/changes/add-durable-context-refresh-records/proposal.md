# Change: add-durable-context-refresh-records

> Parent roadmap: `project-context-refresh-lifecycle`
> Roadmap item: `ri-06`

## Why

Project-context refresh callers currently have no shared, durable identity or
result model. The architecture refresh RPC keeps status in a subprocess-local
singleton, roadmap checkpoints use a roadmap-specific file shape, and review
manifests are durable but domain-specific; none can tell a later process
whether a repository revision already has a refresh operation or whether its
repository artifacts and external semantic index are current.

This change establishes the persistence and schema boundary required by the
later refresh orchestrator. It makes retries idempotent by repository and
source revision, gives every producer a truthful status and remediation shape,
and separates deterministic Git artifacts from external semantic-index state.

## What Changes

- Add a non-user-invocable `project-context-runtime` shared library with typed
  operation, producer-result, semantic-index-reference, and manifest models.
- Persist mutable operation records below the repository's Git common
  directory so all worktrees and later processes see the same operation.
- Derive a stable operation ID from the canonical repository ID and exact
  source revision; duplicate creation returns the existing record.
- Serialize operation updates atomically under a per-operation cross-process
  lock and enforce an explicit state-transition model.
- Add versioned JSON Schemas for shared types, mutable operation records, and
  deterministic committed manifests.
- Add a canonical deterministic manifest writer that records producer
  versions, changed repository artifacts, validations, semantic-index
  operation status, and degraded fallbacks without volatile rerun metadata.
- Reject unknown schema versions, unsafe repository-relative paths, duplicate
  producer identities, invalid transitions, and malformed records instead of
  inferring freshness.
- Add install-asset and cross-process tests plus consumer documentation for the
  downstream architecture, orchestration, checkpoint, and merge changes.
- No breaking behavior is introduced; this is a new shared capability.

## Approaches Considered

### Approach 1: Git-common-dir ledger plus committed manifest

Store mutable operation records under
`$(git rev-parse --git-common-dir)/project-context/refresh-operations/` and
write the deterministic repository manifest separately through a shared Python
library.

Pros:

- Shares operation state across managed worktrees and process restarts.
- Adds no coordinator, database, or network availability dependency.
- Keeps volatile retry metadata out of Git while allowing deterministic
  project context to be committed.
- Matches existing file-backed checkpoint and atomic-manifest patterns.

Cons:

- Durability is scoped to one clone; a different machine cannot query the
  ledger unless a higher-level service mirrors it.
- Requires explicit file locking and crash-safe writes.

Effort: M

### Approach 2: Coordinator-backed operation service

Add coordinator API, MCP, and Postgres tables for refresh operations, producer
results, and manifests.

Pros:

- Makes operation state queryable across machines and cloud agents.
- Reuses coordinator authentication, audit, and database durability.

Cons:

- Makes local refresh correctness depend on coordinator and Postgres
  availability.
- Expands this roadmap item into API, database migration, deployment, and
  authorization work.
- Conflicts with the proposal's requirement that deterministic refresh remain
  usable when external services are unavailable.

Effort: L

### Approach 3: Commit the entire operation journal

Store mutable operation status, attempts, errors, and the final manifest
directly in the worktree as versioned repository files.

Pros:

- Requires no hidden local state.
- Makes all operation history visible in Git.

Cons:

- Retry timestamps and in-flight state create nondeterministic diffs and
  convergence commits.
- Feature worktrees can diverge or race on global operation history.
- External semantic state would be misleadingly represented as a Git artifact.

Effort: M

### Recommended

Approach 1 is recommended. It provides the required cross-process and
cross-worktree durability without coupling the refresh lifecycle to an
external service, while retaining a deterministic Git artifact for human and
agent consumers. The clone-local boundary is explicit and can later be adapted
to a remote operation store behind the same models if cross-machine querying
becomes necessary.

### Selected Approach

Approach 1 is selected under the inherited
`$autopilot-roadmap project-context-refresh-lifecycle` approval. The roadmap
already fixes the direction: durable and idempotent records, deterministic
manifests, and external semantic state represented by references rather than
pretending it is committed state.

## Impact

### Architecture layers

- **Execution:** refresh producers and orchestrators gain a shared local
  persistence and manifest API.
- **Coordination:** worktrees and subprocesses coordinate on one operation
  identity and per-operation lock.
- **Trust:** persisted paths and error summaries are validated and
  repository-relative; unknown or malformed state fails closed.
- **Governance:** versioned contracts make freshness claims and degraded
  fallbacks reviewable.

### Spec deltas

- `project-context-refresh-records`:
  `specs/project-context-refresh-records/spec.md` adds the durable identity,
  persistence, producer-result, manifest, and compatibility requirements.

### Expected implementation touchpoints

- `skills/project-context-runtime/SKILL.md`
- `skills/project-context-runtime/scripts/models.py`
- `skills/project-context-runtime/scripts/atomic.py`
- `skills/project-context-runtime/scripts/store.py`
- `skills/project-context-runtime/scripts/manifest.py`
- `skills/project-context-runtime/install_assets/openspec/schemas/*.schema.json`
- `skills/tests/project-context-runtime/**`
- `docs/project-context-refresh.md`

### Dependencies and consumers

- This change has no roadmap prerequisite and does not depend on a semantic
  index implementation or coordinator database.
- `make-architecture-refresh-revision-aware`,
  `implement-project-context-refresh-orchestration`,
  `add-branch-local-context-checkpoints`, and
  `integrate-main-context-convergence` consume these records later.
- Semantic-index operation and registry identifiers remain opaque contracts
  owned by the semantic indexing changes.

## Rollback

Because the capability is additive, rollback consists of removing the new
runtime and installed schemas before downstream consumers adopt them.
Operation files live outside tracked content under the Git common directory
and may be left for forensic inspection or deleted with an explicit
repository-scoped cleanup command. A future schema change must use a new
`schema_version`; readers never rewrite or silently reinterpret an unknown
version.
