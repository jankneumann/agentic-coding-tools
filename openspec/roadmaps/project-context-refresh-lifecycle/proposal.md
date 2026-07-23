# Unified Project Context Refresh Lifecycle

## Motivation

The repository produces several kinds of durable context for humans and coding
agents: OpenSpec capability specifications, API contracts, architecture graphs
and reports, decision timelines, workflow documentation, and a semantic code
index. These artifacts are refreshed by different skills, at different times,
with different durability guarantees. As a result, code can land while the
context used to plan and implement the next change remains stale.

The drift is observable today. The committed architecture snapshot predates
hundreds of commits even though `cleanup-feature` contains a nominal
`make architecture` step. The semantic-search surfaces exist, but
`index_repo` does not execute the CocoIndex pipeline, the coordinator does not
advertise a code-search capability to skills, and coding-job prompts do not
consume semantic results. The active `add-update-documentation-skill` proposal
addresses mechanical documentation inventories, but it does not cover the
larger capability/API/architecture/concept/index lifecycle.

`merge-pull-requests` is the correct main-branch convergence owner. It already
operates at the synchronization point where merged source is authoritative and
where OpenSpec cleanup can be invoked. It should orchestrate a shared project
context refresh after each successful merge (and after `cleanup-feature
--post-merge` for OpenSpec changes), commit and push deterministic repository
artifacts, and enqueue semantic indexing for the exact resulting commit.

Success means that a merge leaves both the code and its working context current:
humans can inspect accurate capability, API, architecture, and decision
artifacts; agents can retrieve scoped semantic code context; and every consumer
can detect and safely handle stale or unavailable context rather than silently
using it.

## Capabilities

### Capability: Complete semantic code-search runtime

Finish the currently incomplete CocoIndex/Postgres runtime. `index_repo` must
execute the incremental pipeline, update registry freshness metadata, and
support reliable coordinator startup/query wiring. The runtime must expose
repository and commit freshness, advertise `CAN_CODE_SEARCH`, and disable or
degrade semantic retrieval when the requested revision is not indexed.

Index namespaces must be revision-aware. A feature worktree or large
work-package checkpoint must never overwrite the shared `main` index. The
runtime may use a `(repo, ref-or-commit)` identity, isolated per-ref slugs, or an
equivalent design, provided query provenance and garbage collection are
explicit.

This capability may use the embedding endpoint delivered by the active
`add-coordinator-llm-gateway` change, but must retain an explicit unavailable
state and exact-search fallback when no embedder is configured.

**Acceptance Outcomes:**

- `index_repo` completes against a reachable Postgres/embedder environment
  without raising `NotImplementedError` and reprocesses only changed files.
- The registry records the exact indexed commit, model, embedding dimension,
  chunk count, completion status, and last error.
- Query results identify the indexed revision and are never returned as current
  when that revision differs from the requested revision.
- Coordinator capability discovery reports `CAN_CODE_SEARCH` only when the
  query service is initialized and a usable index is available.
- Concurrent feature/work-package indexing cannot mutate or masquerade as the
  canonical `main` index.

### Capability: Add a project-context refresh orchestrator

Create a shared `refresh-project-context` skill/service that coordinates the
independent context producers without collapsing their ownership boundaries.
It invokes the canonical tools for capability specs, API contracts,
architecture analysis, decision timelines, generated documentation, and
semantic indexing, then emits one machine-readable refresh manifest.

The manifest must record the source revision, producer versions, artifacts
changed, validation results, semantic-index operation/status, and any degraded
fallbacks. Deterministic repository artifacts are staged together; external
index state is represented by a durable operation and registry record rather
than pretending it is a Git artifact.

The active `add-update-documentation-skill` proposal should be absorbed,
superseded, or explicitly depended upon so its generated-block and drift-check
work is not implemented as a parallel competing lifecycle.

**Acceptance Outcomes:**

- One command refreshes all configured project-context producers and emits an
  idempotent manifest tied to a Git commit.
- Producers remain independently runnable and testable; semantic-index failure
  does not corrupt architecture or documentation artifacts.
- A second run at the same revision produces no repository diff and either
  reuses or verifies the same semantic-index operation.
- The refresh reports `fresh`, `degraded`, `failed`, or `not-configured` per
  producer with actionable remediation.

### Capability: Integrate context refresh into merge-pull-requests

Make `merge-pull-requests` the primary main-branch context convergence owner.
For an OpenSpec PR it merges the PR, invokes `cleanup-feature --post-merge` to
archive the change and merge spec deltas, then runs the shared context refresh
against the resulting `main`. For non-OpenSpec PRs it runs the same refresh
directly after merge. Deterministic refresh output is committed and pushed as a
single follow-up convergence commit.

The flow must be idempotent across retries and must not race another sync-point
writer. It must not duplicate architecture/documentation refresh work in
`cleanup-feature`; direct/manual cleanup paths should delegate to the same
shared operation or clearly hand control back to `merge-pull-requests`.

Semantic indexing must be enqueued for the final pushed `main` SHA. A failed or
pending index operation marks semantic context stale and causes consumers to
fall back safely; it must never leave a stale index appearing current.

**Acceptance Outcomes:**

- Every successful merge path runs exactly one project-context convergence
  operation for the final `main` revision.
- OpenSpec archive/spec/decision output, architecture artifacts, API/docs
  output, and the refresh manifest are committed and pushed together.
- Retrying after interruption does not create duplicate commits, duplicate
  indexing work, or double-archive an OpenSpec change.
- Sync-point locking prevents concurrent main writers from interleaving
  refresh commits.
- The final handoff names the merged SHA, context-refresh SHA, and semantic
  index status.

### Capability: Add work-package context-impact checkpoints

Extend planning and implementation artifacts so large work packages declare
which context surfaces they can affect: capabilities, APIs/interfaces,
architecture, concepts/decisions, human/agent documentation, and semantic code.
The declaration is a reviewable hint, not the sole detector; changed-file and
contract analysis must catch undeclared impacts.

After each large or integration work package, `implement-feature` runs a
branch-local checkpoint. It updates change-context/spec/contract/decision
inputs, generates an architecture feature slice or diff, validates relevant
documentation, and optionally refreshes a revision-isolated semantic index.
It must not write project-global `main` artifacts from a feature worktree.

**Acceptance Outcomes:**

- Work-package schema and templates support explicit context-impact metadata.
- Validation fails when changed files imply a context impact omitted from the
  package declaration without an approved rationale.
- Large/integration packages produce a checkpoint report with affected
  capabilities, APIs, architecture nodes, decisions, docs, and index revision.
- Branch-local generated artifacts and indexes are isolated from canonical
  `main` context.

### Capability: Make deterministic context drift a validated gate

Add check modes and CI validation for deterministic context artifacts.
Architecture graphs/reports, generated documentation inventories, decision
timelines, API catalogues/generated bindings, and OpenSpec projections must be
regenerable and compared to the committed state. Staleness must be based on
source revision and producer inputs, not file modification time alone.

Architecture refresh RPC behavior must have durable, cross-process operation
state or be replaced by the shared refresh operation. A subprocess-local
singleton cannot claim idempotence or status continuity across calls.

**Acceptance Outcomes:**

- CI can regenerate deterministic context and fail with a precise artifact
  list when committed output is stale.
- Architecture freshness is tied to a Git SHA and changed inputs, not a six-hour
  mtime window.
- Refresh operation status survives process boundaries and can be queried after
  the triggering process exits.
- Merge validation distinguishes deterministic drift failures from optional
  external-service degradation.

### Capability: Supply semantic context to coding jobs

Integrate semantic retrieval into `context-engineering` and the coding skills
that dispatch or perform implementation, debugging, review, and validation.
Queries are derived from the task, requirements, target files, and errors;
results are scope-filtered, provenance-rich, deduplicated, and bounded by a
context budget.

Semantic retrieval complements exact search and direct source reading. When
code search is unavailable, stale, mismatched, or outside scope, the worker
must receive an explicit fallback state and continue with `rg`/filesystem
context. No skill may silently assume semantic results describe its working
revision.

**Acceptance Outcomes:**

- `context-engineering` detects `CAN_CODE_SEARCH` and requests results for the
  exact repository revision and work-package read scope.
- `implement-feature`, `quick-task`, `iterate-on-implementation`, debugging,
  validation, and implementation review can receive a bounded “Semantic code
  context” section.
- Every injected hit includes file, line range, score, indexed commit, and
  scope decision.
- Tests prove stale/unavailable semantic search falls back to exact search
  without blocking the coding job.
- Retrieval-quality and context-utility evaluations demonstrate measurable
  benefit before semantic context becomes enabled by default.

## Constraints

- `merge-pull-requests` shall remain the primary main-branch synchronization
  owner; the design must not introduce another independent main writer.
- `cleanup-feature` shall retain responsibility for OpenSpec task migration,
  archive, and spec-delta merge, but shared context refresh must not be
  duplicated between cleanup and merge flows.
- All local mutations must occur in managed worktrees until the authorized
  sync-point operation writes `main`.
- Deterministic context artifacts must be reproducible, staged, committed, and
  pushed atomically with their convergence record.
- External semantic indexing must be durable and idempotent by repository and
  commit. Stale results must fail closed and trigger an explicit exact-search
  fallback.
- Work-package scopes (`read_allow`, `deny`) must constrain both indexing
  queries and injected worker context.
- Generated context must carry source revision and producer metadata so humans
  and agents can judge freshness.
- The roadmap must reuse `refresh-architecture`, `update-specs`,
  `documentation-and-adrs`, and the existing documentation-sync proposal
  rather than reimplementing their domain logic.
- The embedding dependency on `add-coordinator-llm-gateway` must be explicit;
  no production-default enablement occurs before the semantic retrieval quality
  gate passes.
- Every roadmap item must be independently reviewable and must preserve an
  exact-search/direct-source fallback.

## Phases

### Phase 1: Make context producers truthful

- Complete semantic code-search runtime and revision-aware freshness.
- Make deterministic architecture/documentation/API/decision producers
  reproducible and checkable.

### Phase 2: Establish shared orchestration

- Add the project-context refresh orchestrator and durable refresh manifest.
- Add work-package context-impact declarations and branch-local checkpoints.

### Phase 3: Converge on main

- Integrate the shared refresh into `merge-pull-requests` after OpenSpec
  post-merge cleanup where applicable.
- Add CI and retry/idempotence gates around convergence.

### Phase 4: Consume current context

- Integrate scoped, revision-aware semantic results into coding-job context.
- Run retrieval-quality and context-utility evaluations before default-on use.

## Out of Scope

- Building an interactive codebase visualization UI; existing architecture
  artifacts may feed one later.
- Replacing OpenSpec, ADR/capability timelines, OpenAPI, or source code with a
  new universal knowledge store.
- Letting every producer write `main` independently.
- Blocking exact-search coding workflows when embeddings, Postgres, or the
  coordinator are unavailable.
- Rewriting all hand-authored documentation automatically.
- Indexing secrets, ignored files, generated dependency trees, or files outside
  the work package's permitted read scope.
- Making semantic retrieval default-on before the existing quality gate and
  new coding-context evaluation pass.
