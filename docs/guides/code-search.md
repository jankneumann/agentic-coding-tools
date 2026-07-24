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
| Revision-aware registry library | `packages/code-search/src/code_search_pkg/registry.py` |

Retrieval is a **read** (design D5): it never locks, enqueues, or triggers indexing, and is
exposed as a tool/endpoint (not an MCP resource) so it works through the `http_proxy` fallback.

## The embedding-endpoint requirement (read this first)

The index and query paths need a reachable embedder. The spike gate discovered that an ephemeral
cloud harness allowlisting only PyPI **cannot reach any model host** (`huggingface.co`,
`download.pytorch.org`, `api.openai.com` all 403), so before enabling this feature in a given
environment, provision **one** of:

1. **Local model** — allowlist `huggingface.co` (+ `download.pytorch.org` for CPU torch) so
   `cocoindex-code[embeddings-local]` can download a SentenceTransformers model once.
2. **Cloud model** — set an embedding API key (`OPENAI_API_KEY` / `VOYAGE_API_KEY` / …) and
   allowlist the provider host, used via LiteLLM.
3. **Pre-baked model** — bake the embedding model into the container image (no runtime download).

The registered embedder per repo is pinned in `code_search_registry` (design D4); a query-time
mismatch is a hard error, never a silently degraded search.

## Indexing (write path)

Indexing is a **write**, run by `index_repo` — never reachable from a query. Trigger it on demand
or from a post-merge hook; never from an agent search.

```bash
# One-time per environment: install the index extra (needs a reachable embedder, see above).
uv pip install -e "packages/code-search[index]"

# Index a repo (upserts code_search_registry, builds code_chunks__<slug> incrementally):
POSTGRES_DSN=... index_repo --repo-root . --repo-slug agentic_coding_tools
```

### Revision-aware registry

`code_search_registry` remains the repository configuration and legacy
compatibility table. `code_search_indexes` is authoritative for each individual
semantic index and records:

- the exact 40- or 64-character Git object ID;
- namespace kind (`main`, `feature`, or `work_package`) and namespace key;
- embedder model and embedding dimension;
- lifecycle status, lease ownership, attempt count, chunk count, and last error;
- retention and deletion state.

The natural key is repository + namespace + exact revision + embedding contract.
Duplicate requests therefore reuse one durable `index_id`. Storage uses the
UUID-derived `storage_key`, never a human-readable branch or work-package name.

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
