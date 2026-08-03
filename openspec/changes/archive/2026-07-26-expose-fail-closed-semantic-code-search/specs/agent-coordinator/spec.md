## MODIFIED Requirements

### Requirement: Code Search Dual-Surface Exposure

The coordinator SHALL expose semantic code retrieval through one typed service
on the direct MCP `search_code` tool and authenticated `POST /search/code` HTTP
endpoint. Both surfaces SHALL require query, repository slug, exact source
revision, namespace, and authoritative scope; non-main namespaces additionally
require an exact index ID. Limit, offset, language, and caller path filters are
bounded optional narrowings. Direct MCP and HTTP-proxy MCP SHALL serialize the
same discriminated operational envelope as HTTP. Query embedding SHALL happen
inside the service after authorization, scope, revision, index, and provider
validation.

#### Scenario: Exact ready request has three-surface parity

- **WHEN** the same valid request is issued through HTTP, direct MCP, and
  HTTP-proxy MCP against the same ready index
- **THEN** all surfaces SHALL return the same state and provenance-rich results

#### Scenario: Fail-closed request has three-surface parity

- **WHEN** the same request encounters revision mismatch, scope rejection, or
  optional-resource unavailability
- **THEN** all surfaces SHALL return the same non-ready envelope with zero hits
  and exact-search fallback

### Requirement: Code Search Is a Direct Read

`search_code` and `code_search_status` SHALL NOT acquire locks, enqueue work,
trigger indexing, promote indexes, repair storage, or mutate coordination
state. A query SHALL read only a guarded ready v2 index addressed by validated
storage key. Database, provider, timeout, overload, and storage failures SHALL
return a sanitized non-ready envelope or bounded overload response without
partial hits or a hang beyond configured deadlines.

#### Scenario: Search never mutates or repairs

- **WHEN** concurrent code-search queries and status checks execute
- **THEN** registry, chunk, lock, queue, and audit-relevant coordination state
  SHALL remain unchanged
- **AND** no index, table, or promotion operation SHALL be created

#### Scenario: Optional outage preserves coordinator readiness

- **WHEN** code-search Postgres or embedding resources are unreachable
- **THEN** global coordinator startup and readiness SHALL continue
- **AND** code-search status and queries SHALL report sanitized unavailability
  within configured deadlines

### Requirement: Code Search Feature Flag

Code-search runtime initialization and MCP tool registration SHALL be gated by
`CODE_SEARCH_ENABLED` (default off). While disabled, no query pool, provider,
model download, migration-specific query, or network request SHALL occur; the
MCP tool SHALL not be listed and `POST /search/code` SHALL return 404.
`CAN_CODE_SEARCH` SHALL be true only when body-aware status proves an initialized
provider and at least one usable canonical v2 index. Route or tool presence
alone MUST NOT establish capability.

#### Scenario: Disabled flag performs no optional work

- **WHEN** `CODE_SEARCH_ENABLED` is unset
- **THEN** the MCP search tool SHALL not appear and HTTP search SHALL return 404
- **AND** initialization MUST NOT touch optional code-search resources

#### Scenario: Dynamic status controls capability

- **WHEN** the status body is false, contradictory, malformed, unavailable, or
  unverifiable over MCP-only discovery
- **THEN** `CAN_CODE_SEARCH` MUST be false
- **AND** it SHALL become true only after a valid `available=true` ready body
