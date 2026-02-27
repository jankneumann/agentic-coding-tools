## ADDED Requirements

### Requirement: Task Read API

The coordinator SHALL expose a `get_task(task_id)` tool for reading a task's current state including status, result, and input_data without claiming the task.

- The tool SHALL be available as both an MCP tool and an HTTP endpoint (`GET /api/v1/tasks/{task_id}`).
- The response SHALL include `task_id`, `task_type`, `status`, `input_data`, `result`, `error_message`, `priority`, `created_at`, and `completed_at`.
- Reading a task SHALL NOT change its status or ownership.

#### Scenario: Agent reads completed task result
- **WHEN** an agent calls `get_task(task_id)` for a completed task
- **THEN** the coordinator SHALL return the task with `status="completed"` and the full `result` JSON
- **AND** the task's status SHALL remain unchanged

#### Scenario: Agent reads non-existent task
- **WHEN** an agent calls `get_task(task_id)` with an invalid task_id
- **THEN** the coordinator SHALL return an error indicating the task was not found

#### Scenario: Dependency result read during package execution
- **WHEN** a work package agent needs to read its dependency's output
- **THEN** the agent SHALL call `get_task(dependency_task_id)` to fetch the result
- **AND** parse the `result` JSON to extract relevant outputs

### Requirement: Cancellation Convention

The coordinator SHALL support task cancellation via a convention using existing `complete_work` semantics.

- Cancellation SHALL be represented as `complete_work(success=false)` with `error_code="cancelled_by_orchestrator"` in the result payload.
- A helper function `cancel_task_convention(task_id, reason)` SHALL wrap this pattern.

#### Scenario: Orchestrator cancels dependent package
- **WHEN** a package fails and the orchestrator cancels its dependents
- **THEN** the orchestrator SHALL call `cancel_task_convention(task_id, reason)` for each dependent
- **AND** the cancelled task's result SHALL contain `error_code="cancelled_by_orchestrator"` and the reason

#### Scenario: Cancelled task is queryable
- **WHEN** a task has been cancelled via the convention
- **THEN** `get_task(task_id)` SHALL return `status="failed"` with `error_code="cancelled_by_orchestrator"` in the result

### Requirement: Logical Lock Key Namespaces

The coordinator SHALL support logical resource locks using namespace-prefixed keys in the existing `file_locks.file_path` column.

- The following namespace prefixes SHALL be permitted: `api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:`.
- Lock key policy rules SHALL allow these patterns in `acquire_lock`, `release_lock`, and `check_locks`.
- Raw file path locks SHALL continue to work unchanged.
- The coordinator SHALL treat lock keys as opaque resource strings without path semantics.

#### Scenario: Acquire logical lock for API route
- **WHEN** an agent calls `acquire_lock(file_path="api:GET /v1/users")`
- **THEN** the coordinator SHALL acquire the lock using standard lock semantics
- **AND** other agents attempting to lock `api:GET /v1/users` SHALL be blocked

#### Scenario: Acquire pause lock for feature coordination
- **WHEN** an orchestrator calls `acquire_lock(file_path="feature:FEAT-123:pause", reason="contract revision bump")`
- **THEN** the lock SHALL be acquired
- **AND** work package agents checking `check_locks(file_paths=["feature:FEAT-123:pause"])` SHALL see the lock

#### Scenario: Acquire database schema lock
- **WHEN** an agent calls `acquire_lock(file_path="db:schema:users")`
- **THEN** the lock SHALL prevent other agents from acquiring the same schema lock
- **AND** the lock SHALL have standard TTL and expiration behavior

#### Scenario: Mixed file and logical locks
- **WHEN** a work package acquires both file locks (`src/api/users.py`) and logical locks (`api:GET /v1/users`)
- **THEN** both lock types SHALL coexist in the `file_locks` table
- **AND** release of one type SHALL NOT affect the other

### Requirement: Feature Registry

The coordinator SHALL maintain a feature registry for cross-feature resource claim management and conflict detection.

- Features SHALL register with a unique `feature_id` and a set of resource claims using the lock key namespace.
- The registry SHALL support conflict analysis between registered features.
- The registry SHALL produce parallel feasibility assessments: `FULL`, `PARTIAL`, or `SEQUENTIAL`.

#### Scenario: Register feature with resource claims
- **WHEN** an orchestrator registers a feature with resource claims `["api:GET /v1/users", "db:schema:users", "src/api/users.py"]`
- **THEN** the registry SHALL store the feature and its claims
- **AND** the feature SHALL be visible in cross-feature conflict queries

#### Scenario: Conflict analysis between features
- **WHEN** two registered features share resource claims
- **THEN** the registry SHALL identify the overlapping claims
- **AND** produce a feasibility assessment based on overlap severity

#### Scenario: Feature deregistration after completion
- **WHEN** a feature completes (all packages merged, cleanup done)
- **THEN** the orchestrator SHALL deregister the feature from the registry
- **AND** its resource claims SHALL no longer appear in conflict analysis

## MODIFIED Requirements

### Requirement: File Locking (Extended)

The file locking system SHALL be extended to support logical lock key namespaces in addition to repo-relative file paths.

- The `file_path` parameter in `acquire_lock`, `release_lock`, and `check_locks` SHALL accept both repo-relative file paths and namespace-prefixed logical keys.
- Lock key canonicalization rules SHALL be enforced: `api:` keys use uppercase method + single space + normalized path; `db:schema:` keys use lowercase identifiers; `event:` keys use dot-separated lowercase.
- Policy rules SHALL permit the `^(api|db|event|flag|env|contract|feature):.+$` pattern.

#### Scenario: Policy permits logical lock key
- **WHEN** an agent attempts to acquire a lock with key `api:POST /v1/users`
- **THEN** the policy engine SHALL permit the operation
- **AND** the lock SHALL be stored in `file_locks.file_path` as-is

#### Scenario: Policy rejects malformed logical lock key
- **WHEN** an agent attempts to acquire a lock with key `invalid:prefix:key`
- **THEN** the policy engine SHALL reject the operation with `operation_not_permitted`
