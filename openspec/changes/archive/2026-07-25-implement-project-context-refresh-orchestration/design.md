# Design: Implement project context refresh orchestration

## Context

ri-01…ri-06 delivered the pieces of a durable, revision-addressed project-context
refresh but no single caller that runs them together:

- **ri-06 `project-context-runtime`** — the durable operation store
  (`OperationStore`: `create_or_load` / `begin_attempt` / `record_producer_result`
  / `record_semantic_index` / `finalize` / `record_manifest`) plus the manifest
  projection (`manifest.project_manifest` / `write_manifest`) and the canonical
  `ProducerResult` / `SemanticIndexReference` / `RefreshManifest` models.
- **ri-05 `project-context-refresh`** — four deterministic producers
  (`documentation.inventory`, `api.contracts`, `decisions.timeline`,
  `openspec.projection`) exposed through `registry.run_producer` /
  `list_producers`, each returning a canonical `ProducerResult`.
- **ri-04 `refresh-architecture`** — the `architecture` producer, recorded through
  its own idempotent `ArchitectureAdapter.record_architecture(result)`.
- **ri-02 semantic index** — `agent-coordinator/src/code_search.py`, a
  Postgres/CocoIndex service that indexes a repository at an exact revision. It is
  the one producer that can be *unavailable* (no DB) or *fail* at runtime.

ri-07 adds the missing coordinator: **one idempotent operation that drives every
configured producer for a specified revision, stages their outputs together, and
emits the durable manifest — without collapsing producer ownership.**

Scope was fixed with the requester: orchestrate only **configured** producers (the
proposal also names a "capability" producer that has no canonical owner anywhere —
it is recorded as a follow-up, not built here), and treat the semantic index as a
**degradable** producer whose absence or failure never discards deterministic work.

## Decisions

### D1 — The orchestrator owns coordination only; producers keep their owners
The new `orchestrator.py` (in the ri-05 `project-context-refresh` skill) imports
the runtime store, the ri-05 registry, the ri-04 adapter, and a new semantic-index
adapter. It never re-implements producer domain logic, never defines a result or
manifest model, and never merges canonical specs. It calls each canonical owner and
records the returned `ProducerResult` (or `SemanticIndexReference`) into the one
canonical operation. Housing it in the existing skill (rather than a near-duplicate
skill) reuses the runtime `sys.path` wiring and CLI; the ri-05 SKILL.md boundary
note ("does not own … orchestration (ri-07)") is updated to point at this module.

### D2 — One canonical operation per `(repository, revision)`, reused idempotently
`create_or_load(repository_id, source_revision)` yields a single operation keyed by
`derive_operation_id(repo, rev)`. A second run for the same revision reuses it. The
architecture adapter and this orchestrator both write into that same operation, so
architecture recorded by an ri-04 RPC and the deterministic producers coexist in one
record. Producer results are append-only and reject duplicate `producer_id`, so the
orchestrator records each producer at most once per attempt and treats an
already-present result as satisfied (idempotent reuse, not re-run).

### D3 — Deterministic producers are recorded before the semantic index is touched
Ordering is the durability guarantee. The orchestrator (a) `begin_attempt`, (b) runs
the four ri-05 deterministic producers + the ri-04 architecture producer and records
each result, then (c) attempts the semantic index last. A crash or failure in (c)
therefore cannot lose any result from (b): they are already persisted. This directly
satisfies "failure or degradation of semantic indexing does not corrupt or discard
successful deterministic producer output."

### D4 — Semantic index is degradable, never fatal
A new `semantic_adapter.py` maps ri-02 `code_search` outcomes to a
`SemanticIndexReference`:
- success → `SUCCEEDED` with `operation_id` + `registry_record_id` +
  `indexed_revision == requested_revision` (the model enforces these);
- DB/service unavailable, or an indexing error → a non-succeeded status carrying a
  bounded `Fallback` (never raising into the orchestrator).
The reference is stored via the store's *separate* `record_semantic_index` slot, so
a degraded index is structurally distinct from a failed deterministic producer.

### D5 — Terminal state is a pure function of recorded results
The orchestrator finalizes into exactly one terminal state; the manifest's
`refresh_status` follows mechanically (`_TERMINAL_TO_OUTCOME`), so the two can never
disagree:
- **FAILED** — any *required* deterministic/architecture producer returned `failed`
  (finalize requires a bounded `SafeError`).
- **DEGRADED** — no required producer failed, but at least one producer is `degraded`
  / a required one is `not-configured`, or the semantic index is not `SUCCEEDED`.
- **SUCCEEDED** — every configured producer is `fresh` and the semantic index
  `SUCCEEDED`.
`check` mode maps drift (a `degraded` producer with a failed validation) to a
non-zero exit without writing, reusing ri-05's exit-code convention (0 fresh · 2
drift · 1 failed).

### D6 — The manifest is durable but untracked; producer outputs stay byte-stable
After finalize, the orchestrator calls `write_manifest(record, target, repo_root=…)`
(project + schema-validate + atomic write) and records the pointer with
`record_manifest`. The manifest target is the **gitignored** repository-relative path
`.git-context/context-refresh-manifest.json`, not the tracked tree, because the
manifest embeds volatile identity (`operation_id`, `operation_created_at`). A
gitignored working-tree path (rather than a literal `.git/…` path) is used because
the ri-06 `ManifestPointer` requires a repository-relative path and, in a linked
worktree, `.git` is a gitdir *file* — a gitignored path resolves correctly in both
the primary checkout and every worktree. Keeping it untracked means "a second run for
the same revision produces no repository diff" holds by construction, while
deterministic producer *outputs* (e.g. `docs/architecture-analysis/*`) are byte-stable
by ri-05/ri-04's content-based design. The committed, reviewable surface remains the
producer outputs; the manifest is the durable machine record. (Because the working
tree is at one revision at a time, a single fixed manifest path is sufficient; a
different revision overwrites its own gitignored copy.)

### D7 — Every refresh path is worktree-scoped; main is never written directly
The orchestrator runs inside a managed worktree and only ever writes producer-managed
outputs and the git-dir manifest. `openspec.projection` stays projection-only.
Canonical spec merges and any main mutation remain the sync-point responsibility of
`cleanup-feature` — the orchestrator refuses to run against a bare/shared checkout
(reuses `checkout_policy`).

### D8 — CLI + Makefile, per-producer runnable; ownership via the registry
`cli.py` gains `refresh` (generate every configured producer + emit manifest) and
`refresh-check` (read-only drift) subcommands, plus a `--producer <id>` filter. A
`--producer` run is a targeted regenerate-and-report: it never drives the shared
per-revision operation to a terminal state (which would poison a later full refresh)
and emits no aggregate manifest. `make refresh-project-context` /
`make refresh-project-context-check` wrap the full runs.

The ri-06 `ProducerResult` has **no `owner` field** — canonical ownership lives on the
registry `ProducerSpec`. Rather than modify the landed ri-06 contract, the refresh
*summary* joins each result's stable `producer_id` to its owner via the registry (and
an explicit `architecture -> refresh-architecture` entry, since architecture is a
separate seam). Producer identity in the manifest is the stable `producer_id`, which
maps 1:1 to an owner, so ownership is never collapsed.

### D9 — One immutable operation per revision; resume re-attempts only the mutable index
The ri-06 operation store is append-only per producer and content-addressed by
revision, so a producer's result for an exact revision is immutable. A fully
`succeeded` operation is therefore **reused verbatim** on a repeat run (and, if a
crash left the manifest pointer `absent`, the reuse path re-projects and records it).
A `degraded`/`failed` operation is **resumed**: already-recorded producers are not
re-run (their result is sealed for the revision), and only the *mutable* semantic
index is re-attempted — which can lift `degraded -> succeeded` once the index returns.
Concurrent same-revision refreshes converge rather than crash: a losing
`record_producer_result` (`DuplicateProducerError`) or `finalize`
(`InvalidTransitionError`) reloads the persisted record.

## Failure Behavior

- An adapter that raises is reduced to a bounded `SafeError` (reuse ri-05's
  `_bounded_safe_error`) and recorded as a `failed` result — the orchestrator never
  propagates a traceback into the operation.
- A `FAILED` finalize always carries a `SafeError`; a `DEGRADED`/`SUCCEEDED` finalize
  carries none (store invariant).
- Semantic-index errors are caught in the adapter and become a degraded reference —
  they never reach `finalize` as an exception.
- A non-terminal operation cannot be projected (`project_manifest` raises), so the
  orchestrator always finalizes before writing the manifest.

## Test Strategy

- Unit: outcome-decision table (D5) over synthetic `ProducerResult` sets;
  semantic-adapter mapping for success / unavailable / error (no DB required — the
  degraded paths are exercised with the coordinator import stubbed/absent).
- Idempotency: two orchestration runs at a fixed revision → identical recorded
  operation, no repository diff, semantic reference reused (D2, D6).
- Corruption-resistance: inject a semantic failure after deterministic producers are
  recorded → deterministic results survive, outcome is DEGRADED (D3, D4).
- Ownership: every manifest producer entry carries `producer_id` + `owner`; a single
  `--producer` run records exactly one result (D1, D8).
- Boundary: orchestrator refuses a shared checkout; manifest lands under `.git/`,
  never the tracked tree (D6, D7).
- Fixtures reuse the ri-06 installed schemas; the run exports `SOURCE_DATE_EPOCH`
  (analyzed commit ts) so reruns are byte-identical.
