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
| Registry migration | `agent-coordinator/database/migrations/028_code_search_registry.sql` |

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

### Post-merge reindex trigger

Because indexing is incremental (only changed files re-embed, design D3), the intended trigger is
a **post-merge hook** on the default branch that runs `index_repo` for the affected repo. A git
`post-merge` hook (or a CI step on merge to `main`) calling the command above keeps the index
fresh at low cost. This is intentionally **not** installed as a live hook by the change — wire it
in the deployment environment where `POSTGRES_DSN` and an embedder are configured, so the hook has
something to talk to. A coordinator-scheduled reindex (WatchdogService) is a deferred alternative
(see `deferred-tasks` in the change) if the hook proves insufficient.

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
