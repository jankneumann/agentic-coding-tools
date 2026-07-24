# Semantic Code Search

Semantic ("find code by meaning") retrieval for coding agents, added by the
`add-semantic-code-search` OpenSpec change. Adopts
[`cocoindex-code`](https://github.com/cocoindex-io/cocoindex-code) with a Postgres/pgvector
backend on the coordinator's ParadeDB, exposed through the coordinator's MCP + HTTP surfaces.

See the decision memo and design at `openspec/changes/add-semantic-code-search/` for the full
rationale and the D1–D10 decisions referenced below.

## Status

Behind the `CODE_SEARCH_ENABLED` flag (**default off**, design D10). Do not enable in production
until the retrieval-quality gate (design D9) is closed — see "Retrieval-quality gate" below.

## Components

| Piece | Location |
|---|---|
| Vendored pgvector backend (indexer + query) | `packages/code-search/` |
| Coordinator service | `agent-coordinator/src/code_search.py` |
| MCP tool `search_code` (local agents) | `agent-coordinator/src/coordination_mcp.py` |
| HTTP `POST /search/code` (cloud agents) | `agent-coordinator/src/coordination_api.py` |
| Repository registry migration | `agent-coordinator/database/migrations/028_code_search_registry.sql` |
| Revision-aware index registry migration | `agent-coordinator/database/migrations/029_revision_aware_code_search_indexes.sql` |
| Incremental manifests and repository identity | `agent-coordinator/database/migrations/030_incremental_code_search_indexes.sql` |
| Revision-aware registry library | `packages/code-search/src/code_search_pkg/registry.py` |

Retrieval is a **read** (design D5): it never locks, enqueues, or triggers indexing, and is
exposed as a tool/endpoint (not an MCP resource) so it works through the `http_proxy` fallback.

## Embedding configuration

Semantic indexing is optional and never guesses a provider, model, or vector
dimension. Configure one of:

1. **Local** — an explicit SentenceTransformers model already present or
   reachable by the indexing environment.
2. **OpenAI-compatible** — an explicit base URL, credential reference
   (`env:NAME` or a configured `vault:path` resolver), model, and dimension.
   The coordinator LLM gateway uses this ordinary data-plane boundary and is
   opt-in; the indexer imports no coordinator control-plane code.

Credentials are resolved transiently and excluded from fingerprints, logs, and
operation results. Missing model/dimension or Postgres configuration returns an
ephemeral `not_configured` result. A configured but unreachable registry
returns ephemeral `failed` with `registry_unavailable`. Once a durable operation is claimed, a
missing package, credential, model, or endpoint is recorded as durable
`not_configured`; provider or response failures are recorded as `failed`.

## Indexing (write path)

Indexing is a **write**, run by `index_repo` — never reachable from a query. Trigger it on demand
or from a post-merge hook; never from an agent search.

```bash
# One-time per environment: install the index extra (needs a reachable embedder, see above).
uv pip install -e "packages/code-search[index]"

# Index one exact clean revision with a local provider:
POSTGRES_DSN=... index_repo \
  --repo-root . \
  --repo-slug agentic_coding_tools \
  --source-revision "$(git rev-parse HEAD)" \
  --namespace-kind main \
  --namespace-key main \
  --provider local \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2 \
  --embedding-dimension 384 \
  --read-allow 'packages/**' \
  --deny '**/fixtures/secrets/**' \
  --lease-owner manual-refresh
```

`index_repo` writes one compact JSON result and exits `0` for `ready`, `2` for
`not_configured`, `3` for a concurrent-operation conflict, and `1` for failure.
`--scope-file` accepts the same include, exclude, read-allow, deny,
gitignore, and local-scanner policy as the repeatable CLI flags.

### Revision-aware registry

`code_search_registry` remains the repository configuration and legacy
compatibility table. `code_search_indexes` is authoritative for each individual
semantic index and records:

- the exact 40- or 64-character Git object ID;
- namespace kind (`main`, `feature`, or `work_package`) and namespace key;
- embedder model and embedding dimension;
- deterministic policy, pipeline, and non-secret embedder fingerprints;
- lifecycle status, lease ownership, attempt count, chunk count, and last error;
- a compatible parent and attempt/published file manifests;
- retention and deletion state.

The natural key is repository + namespace + exact revision + all three
fingerprints. Duplicate ready requests reuse one durable `index_id` before any
source read, embedding call, or storage mutation. A scope, chunking, adapter,
model, dimension, or indexing-parameter change creates a distinct identity.
Storage uses the UUID-derived `storage_key`, never a human-readable branch or
work-package name.

The repository slug is permanently bound to one canonical worktree root and
Git common-directory fingerprint. Indexing accepts only a clean materialized
worktree whose HEAD is the requested full 40- or 64-character object ID, and
repeats that proof immediately before publication.

### Incremental storage and scope safety

For a compatible ready Git ancestor, the new attempt copies only unchanged
eligible paths proven by the parent manifest. Added or changed files alone are
chunked and embedded; deleted and newly ineligible files are omitted. A rename
is delete-plus-add because paths participate in chunk identity.

Every retry receives a fresh `ccs__<index-id>__<attempt>` table. Per-file writes
are transactional. Schema, vector dimension, HNSW index, row counts, and full
manifest coverage are verified before the current lease holder atomically
renames the table and publishes the manifest. A stale worker remains confined
to its abandoned attempt table.

Eligibility is evaluated before content is read:

```text
tracked exact revision
  ∩ include
  − exclude
  − root/nested .gitignore
  ∩ read_allow
  − deny
  − secret/credential paths
  − generated/dependency trees
  − symlinks and path escapes
```

Deny rules win. Eligible Git blob bytes pass through the bounded local secret
scanner before they can reach an embedder. Scanner findings, errors, and
timeouts fail closed with sanitized evidence.

Workers claim an index through an expiring lease. Only the current lease holder
may complete or fail an attempt, so a late worker cannot overwrite a newer result.
A ready main index becomes canonical only through compare-and-swap promotion, and
the database rejects feature, work-package, cross-repository, or non-ready
candidates.

Garbage collection is explicit and conservative. It considers only expired
feature/work-package records, excludes active leases and canonical/main indexes,
and marks a record deleted only after isolated storage deletion succeeds. The
injected storage deleter must be idempotent: an expired `deleting` lease is
reclaimed after a worker crash, including a crash after storage removal but
before registry tombstoning. A storage failure is retained as a retryable
registry failure.

Migration 029 is additive: existing `code_chunks__<repo_slug>` tables and the
disabled-by-default query path continue to work. Their repo-level freshness fields
are compatibility data, not proof that results match a requested revision. The
incremental-indexing and fail-closed-query roadmap items migrate those consumers
to `code_search_indexes`.

Migration 030 adds contract fingerprints, immutable repository identity,
attempt/final manifests, parent guards, and lease renewal. `--full-rebuild`
disables parent reuse only for an unready leased attempt. It never replaces an
already ready identity; changing output requires changing the pipeline
fingerprint.

### Main convergence trigger

Because indexing is incremental (only changed files re-embed, design D3), the intended trigger is
the shared project-context convergence invoked by `merge-pull-requests` after the
deterministic context commit reaches `main`. That flow enqueues indexing for the
final pushed main SHA and records an explicit `not-configured` or degraded result
when Postgres or an embedder is unavailable.

Do not add an independent Git `post-merge` writer. Feature and work-package
checkpoints use revision-isolated namespaces and cannot mutate the canonical main
pointer. Until the later convergence roadmap item lands, indexing remains a
manual/deployment operation that requires `POSTGRES_DSN` and a reachable embedder.

This change completes the write operation only. The follow-up
`expose-fail-closed-semantic-code-search` change (`ri-03`) moves reads to ready
revision-aware storage. Until that lands, callers must retain exact search
(`rg` and direct source reads) as the authoritative fallback.

## Querying (read path)

```bash
# HTTP (cloud agents) — 404 while CODE_SEARCH_ENABLED is off:
curl -XPOST "$COORD_URL/search/code" -H "Authorization: Bearer $KEY" \
  -d '{"query":"how are file locks released after a crash","repo":"agentic_coding_tools","limit":5}'
```

Local agents call the `search_code` MCP tool with the same arguments; both delegate to the one
service, so payloads are identical. An optional `scope` (`{work_package}` or `{read_allow, deny}`
globs) restricts results to files the caller is allowed to read (design D7).

## Retrieval-quality gate (design D9)

Enabling in production requires closing the spike gate: run
`openspec/changes/add-semantic-code-search/eval/` against a reachable embedder and confirm
`semantic hit@5 >= 7/10` (see `eval/spike-report.md` for the procedure). Until then the flag stays
off and nothing depends on unproven retrieval quality.
