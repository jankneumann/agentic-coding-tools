# Semantic Code Search

Semantic ("find code by meaning") retrieval for coding agents. The v2 reader
serves one exact Git revision from an immutable, provenance-bearing semantic
index and fails closed to exact source search whenever freshness, authority, or
runtime readiness cannot be proved. The implementation adopts
[`cocoindex-code`](https://github.com/cocoindex-io/cocoindex-code) with a Postgres/pgvector
backend on the coordinator's ParadeDB, exposed through the coordinator's MCP + HTTP surfaces.

See `docs/decisions/code-search.md`, the archived
`openspec/changes/archive/2026-07-20-add-semantic-code-search/` change, and the
active `expose-fail-closed-semantic-code-search` change for the full rationale.

## Status

Behind the `CODE_SEARCH_ENABLED` flag (**default off**). Enabling the flag only
registers/starts the optional query surface; `CAN_CODE_SEARCH` remains false
until the process has a ready provider and a compatible canonical v2 index with
published, addressable storage. Do not enable in production until the
retrieval-quality gate is closed.

## Components

| Piece | Location |
|---|---|
| Vendored pgvector backend (indexer + query) | `packages/code-search/` |
| Coordinator service | `agent-coordinator/src/code_search.py` |
| Principal/work-package authorization | `agent-coordinator/src/code_search_authorization.py` |
| Loop-owned query runtime and readiness | `agent-coordinator/src/code_search_runtime.py` |
| MCP tool `search_code` (local agents) | `agent-coordinator/src/coordination_mcp.py` |
| HTTP `POST /search/code` (cloud agents) | `agent-coordinator/src/coordination_api.py` |
| Immutable Postgres query adapter | `packages/code-search/src/code_search_pkg/query_pg.py` |
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

The query runtime must use the same complete, non-secret embedding contract as
the selected index: provider kind, model, dimension, base URL identity, and
canonical indexing parameters contribute to its fingerprint. A model-name
match alone is insufficient.

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

The v2 reader consumes these ready indexes directly. Exact source search (`rg`,
Git-aware file listing, and direct source reads) remains the mandatory fallback
for every non-ready response.

## Query runtime configuration

The runtime is optional and performs no pool, provider, import, model-download,
or search network work while `CODE_SEARCH_ENABLED` is unset. To enable it,
configure:

| Variable | Purpose |
|---|---|
| `CODE_SEARCH_ENABLED=1` | Start HTTP/direct-MCP query resources and register the MCP tool. Defaults off. |
| `POSTGRES_DSN` | Registry and immutable chunk-storage connection. |
| `CODE_SEARCH_EMBEDDING_PROVIDER` | Explicit `local` or `openai_compatible` query provider. |
| `CODE_SEARCH_EMBEDDING_MODEL` | Exact model ID used by the selected index. |
| `CODE_SEARCH_EMBEDDING_DIMENSION` | Exact positive vector dimension. |
| `CODE_SEARCH_INDEXING_PARAMS_JSON` | Canonical provider/indexing parameters used to reproduce the index fingerprint. |
| `CODE_SEARCH_EMBEDDING_BASE_URL` | Required for an OpenAI-compatible provider when applicable. |
| `CODE_SEARCH_EMBEDDING_CREDENTIAL_REF` | Optional `env:NAME`/configured credential reference; never put the secret itself in fingerprints or logs. |
| `CODE_SEARCH_PRINCIPAL_GRANTS_JSON` | Server-owned repository/namespace read ceilings and deny rules. |

Operational bounds have safe defaults and can be tuned with
`CODE_SEARCH_TIMEOUT_SECONDS`, `CODE_SEARCH_SHUTDOWN_TIMEOUT_SECONDS`,
`CODE_SEARCH_PROVIDER_TTL_SECONDS`, `CODE_SEARCH_INDEX_TTL_SECONDS`,
`CODE_SEARCH_FAILURE_BACKOFF_SECONDS`,
`CODE_SEARCH_MAX_FAILURE_BACKOFF_SECONDS`, `CODE_SEARCH_MAX_CONCURRENCY`, and
`CODE_SEARCH_OVERLOAD_TIMEOUT_SECONDS`. Index readiness refreshes within 15
seconds by default and query outcomes invalidate affected caches immediately.

Each authenticated identity needs exactly one matching server-owned grant. For
example, if `COORDINATION_API_KEY_IDENTITIES` binds an HTTP key to
`bound-agent`, a main-namespace grant can be configured as:

```json
[
  {
    "principal_id": "bound-agent",
    "repo_slug": "agentic_coding_tools",
    "namespace_kind": "main",
    "namespace_key": "main",
    "read_allow": ["agent-coordinator/**", "packages/code-search/**"],
    "deny": ["**/.env*", "**/secrets/**"]
  }
]
```

Direct MCP uses its configured local agent ID as the principal. HTTP-proxy MCP
inherits the HTTP credential boundary and does not create a second query
runtime.

## Querying an exact revision

The v2 request requires `query`, `repo_slug`, a full lowercase 40- or
64-character `source_revision`, a strict namespace, and one authoritative scope
variant. Unknown fields and abbreviated revisions are rejected.

```bash
curl -X POST "$COORD_URL/search/code" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "where are stale index leases fenced",
    "repo_slug": "agentic_coding_tools",
    "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "namespace": {"kind": "main", "key": "main"},
    "scope": {
      "kind": "explicit",
      "read_allow": ["agent-coordinator/**", "packages/code-search/**"],
      "deny": ["**/fixtures/secrets/**"]
    },
    "paths": ["agent-coordinator/**"],
    "languages": ["python"],
    "limit": 5,
    "offset": 0
  }'
```

Local agents call the direct MCP `search_code` tool with the same fields.
HTTP-proxy MCP forwards that shape unchanged. Feature and work-package
namespaces additionally require the exact immutable `index_id`; the reader
never chooses the newest or an arbitrary fingerprint variant:

```json
{
  "namespace": {"kind": "feature", "key": "openspec/example"},
  "index_id": "11111111-1111-4111-8111-111111111111"
}
```

### Scope is authorization

An explicit scope is a caller-requested narrowing of the principal grant, not a
grant of authority. The effective allow set is the intersection of the
server-owned ceiling, caller `read_allow`, and optional `paths`; all principal
and caller deny rules take precedence. Patterns must be normalized,
repository-relative globs. Absolute paths, `./`, dot segments, backslashes,
repeated/trailing separators, controls, empty allow sets, and unknown fields
fail closed before embedding.

A work-package request carries only an immutable reference:

```json
{
  "kind": "work_package",
  "change_id": "expose-fail-closed-semantic-code-search",
  "package_id": "wp-query-service",
  "scope_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

The runtime must resolve that reference through a trusted, repository-bound
declaration registry for the exact source revision. A deployment without that
resolver returns `scope_rejected`; it never trusts caller-supplied work-package
patterns or assumes packaged OpenSpec files are authoritative.

### Provenance and operational states

Only `state=ready` sets `current=true` and may return semantic hits. Its `index`
object records the repository, exact revision, namespace, immutable index ID,
model/dimension, all three fingerprints, and completion time. Every hit repeats
`repo_slug`, `source_revision`, and `index_id`, so copied context retains its
freshness evidence.

Every other state—`revision_mismatch`, `not_indexed`, `not_configured`,
`unavailable`, or `scope_rejected`—has:

```json
{
  "current": false,
  "results": [],
  "fallback": {
    "required": true,
    "strategy": "exact_search",
    "reason": "revision_mismatch"
  }
}
```

Do not use a selected index's provenance as permission to consume hits from a
non-ready response. Run exact search against the requested Git revision and
respect the same effective read scope. Provider mismatch, legacy-only metadata,
missing final storage, stale work-package authority, timeouts, and optional
resource failures never return partial or approximate-current results.

Malformed input is 422 (or MCP validation failure), disabled HTTP search is
404, missing/invalid HTTP credentials are 401, a missing principal grant is
403, and exhausted bounded capacity is 429 with `Retry-After`. Expected
operational degradation uses the typed HTTP 200 envelope so all transports
carry identical fallback evidence.

## Readiness and capability

`GET /search/code/status` is body-aware:

```json
{
  "available": true,
  "state": "ready",
  "reason": "ready",
  "usable_index_count": 2
}
```

`available=true` requires the flag, a process-local initialized runtime, a
ready provider, and at least one compatible canonical v2 index with a published
manifest, positive chunk count, and addressable final table. Disabled,
uninitialized, unconfigured, provider/registry unavailable, legacy-only, and
missing-storage states return `available=false` with zero usable indexes.

Capability discovery sets `CAN_CODE_SEARCH=true` only after parsing a valid
ready body. Route presence, HTTP status alone, MCP tool registration, malformed
or contradictory bodies, and unverifiable MCP-only discovery remain false.
Global coordinator readiness stays healthy when optional semantic resources
fail.

## Compatibility break and rollback

The previous request used `repo` and could omit revision and scope. That shape
is intentionally unsupported: it cannot prove freshness or authorization.
Legacy `code_search_registry` fields and `code_chunks__<repo_slug>` tables are
retained for rollback diagnostics, but v2 never queries them.

Rollback is operational and does not require a data migration: unset
`CODE_SEARCH_ENABLED` (or set it to `0`) and restart the coordinator. HTTP
search then returns 404, direct MCP does not register `search_code`, capability
discovery reports false, and no optional query resources start. Immutable v2
indexes remain available for a later re-enable; exact source search remains the
supported coding-context path throughout rollback.

## Retrieval-quality gate (design D9)

Enabling in production requires closing the spike gate: run
`openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/` against a
reachable embedder and confirm `semantic hit@5 >= 7/10` (see that directory's
`spike-report.md` for the procedure). Until then the flag stays off and nothing
depends on unproven retrieval quality.

## Consuming results in coding jobs (ri-12)

The query service described above is the *producer*. How coding jobs request,
bound, and read its results — the `SEMANTIC_CONTEXT_INJECTION` flag, the five
fallback triggers, the four budget bounds, and the HTTP-only constraint — is
documented in [semantic context injection](semantic-context-injection.md).

Injection is off by default and stays off until the retrieval-quality gate above
*and* the coding-context utility gate (roadmap item ri-13) both pass.
