## ADDED Requirements

### Requirement: Strict code-search request identity

The coordinator MUST accept semantic code-search requests only when they contain
a bounded query, validated repository slug, exact full source revision, strict
namespace, and authoritative scope.

#### Scenario: code-search.1 — Exact identity is accepted

- **WHEN** a caller supplies a valid query, repository slug, full source
  revision, namespace, and scope
- **THEN** the coordinator SHALL validate the complete request before accessing
  an embedder or index

#### Scenario: code-search.2 — Missing exact identity is rejected

- **WHEN** a request omits its revision or scope, uses an abbreviated revision,
  omits the index ID required for a non-main namespace, mixes scope variants,
  or contains unknown fields
- **THEN** the coordinator MUST reject it as malformed
- **AND** it MUST NOT access an embedder or semantic storage

### Requirement: Discriminated fail-closed outcomes

The coordinator SHALL return a discriminated operational envelope whose state
is `ready`, `revision_mismatch`, `not_indexed`, `not_configured`, `unavailable`,
or `scope_rejected`.

#### Scenario: code-search.3 — Ready outcome contains current results

- **WHEN** the exact requested index and scope are usable
- **THEN** the response SHALL set `state=ready` and `current=true`
- **AND** it MAY contain allowed semantic hits
- **AND** exact-search fallback SHALL not be required

#### Scenario: code-search.4 — Non-ready outcome requires fallback

- **WHEN** the state is not `ready`
- **THEN** the response MUST set `current=false`
- **AND** it MUST return zero semantic hits
- **AND** it SHALL require an `exact_search` fallback with a stable reason code

### Requirement: Revision-aware immutable query storage

The coordinator MUST query only an RI02 ready index selected through guarded v2
registry state and addressed by its validated immutable storage key.

#### Scenario: code-search.5 — Canonical exact main index is queried

- **WHEN** the canonical pointer identifies a same-repository ready main index
  whose revision and provider contract match the request
- **THEN** the query adapter SHALL derive the final table from the selected
  index storage key
- **AND** every result SHALL identify the repository, source revision, and
  index ID

#### Scenario: code-search.6 — Revision mismatch returns no stale hits

- **WHEN** the canonical index revision differs from the requested revision
- **THEN** the response SHALL use `revision_mismatch`
- **AND** it MUST return no results as current
- **AND** neither embedding nor KNN search SHALL run

#### Scenario: code-search.7 — Legacy storage is never authoritative

- **WHEN** only a legacy registry row or `code_chunks__<repo_slug>` table exists
- **THEN** the response SHALL use `not_indexed`
- **AND** the legacy table MUST NOT be queried

#### Scenario: code-search.8 — Unusable storage degrades explicitly

- **WHEN** the selected row is non-ready, has legacy fingerprints, lacks
  published storage, has a missing final table, or is provider-incompatible
- **THEN** the response SHALL be non-ready with exact-search fallback
- **AND** it MUST NOT return partial or stale hits

#### Scenario: code-search.9 — Non-main selection is exact

- **WHEN** a feature or work-package request supplies an index ID
- **THEN** the selected record MUST match that ID, repository, namespace,
  revision, and complete provider contract
- **AND** the coordinator MUST NOT choose another ready fingerprint variant

### Requirement: Authoritative read scope

Semantic code search MUST enforce a trusted read scope before embedding and
storage access, with deny rules taking precedence and caller filters only
narrowing authority.

#### Scenario: code-search.10 — Scope resolution fails closed

- **WHEN** explicit allow rules are empty or malformed, a work-package scope
  cannot be resolved, or its scope revision is stale
- **THEN** the response SHALL use `scope_rejected`
- **AND** it MUST return no semantic hits
- **AND** it MUST NOT degrade to unrestricted search

#### Scenario: code-search.11 — Deny overrides allow

- **WHEN** a path matches both an allow rule and a deny rule
- **THEN** the path MUST be excluded before it can appear in semantic results

### Requirement: Truthful dynamic capability

Capability discovery SHALL report `CAN_CODE_SEARCH=true` only when code search
is enabled, initialized, provider-ready, and backed by at least one compatible
usable canonical v2 index.

#### Scenario: code-search.12 — Body-aware status proves availability

- **WHEN** the status endpoint returns a valid document with
  `available=true`
- **THEN** HTTP capability discovery SHALL report `CAN_CODE_SEARCH=true`

#### Scenario: code-search.13 — Presence alone is insufficient

- **WHEN** the route or MCP tool exists but status is false, malformed,
  unavailable, or cannot be invoked
- **THEN** capability discovery MUST report `CAN_CODE_SEARCH=false`

### Requirement: Loop-owned optional runtime

HTTP and direct MCP SHALL own query runtime resources in their serving event
loop, while optional search failure MUST NOT fail global coordinator startup.

#### Scenario: code-search.14 — Disabled startup performs no search work

- **WHEN** code search is disabled
- **THEN** startup MUST NOT create a search pool, load a provider, download a
  model, or make a search-related network request

#### Scenario: code-search.15 — Optional resource failure is isolated

- **WHEN** Postgres, migration, provider, or storage readiness fails
- **THEN** the coordinator SHALL remain available
- **AND** code-search status SHALL be unavailable with a sanitized reason

#### Scenario: code-search.16 — Shutdown releases loop-owned resources

- **WHEN** the HTTP or direct-MCP process shuts down
- **THEN** it MUST close its search pool/provider resources
- **AND** it SHALL clear process-local availability state

### Requirement: HTTP, MCP, and proxy parity

HTTP, direct MCP, and HTTP-proxy MCP MUST carry the same v2 search inputs and
serialize the same expected operational outcomes.

#### Scenario: code-search.17 — Ready response parity

- **WHEN** the same valid exact-revision request is served through all three
  surfaces
- **THEN** each surface SHALL return the same ready envelope and provenance

#### Scenario: code-search.18 — Degraded response parity

- **WHEN** the same request encounters a revision mismatch or unavailable
  optional resource
- **THEN** each surface MUST return the same non-ready envelope
- **AND** unexpected internal details MUST be sanitized

### Requirement: Authenticated bounded query execution

HTTP semantic search MUST require a valid coordinator principal, and all
expensive provider and database work MUST be bounded.

#### Scenario: code-search.19 — Anonymous HTTP search is rejected

- **WHEN** an HTTP caller supplies no valid coordinator credential
- **THEN** the coordinator SHALL return 401 before scope, embedding, or database
  query work

#### Scenario: code-search.20 — Timeout or overload degrades safely

- **WHEN** a configured timeout expires or the bounded query concurrency is
  exhausted
- **THEN** the coordinator MUST return a sanitized retryable outcome
- **AND** it MUST NOT return partial hits

### Requirement: Privacy-preserving code-search observability

The coordinator SHALL expose state and latency evidence without logging query
text, source content, credentials, DSNs, scope patterns, or provider bodies.

#### Scenario: code-search.21 — Operational state is observable

- **WHEN** initialization, readiness, a query, or fallback completes
- **THEN** counters and structured logs SHALL identify the state and sanitized
  reason
- **AND** sensitive request and result content MUST be absent

## MODIFIED Requirements

### Requirement: Repo Registry with Embedder Consistency

The system SHALL use revision-aware `code_search_indexes` records as the query
authority. Query-time embedding MUST match the selected index's model,
dimension, and nonlegacy embedder fingerprint. A mismatch SHALL return a
structured non-ready response with zero results and exact-search fallback; it
MUST NOT query semantic storage or expose credential/configuration details.
Legacy `code_search_registry` model fields remain compatibility metadata and
MUST NOT independently establish query compatibility.

#### Scenario: Complete embedder mismatch fails closed

- **WHEN** a selected index's model, dimension, or embedder fingerprint differs
  from the initialized query provider
- **THEN** search SHALL return a non-ready state with zero results
- **AND** neither the query embedder nor KNN storage SHALL run

#### Scenario: Legacy registry metadata is insufficient

- **WHEN** a repository has only legacy model metadata and no compatible ready
  v2 index
- **THEN** search SHALL return `not_indexed`
- **AND** it MUST NOT read a legacy repo-slug chunk table

### Requirement: Semantic Retrieval Query

The system SHALL accept a bounded natural-language query with a validated
repository slug, exact full source revision, strict namespace/index selector,
and authoritative scope, returning allowed chunks ranked by cosine similarity. Every response
and hit MUST retain repository, source revision, and index provenance. Language,
caller path, allow, and deny predicates MUST be applied in the same
parameterized database statement as nearest-neighbor ranking. Cosine similarity
SHALL be represented in its mathematical range `[-1, 1]`.

#### Scenario: Exact filtered search executes as one statement

- **WHEN** a ready request includes language, caller path, allow, and deny
  filters
- **THEN** returned hits SHALL satisfy their intersection and be ranked by
  cosine similarity
- **AND** the service SHALL issue one parameterized ranking statement against
  the validated storage-key table

#### Scenario: Mismatched retrieval never returns approximate current context

- **WHEN** exact revision, namespace, provider, storage, or scope validation
  fails
- **THEN** semantic results MUST be empty
- **AND** the response SHALL require exact-search fallback

### Requirement: Scope-Aware Result Filtering

The service SHALL require an authenticated or configured local principal whose
server-owned code-search grant establishes repository, namespace, read ceiling,
and deny rules. Caller explicit filters MAY only narrow that grant. A
work-package reference MUST resolve through an immutable, repository-bound
authority for the exact source revision. Missing grants, missing resolvers,
stale/cross-repository references, empty effective allow sets, and malformed
patterns MUST fail closed before embedding or storage access.

#### Scenario: Caller scope cannot widen server authority

- **WHEN** a caller requests `read_allow=["**"]` but the principal grant allows
  only `agent-coordinator/**`
- **THEN** the effective scope SHALL remain within `agent-coordinator/**`
- **AND** no other path may be embedded, queried, logged, or returned

#### Scenario: Stale work-package authority is rejected

- **WHEN** a work-package scope record belongs to another repository or source
  revision
- **THEN** the response SHALL use `scope_rejected`
- **AND** semantic work MUST NOT run
