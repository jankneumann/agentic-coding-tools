# Delta Spec: agent-coordinator

## ADDED Requirements

### Requirement: Feature Registry MCP Tools

The coordination MCP server SHALL expose `register_feature`, `deregister_feature`, `get_feature`, `list_active_features`, and `analyze_feature_conflicts` as MCP tools that delegate to `FeatureRegistryService`.

#### Scenario: Register feature via MCP
- WHEN an agent calls `register_feature` with `feature_id`, `resource_claims`, and `title`
- THEN the tool SHALL delegate to `FeatureRegistryService.register()` and return a dict with `success`, `feature_id`, and `action` fields

#### Scenario: Register feature with missing feature_id
- WHEN an agent calls `register_feature` without `feature_id`
- THEN the tool SHALL return an error indicating the required parameter is missing

### Requirement: Feature Registry HTTP Endpoints

The coordination HTTP API SHALL expose feature registry operations as REST endpoints with auth middleware.

#### Scenario: List active features via HTTP
- WHEN a client sends `GET /features/active` with a valid API key
- THEN the API SHALL return a JSON array of active features ordered by merge priority

#### Scenario: Unauthorized feature access
- WHEN a client sends `GET /features/active` without an API key
- THEN the API SHALL return HTTP 401

### Requirement: Merge Queue MCP Tools

The coordination MCP server SHALL expose `enqueue_merge`, `get_merge_queue`, `get_next_merge`, `run_pre_merge_checks`, `mark_merged`, and `remove_from_merge_queue` as MCP tools that delegate to `MergeQueueService`.

#### Scenario: Enqueue feature for merge
- WHEN an agent calls `enqueue_merge` with `feature_id`
- THEN the tool SHALL delegate to `MergeQueueService.enqueue()` and return the queue entry with `feature_id`, `merge_status`, and `merge_priority`

#### Scenario: Enqueue non-existent feature
- WHEN an agent calls `enqueue_merge` with a `feature_id` that is not registered
- THEN the tool SHALL return `success: false` with a descriptive reason

### Requirement: Merge Queue HTTP Endpoints

The coordination HTTP API SHALL expose merge queue operations as REST endpoints.

#### Scenario: Get merge queue via HTTP
- WHEN a client sends `GET /merge-queue` with a valid API key
- THEN the API SHALL return a JSON array of queued features in priority order

#### Scenario: Run pre-merge checks via HTTP
- WHEN a client sends `POST /merge-queue/check/{feature_id}` with a valid API key
- THEN the API SHALL return a JSON object with `passed`, `checks`, `issues`, and `conflicts` fields

### Requirement: CLI Entry Point

The coordinator SHALL provide a `coordination-cli` command-line entry point with subcommand groups for all coordinator capabilities.

#### Scenario: CLI feature list with JSON output
- WHEN a user runs `coordination-cli --json feature list`
- THEN the CLI SHALL print a JSON array of active features to stdout and exit 0

#### Scenario: CLI help text
- WHEN a user runs `coordination-cli --help`
- THEN the CLI SHALL print usage information including all subcommand groups

#### Scenario: CLI merge-queue enqueue
- WHEN a user runs `coordination-cli merge-queue enqueue --feature-id X`
- THEN the CLI SHALL delegate to `MergeQueueService.enqueue()` and print the result

#### Scenario: CLI with database unavailable
- WHEN a user runs any CLI command and the database is unreachable
- THEN the CLI SHALL print an error message to stderr and exit with non-zero code

### Requirement: CLI Coverage

The CLI SHALL expose subcommands for all existing coordinator capabilities: `lock`, `work`, `handoff`, `memory`, `feature`, `merge-queue`, `health`, `guardrails`, `policy`, `audit`, `ports`, `approval`.

#### Scenario: CLI lock acquire
- WHEN a user runs `coordination-cli lock acquire --file-path X --agent-id Y --agent-type Z`
- THEN the CLI SHALL delegate to `LockService.acquire()` and print the result

#### Scenario: CLI unknown subcommand
- WHEN a user runs `coordination-cli unknown-cmd`
- THEN the CLI SHALL print an error and available subcommands to stderr

## MODIFIED Requirements

### Requirement: Bridge Endpoint Probes

The coordination bridge SHALL probe only canonical endpoint paths, removing stale variants.

#### Scenario: Handoff capability detection
- WHEN `detect_coordination()` probes for `CAN_HANDOFF`
- THEN it SHALL probe `POST /handoffs/write` only (not `/handoff/write` or `/handoffs/latest`)

#### Scenario: All capability probes use correct methods
- WHEN `detect_coordination()` probes any capability
- THEN the probe SHALL use the HTTP method matching the actual endpoint (POST for write operations, GET for read operations)

### Requirement: Bridge Capability Flags

The coordination bridge SHALL support `CAN_FEATURE_REGISTRY` and `CAN_MERGE_QUEUE` capability flags in addition to existing flags.

#### Scenario: Feature registry capability detection
- WHEN `detect_coordination()` runs
- THEN it SHALL set `CAN_FEATURE_REGISTRY` based on probing `GET /features/active`

#### Scenario: Merge queue capability detection
- WHEN `detect_coordination()` runs
- THEN it SHALL set `CAN_MERGE_QUEUE` based on probing `GET /merge-queue`
