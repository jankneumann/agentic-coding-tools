# Design: Expose fail-closed semantic code search

## Context

RI02 separated semantic storage by immutable index identity:

```text
code_search_registry.canonical_index_id
                  |
                  v
code_search_indexes.storage_key
                  |
                  v
code_chunks__<storage_key>
```

The current reader bypasses that chain and uses a legacy table derived from a
repository slug. RI03 makes the guarded chain the only query authority.

## Decisions

### D1 — Require exact query identity

Every request supplies:

- a validated repository slug;
- a full lowercase 40- or 64-hex `source_revision`;
- a strict namespace `{kind, key}`;
- a trusted explicit or work-package scope.

`main` requires key `main`. Feature and work-package keys are bounded data, not
SQL identifiers. A non-main namespace additionally requires an exact
`index_id`; its selected record must match the requested repository, namespace,
revision, and provider contract. Missing revision, scope, or required index ID
is malformed input, not permission to guess.

### D2 — Select only guarded ready v2 indexes

Main queries join `code_search_registry.canonical_index_id` to a same-repository
`main`, `ready` `code_search_indexes` row. Feature and work-package queries use
the caller-supplied exact index ID and validate the complete repository,
namespace, revision, model, dimension, policy, pipeline, and embedder
fingerprint boundary. Selection never means “latest ready.”

Rows with legacy zero fingerprints, non-ready lifecycle state, missing
published manifest, missing final table, invalid vector dimension, or
incompatible query provider are unusable. Legacy registry metadata and
repo-slug chunk tables are diagnostic only.

### D3 — Address storage exclusively by validated storage key

`query_pg.py` accepts `storage_key`, validates it with the RI02 identifier
helper, and derives `code_chunks__<storage_key>`. Repository slugs and namespace
keys are never interpolated into SQL.

The query adapter performs one bounded KNN statement with language, path, and
scope predicates. Cosine similarity is documented as `[-1, 1]`; it is not
misrepresented as a probability.

### D4 — Fail closed before embedding

Processing order is:

```text
validate request
  -> resolve trusted scope
  -> select exact usable index
  -> verify revision and provider contract
  -> embed query
  -> query bounded storage
  -> defensively recheck returned paths
```

Revision mismatch, scope failure, and known provider mismatch invoke neither
the embedder nor storage backend. Storage disappearance or a database failure
returns unavailable without partial hits.

### D5 — Use one discriminated result envelope

Operational states are:

- `ready`
- `revision_mismatch`
- `not_indexed`
- `not_configured`
- `unavailable`
- `scope_rejected`

Only `ready` sets `current=true` and may contain results. Every other state sets
`current=false`, returns `results=[]`, and requires
`fallback.strategy=exact_search` with a stable reason code. Malformed requests
remain HTTP 422 / MCP validation errors.

The envelope contains requested identity, selected-index provenance when safe,
scope disposition, and fallback evidence. Each hit repeats repository,
revision, and index ID so extracted context retains provenance.

### D6 — Treat scope as authorization

Caller scope is always a narrowing request, never the trust root. Runtime
configuration supplies a server-authoritative read ceiling and deny set for the
validated process/principal. Explicit scope is intersected with that ceiling
and must contain at least one `read_allow` glob; missing server authority or an
empty effective allow set is rejected.

A work-package reference is resolved through an injected trusted resolver using
change ID, package ID, and scope revision. `scope_revision` is the full Git
object ID of the repository commit containing the declaration and must equal
the query source revision. A deployed runtime without a durable resolver
rejects this variant; it never trusts caller patterns or assumes the Docker
image contains OpenSpec artifacts. RI08 may supply the durable declaration
registry without changing this boundary. Unknown, malformed, unavailable, or
revision-mismatched resolution produces `scope_rejected`.

Patterns must be bounded normalized repository-relative globs: no absolute
paths, backslashes, NULs, or `..` segments. Deny wins. Caller `paths` are
additional filters intersected with scope and can never widen it.

The SQL adapter applies safe path constraints before ranking. A defensive
shared matcher rechecks hits. The shared matcher compiles normalized globs to
parameterized Postgres regular expressions so allow, deny, and caller path
intersection are applied in the ranked SQL statement without interpolating
patterns. A fixed `limit * 4` overfetch is not a completeness contract.

HTTP requires and binds the coordinator API-key principal before scope
resolution. Direct stdio MCP runs under the configured local agent identity;
HTTP-proxy MCP inherits HTTP authentication. An unauthenticated HTTP caller
cannot select an explicit full-repository scope.

### D7 — Match the complete query embedding contract

Startup constructs an explicit RI02 embedding provider. Search requires model,
dimension, and embedder fingerprint compatibility with the selected index.
There is no guessed default model and no implicit model download.

Missing model/dimension/provider configuration is `not_configured`. Provider
readiness or runtime failure is sanitized and reported as unavailable. Query
vectors must contain exactly the selected index dimension. Provider readiness,
embedding, registry selection, storage verification, and KNN execution use
bounded timeouts. A process-local semaphore bounds concurrent embedding/KNN
work and produces a retryable, sanitized overload response.

### D8 — Give each process a loop-owned runtime

HTTP lifespan and direct MCP lifespan use one shared runtime factory but own
their own asyncpg pool/provider instance. HTTP-proxy MCP does not initialize a
second local runtime.

Disabled search performs no pool, provider, import, download, or network work.
Initialization failure leaves the coordinator alive, exposes unavailable
status, and is reset on clean shutdown. A process never creates a pool in one
`asyncio.run` loop and reuses it in another.

### D9 — Make capability discovery body-aware

`GET /search/code/status` returns a typed readiness document. `available=true`
requires:

- feature flag enabled;
- runtime initialized in the current process;
- provider ready;
- at least one compatible canonical v2 index;
- addressable published storage with a positive usable chunk count.

Both HTTP capability detectors parse that body. Route presence, 422, 405, 500,
or MCP tool registration is insufficient. MCP-only discovery remains false
unless a body-aware status invocation is available; a false negative is safer
than advertising unusable code context.

Query-time selection rechecks readiness because startup status can become stale.

Readiness is a bounded state machine rather than a startup snapshot. Provider
readiness uses a configurable TTL and exponential failure backoff; canonical
index/storage readiness uses a short configurable TTL. A successful query,
query failure, provider recovery, canonical change, missing table, or shutdown
invalidates the affected cache immediately. Defaults expose index creation or
deletion within 15 seconds without issuing a remote provider probe on every
status request. Transition tasks are cancelled and awaited during shutdown.

### D10 — Preserve surface parity

The HTTP request model, MCP signature, and proxy payload carry the same fields.
All expected operational outcomes return the D5 envelope. Unexpected internal
exceptions are sanitized into `unavailable`; direct MCP does not leak a
different exception shape.

The legacy default-off feature has no supported current consumers, so RI03
updates the existing endpoint and MCP tool in place instead of maintaining an
unsafe v1 behavior. The contract is published as v2 and the guide documents the
break.

### D11 — Keep RI03 read-only

Status and query operations do not index, promote, repair, enqueue, or mutate
registry state. RI02 owns indexing and promotion. The upstream retry repair
allows a duplicate ready main operation to retry promotion only when the
canonical pointer is unset or still equals its recorded parent; it never
replaces an unrelated canonical index.

### D12 — Observe states without observing source

The runtime records bounded counters and latency for initialization, status,
query state, fallback reason, provider failure class, and scope rejection.
Structured logs contain repository slug, requested revision, index ID when
selected, state, and sanitized reason codes. Query text, source chunks, scope
patterns, credentials, DSNs, and provider response bodies are never logged.
Status transitions are visible without changing global coordinator readiness.

### D13 — Install the shared query package explicitly

`code-search-pkg` is a declared non-editable monorepo path dependency of the
coordinator. Its asyncpg compatibility range is widened to the tested
coordinator version, both lockfiles are regenerated, and the Docker builder
installs the wheel before the runtime stage. The runtime image no longer relies
on copying package source beside site-packages.

An import smoke test runs from a clean coordinator environment, and the Docker
import contract proves the installed package exposes the light query,
identifier, registry-model, and embedding-contract modules. Heavy CocoIndex and
local-model imports remain lazy and absent from the coordinator startup path.

## Component Shape

```text
HTTP lifespan ─┐
               ├─ code_search_runtime factory ─ pool + provider + service
MCP lifespan ──┘
                         |
                         v
                  CodeSearchService
                  ├─ trusted scope resolver
                  ├─ exact index selector
                  ├─ query embedder
                  └─ storage-key KNN adapter

GET /search/code/status ──> runtime readiness ──> CAN_CODE_SEARCH
POST /search/code        ──> discriminated query envelope
MCP search_code          ──> same envelope (direct or HTTP proxy)
```

## Failure Semantics

| Condition | State | Semantic hits | Fallback |
|---|---|---:|---|
| Exact compatible index and scope | `ready` | allowed | not required |
| Requested revision differs | `revision_mismatch` | 0 | exact search |
| No v2 index / legacy only | `not_indexed` | 0 | exact search |
| Missing provider contract | `not_configured` | 0 | exact search |
| DB/provider/table failure | `unavailable` | 0 | exact search |
| Invalid or unresolved scope | `scope_rejected` | 0 | exact search |

## Security Notes

- Source content is sensitive even when repository metadata is public.
- Server-resolved scope is authoritative; caller-supplied filters only narrow.
- Error details never include DSNs, credentials, provider responses, SQL, or
  file content.
- Status exposes counts and stable reason codes, not internal storage names or
  secrets.

## Verification Strategy

- Pure contract and model tests cover impossible envelope states.
- Fake registry/provider/storage tests prove rejection occurs before embedding.
- Query adapter tests prove storage-key-only SQL and bounded filtering.
- HTTP, direct MCP, and proxy tests compare serialized envelopes.
- Capability tests cover disabled, 404, 422, 500, malformed, false-body, and
  true-body probes.
- Authorization, timeout, and overload tests prove expensive work is neither
  anonymous nor unbounded.
- Resource-gated Postgres tests seed migration 030 plus a canonical final table
  and prove happy, mismatch, missing-table, and legacy-only outcomes.
- Full validation distinguishes mandatory deterministic tests from deferred
  Postgres/embedder evidence.

## Intentional Trade-offs

- A strict request break is accepted because the feature is default-off and the
  previous implementation cannot query RI02 output safely.
- MCP-only capability discovery may under-report availability when it cannot
  invoke status; it never over-reports based on tool presence.
- Optional semantic infrastructure never blocks global coordinator readiness,
  but callers always receive explicit fallback evidence.
