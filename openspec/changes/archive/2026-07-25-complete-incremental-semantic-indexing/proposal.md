# Change: Complete incremental semantic indexing

> Parent roadmap: `project-context-refresh-lifecycle`
> Roadmap item: `ri-02`
> Change ID: `complete-incremental-semantic-indexing`
> Effort: L
> Priority: 1

## Why

`index_repo` currently opens Postgres, writes legacy repository metadata, and
then raises `NotImplementedError`. The CocoIndex functions are never placed in
an `App`, all advertised end-to-end tests skip unconditionally, and the write
path still targets one mutable table per repository.

The revision-aware registry delivered by `ri-01` supplies durable identity,
leases, immutable storage keys, and canonical promotion. This change must make
that boundary executable without allowing a moved Git ref, changed read scope,
or changed indexing policy to masquerade as the same index.

## What Changes

- Replace the `NotImplementedError` path with a typed, dependency-injected
  indexing operation: source proof, ensure, claim, lease heartbeat, incremental
  build, storage verification, terminal registry update, and optional canonical
  promotion.
- Extend revision-aware identity with deterministic policy and pipeline
  fingerprints, persist per-revision file manifests, and add lease renewal plus
  compatible-parent lookup.
- Build each revision in its own `code_chunks__<storage_key>` table. Copy
  unchanged rows from a compatible ready ancestor and run CocoIndex only for
  added or changed eligible files; deleted and newly ineligible files are not
  copied.
- Enforce index-time eligibility before content is read or embedded:
  configured include/exclude rules, nested `.gitignore`, `read_allow`, `deny`,
  non-overridable secret/generated-tree exclusions, and repository containment.
- Configure local or OpenAI-compatible/LiteLLM embedding explicitly. The
  coordinator LLM gateway is an opt-in OpenAI-compatible endpoint, not an
  imported coordinator dependency or a production default.
- Replace placeholder E2E tests with executable fixtures and resource-gated
  Postgres/embedder tests.
- Pin the verified `cocoindex-code` compatibility line instead of claiming that
  the floating `0.*` constraint is a hard pin.

## Selected Approach

Use **copy-forward immutable revisions with a persisted file manifest**.

For a new revision, the operation selects the newest ready ancestor with the
same repository, namespace, embedder, policy, and pipeline contract. Each lease
builds in attempt-specific staging, copies rows for unchanged eligible files,
processes only added/changed eligible files, and omits deleted/ineligible files.
A short fenced publish transaction verifies the current lease, atomically
promotes the winning staging table and manifest to the immutable storage key,
and only then permits readiness. A duplicate ready request returns the existing
operation without invoking the embedder.

A blocking, non-skipping target-contract test will prove copied-row ownership,
retry, stale-attempt fencing, and atomic publication through the selected thin
`storage_pg.py` adapter. CocoIndex remains responsible for source processing,
chunking, and embedding; the adapter owns revision storage and fenced
publication. It SHALL NOT fall back to rebuilding every revision.

## Alternatives Considered

### Stable mutable staging table followed by a snapshot

This preserves CocoIndex component identity naturally, but introduces another
mutable storage lifecycle, namespace-wide locking, crash recovery around the
snapshot boundary, and a second table naming contract. It remains a future
optimization if copy-forward measurements show unacceptable overhead.

### One isolated CocoIndex App and full rebuild per revision

This is simple and safe, but fails the roadmap requirement that a one-file
revision change only re-embeds changed content.

### Content-addressed global embedding cache

This maximizes reuse across repositories and namespaces, but adds a new shared
privacy, retention, and invalidation boundary. It is disproportionate to this
change and can be layered behind the embedding protocol later.

## Dependencies

- `ri-01` / `add-revision-aware-semantic-index-registry`
- CocoIndex `>=1.0.13,<1.1.0`
- Verified `cocoindex-code` `0.2.37` compatibility line
- Optional live integration with `add-coordinator-llm-gateway`; core indexing
  does not depend on that proposal being implemented

## Acceptance Outcomes

- `index_repo` completes against reachable Postgres and embedder resources and
  never reaches the former `NotImplementedError`.
- A request proves a clean materialized checkout for an exact full Git object
  ID before a registry row is created; symbolic, abbreviated, mismatched,
  dirty, or path-escaping sources fail closed.
- Duplicate requests reuse one durable operation. A compatible one-file
  revision change produces a complete isolated index while embedding only that
  changed eligible file; deleted files disappear.
- Ignored files, secrets, generated dependency trees, denied files, and files
  outside `read_allow` never reach the content reader, embedder, or target.
- Policy, pipeline, and embedding-parameter changes produce a distinct index
  identity and cannot reuse stale rows.
- Long runs renew their lease; a stale worker cannot complete after takeover.
- A stale attempt cannot mutate published storage or manifests after takeover.
- Missing DSN produces a structured ephemeral `not_configured` result because
  no database is available. Missing embedder with reachable Postgres records a
  durable `not_configured` state. Runtime failures after claim are recorded as
  `failed` whenever the registry remains reachable.
- Main indexes are promoted only after verified readiness and guarded
  compare-and-swap. Feature and work-package indexes are never promoted.
- Gateway embedding is opt-in through an OpenAI-compatible base URL/key/model;
  absent configuration performs no download or network attempt.

## Impact

- **Affected specs**: `code-search`
- **Affected code**:
  `packages/code-search/src/code_search_pkg/{cli,indexer_pg,schema,registry*}.py`,
  new light indexing policy/orchestration modules, migration `030`, code-search
  tests and fixtures, and `docs/guides/code-search.md`
- **Affected data**: additive index fingerprints and file manifests; immutable
  per-revision chunk tables
- **Unaffected surface**: query behavior and coordinator capability exposure
  remain owned by `ri-03`

## Approval

The explicit `$autopilot-roadmap project-context-refresh-lifecycle` invocation
provides inherited Gate 1 and Gate 2 approval for this roadmap-selected
direction and its implementation-ready decomposition.
