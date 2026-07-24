# Design: Complete incremental semantic indexing

## Context

`ri-01` established an immutable revision-aware registry, but intentionally left
the legacy indexer and query paths untouched. The remaining write path has four
conflicting requirements:

1. every ready target must describe one exact Git revision;
2. a small revision delta must not re-embed the whole repository;
3. index-time scope must prevent denied content from reaching an embedder;
4. unavailable optional infrastructure must degrade explicitly.

CocoIndex obtains incrementality from stable App/component state and declarative
target reconciliation. Merely changing its target table for each revision does
not prove cross-revision memo reuse. The design therefore makes reuse explicit
at the immutable storage boundary.

## Decisions

### D1 — Prove the materialized source before creating identity

`IndexRequest.source_revision` is a full lowercase 40- or 64-character object
ID. The source prover verifies:

- `repo_root` is the same canonical worktree recorded for `repo_slug` in
  repository metadata, with a stable Git common-directory fingerprint;
- `HEAD` resolves exactly to `source_revision`;
- tracked and untracked state relevant to eligibility is clean;
- all eligible paths normalize below `repo_root` and symlinks cannot escape;
- the same proof still holds immediately before readiness.

Symbolic or abbreviated revisions, dirty/mismatched worktrees, path escapes, and
source mutation fail before a falsely labeled index becomes ready.

### D2 — Fingerprint every computation-affecting contract

The `ri-01` natural key is extended with:

- `policy_fingerprint`: includes include/exclude rules, gitignore behavior,
  read/deny scope, hard security denies, and secret-scan policy;
- `pipeline_fingerprint`: includes chunker versions/options, path-aware ID
  version, CocoIndex/cocoindex-code compatibility, and storage adapter version;
- `embedder_fingerprint`: includes provider mode, model, dimension, and indexing
  parameters, but excludes credentials.

The database uniqueness contract includes these fingerprints. A changed scope,
chunker, provider parameter, or dependency compatibility line creates a new
index rather than reusing an incompatible ready row. Fingerprints hash
UTF-8 canonical JSON with recursively sorted object keys and schema-normalized
arrays; arbitrary provider keys, non-finite numbers, credential values, and
secret-like parameter names are rejected before hashing.

### D3 — Copy forward from a compatible immutable ancestor

The operation selects the newest ready Git ancestor in the same repository and
namespace with identical model, dimension, and D2 fingerprints.

For revision B:

1. create an attempt-specific staging table and manifest keyed by
   `(index_id, attempt_count)`;
2. copy rows belonging to unchanged eligible files from ancestor A into the
   staging table;
3. run CocoIndex only for added/changed eligible files;
4. omit deleted and newly ineligible paths;
5. persist B's complete attempt manifest;
6. verify table schema, vector index, row count, and manifest coverage;
7. acquire a short Postgres advisory publish lock keyed by `index_id`, verify
   the current lease/fencing generation, atomically rename the winning staging
   table to the final storage key, publish its manifest, and remove older
   attempt artifacts;
8. mark B ready with the same current lease token.

If no compatible ancestor exists, all eligible files are processed. A retry
starts a fresh attempt staging table. Stale workers remain confined to their own
attempt tables and cannot rename or publish after lease takeover. No incomplete
table is query-visible because `ri-03` will consume only `ready` records.

The selected `storage_pg.py` adapter owns copy-forward, per-file changed-row
replacement, attempt tables, verification, and fenced publication. CocoIndex
owns source processing, chunking, and embedding but does not own table
lifecycle. The mandatory target-contract test uses a deterministic fake and
never skips; live Postgres tests verify the same frozen contract. The boundary
is recorded in `contracts/target-strategy.md`.

Crash retry is explicit: discard/recreate only the new attempt's staging table
and manifest; copy unchanged rows; transactionally replace each changed file's
staged rows; create and verify HNSW; verify complete manifest coverage; then
perform the fenced publish. Failure-injection tests cover each boundary.

### D4 — Enforce one canonical eligibility policy before read

Eligibility is evaluated over normalized repository-relative paths in this
order:

```text
exact revision
  ∩ configured includes
  − configured excludes
  − root/nested .gitignore
  ∩ read_allow
  − deny
  − non-overridable secret/credential patterns
  − generated/dependency trees
  − symlink/path escapes
```

Deny wins. Missing or invalid referenced scope fails closed. Baseline exclusions
include `.env*`, private keys/certificates, credential files, hidden secret
configuration, dependency trees, caches, and generated build output. Content
rejected by path policy is never read. A built-in, pinned local secret-scanner
protocol runs before content can be sent to a remote provider; a scan finding,
timeout, or scanner error fails the operation closed and records only a
sanitized reason. The scanner has bounded per-file and operation timeouts and
never sends content remotely.

### D5 — Use an explicit embedding protocol

The light orchestration layer depends on an `EmbeddingProvider` protocol with
model ID, dimension, indexing parameters/fingerprint, readiness, and embedding
operations.

Adapters may use:

- explicitly configured local sentence-transformers;
- an explicitly configured OpenAI-compatible/LiteLLM endpoint;
- the coordinator-managed gateway through that same OpenAI-compatible adapter.

Gateway integration is configuration compatibility, not an import from the
coordinator. Base URL, scoped key, model, and dimension are required. When an
intended model/dimension contract is declared but its package, credential, or
endpoint is unavailable, a durable operation may be marked `not_configured`.
When model/dimension are wholly absent, no safe natural key exists: CLI
preflight returns an ephemeral `not_configured` result before constructing an
`IndexRequest`. Neither path downloads a model or performs an unrequested
network call.

Indexing and query parameters remain separate and are documented for `ri-03`;
the ready record freezes the indexing contract.

### D6 — Heartbeat the exact-index lease

After `ensure_index`, a ready compatible record short-circuits. Otherwise one
worker claims the row. A heartbeat renews the current lease during source
processing, embedding, copying, and verification.

Only the current token may renew or complete. Lease loss cancels local work and
prevents readiness. Every attempt writes to generation-specific staging; only a
current-token publish transaction can rename staging to the final storage key.
A replacement worker therefore cannot be corrupted by a late write from the
former worker.

Main promotion is a separate compare-and-swap after readiness. A successful
older main build may remain ready without becoming canonical if another main
revision was promoted first. Feature and work-package indexes are never
promoted.

### D7 — Distinguish unavailable from failed

- No DSN: return a structured ephemeral `not_configured` result. A durable
  Postgres row is impossible.
- Registry reachable, embedder absent: claim and durably mark
  `not_configured`.
- Provider, source, pipeline, or verification error after claim: durably mark
  `failed` when the registry remains reachable.
- Registry connection failure before a durable identity exists: return a
  structured `failed` result with no operation ID.
- Lease loss: return `conflict`; do not write a terminal state with a stale
  token.

Errors are sanitized and bounded before persistence or JSON output.

### D8 — Make the CLI a typed operation boundary

`index_repo` accepts repository root/slug, exact revision, namespace kind/key,
scope policy, embedder configuration, lease owner/duration, and isolated
full-rebuild intent. It emits one JSON `IndexExecutionResult` on stdout and
uses documented exit codes.

`--full-rebuild` disables compatible-parent reuse only while building or
retrying an unready record and starts a clean attempt staging table and
manifest. A duplicate ready identity remains immutable and returns a no-op; a
caller that must replace ready output changes the pipeline contract/fingerprint
and therefore receives a new identity. The flag never drops canonical,
ancestor, or namespace-wide storage.
Heavy CocoIndex/provider imports remain lazy so help, configuration validation,
and exact-search fallback work without indexing extras.

### D9 — Freeze and tripwire the upstream API

The implementation uses CocoIndex v1 `App`, stable `ContextKey` identities, a
durable App state path, `localfs.walk_dir`, and per-file `mount_each` for source
processing. The thin asyncpg storage adapter owns target lifecycle and fenced
publication. Contexts include repository root, pool, embedder, indexing
parameters, and chunkers.

The verified compatibility window is CocoIndex `>=1.0.13,<1.1.0` with
`cocoindex-code==0.2.37`. A live compatibility test exercises App construction,
vector schema, target behavior, and two-revision incrementality so dependency
updates fail loudly.

Relevant primary documentation:

- https://cocoindex.io/docs/programming_guide/app/
- https://cocoindex.io/docs/programming_guide/context/
- https://cocoindex.io/docs/programming_guide/processing_component/
- https://cocoindex.io/docs/programming_guide/target_state/
- https://cocoindex.io/docs/connectors/localfs/
- https://cocoindex.io/docs/connectors/postgres/
- https://github.com/cocoindex-io/cocoindex-code/blob/v0.2.37/pyproject.toml

## Component Shape

```text
cli.py
  ├── source_proof.py / indexing_policy.py        [light]
  ├── embedding_protocol.py / embedding_config.py [light boundary + lazy adapters]
  └── indexing_runtime.py                        [light lifecycle orchestration]
          ├── SemanticIndexRegistry              [ri-01 + fingerprints/heartbeat]
          └── indexer_pg.run_pipeline()            [heavy CocoIndex adapter]
                    ├── compatible parent rows
                    ├── changed eligible files
                    └── storage_pg fenced publisher/verifier

code_search_indexes
  ├── contract fingerprints
  ├── code_search_index_file_attempts
  └── code_search_index_files                      [published manifest]
          |
          v
code_chunks__i_<index_uuid_hex>

attempt storage: ccs__<index_uuid_hex>__<attempt_count>
```

## Persistence Additions

Migration `030_incremental_code_search_indexes.sql`:

- adds non-secret policy, pipeline, and embedder fingerprints;
- replaces the old natural-key uniqueness constraint with the complete
  fingerprint-aware uniqueness contract;
- adds attempt-scoped and published file manifests with blob digest,
  eligibility, reason, Git entry type, chunk count, and content/chunk digest;
- adds indexes needed for ready compatible-parent lookup.

The migration first adds nullable columns, backfills a documented 64-zero
legacy fingerprint, and only then applies `NOT NULL` and fingerprint checks.
Legacy rows cannot be selected as compatible parents until rebuilt under the
current pipeline contract.

## File and Chunk Identity

The manifest is revision-specific. Eligible entries carry Git entry type,
blob/content digest, a required chunk-set digest (including a canonical
zero-chunk digest), and the path-aware chunk IDs stored in the target. Chunk
identity includes normalized path, chunk ordinal/range, content digest, and
pipeline version so identical text in two files cannot collide. A rename is
treated as delete-plus-add because path participates in identity.

## Operation Result

The JSON result records:

- operation/index ID and storage key when durable identity exists;
- exact source revision and namespace;
- terminal status: `ready`, `not_configured`, `failed`, or `conflict`;
- whether the record was reused and whether main promotion succeeded;
- parent index/revision when incremental;
- eligible, copied, changed, removed, skipped, embedded, and chunk counts;
- sanitized error code/message and durability flag.

## Rollout

1. Apply migration 030 after migration 029.
2. Deploy fingerprint/manifest/heartbeat support unused by production queries.
3. Enable `index_repo` only in explicit development/refresh invocations.
4. Validate local and optional gateway providers.
5. Let `ri-03` migrate reads to ready revision-aware storage.
6. Let the later refresh orchestrator invoke this operation at merge sync
   points; this change does not independently write main.

## Verification Strategy

- Pure tests cover request/result schemas, source proof, fingerprints, policy,
  error mapping, and lifecycle orchestration.
- Structural and optional live Postgres tests cover migration, uniqueness,
  manifests, parent lookup, and heartbeat.
- Adapter tests audit embed calls and verify isolated target completeness.
- Resource-gated E2E tests prove two-revision delta behavior, deletion,
  provenance, HNSW shape, retries, scope/secret exclusion, and namespace
  isolation.
- Strict OpenSpec, work-package, Ruff, Pyright, architecture, and changed-file
  validation run before publication.
