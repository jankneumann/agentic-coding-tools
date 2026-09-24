## ADDED Requirements

### Requirement: Semantic Code Search Bridge Helper

The bridge SHALL expose a `try_code_search` helper so non-MCP callers can
execute a semantic code-search query over HTTP. The helper SHALL obey the
uniform helper envelope: it SHALL NOT raise on any transport, authorization, or
service failure, and SHALL report failure through the structured result.

<!-- Scenario ID: coordination-bridge.code-search-helper-success -->
#### Scenario: A ready response is returned unmodified

- **WHEN** the coordinator answers a semantic code-search request successfully
- **THEN** the helper SHALL return the coordinator's discriminated response
  unmodified inside the standard envelope
- **AND** it SHALL NOT drop, reorder, re-rank, or filter the returned hits

<!-- Scenario ID: coordination-bridge.code-search-helper-capability-gate -->
#### Scenario: An absent capability skips the call

- **WHEN** capability detection reports that code search is unavailable
- **THEN** the helper SHALL return a skipped result naming the absent capability
- **AND** it SHALL NOT issue an HTTP request

<!-- Scenario ID: coordination-bridge.code-search-helper-failures -->
#### Scenario: Failure causes are distinguishable

- **WHEN** the request fails with an unreachable host, a rejected credential, an
  unmounted route, a malformed request, an overload signal, or a server error
- **THEN** the helper SHALL return a failed result whose reason distinguishes
  those causes from one another
- **AND** it SHALL NOT raise

### Requirement: MCP-Only Transport Reports No Code Search

Capability detection SHALL continue to report code search as unavailable
whenever availability cannot be proven from a status response. Detecting a
connected coordination MCP server SHALL NOT by itself set the code-search
capability flag.

<!-- Scenario ID: coordination-bridge.code-search-mcp-only -->
#### Scenario: MCP transport leaves code search false

- **WHEN** HTTP detection fails and a connected coordination MCP server is
  detected
- **THEN** the code-search capability flag SHALL remain false
- **AND** the other capability flags SHALL be unaffected

<!-- Scenario ID: coordination-bridge.code-search-mcp-only-consumers -->
#### Scenario: Consumers degrade rather than guess

- **WHEN** a coding job assembles context under a non-HTTP transport
- **THEN** semantic retrieval SHALL report an unavailable fallback naming the
  transport as the cause
- **AND** it SHALL NOT attempt a semantic query over that transport
