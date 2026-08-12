## ADDED Requirements

### Requirement: Backend selection SHALL be a pure function of the routing decision

Dispatch SHALL select an execution backend solely from the routing decision's
`(location, isolation)` pair, behind a single `ExecutionBackend` seam
(`run`/`poll`/`cancel` over a `DispatchSpec`). No adapter SHALL contain its own
placement or isolation logic, and the `(local, none|worktree)` backend SHALL be
behaviorally identical to the pre-change subprocess path.

#### Scenario: Legacy path is byte-identical

- **WHEN** the routing decision resolves to `(local, none)` or `(local, worktree)`
- **THEN** the selected backend SHALL execute the same argv, in the same working
  directory, with the same observable behavior as dispatch before this change
- **AND** no sandbox wrapping or credential brokering SHALL be applied.

#### Scenario: Unknown combination refuses loudly

- **WHEN** the routing decision carries a `(location, isolation)` pair with no
  registered backend
- **THEN** dispatch SHALL fail with a structured error before any process or
  sandbox is created
- **AND** a coordinator audit event SHALL record the unresolvable pair
- **AND** dispatch SHALL NOT silently fall back to `(local, none)`.

### Requirement: Child environments SHALL be constructed from an explicit allowlist

Every execution backend — including the local unsandboxed one — SHALL construct the
child process environment from an explicit allowlist, never by inheriting the
parent environment. Rollback of this behavior SHALL be possible only via an explicit
flag whose use is audited.

#### Scenario: Only allowlisted variables reach the child

- **WHEN** any vendor CLI is dispatched through any backend
- **THEN** the child environment SHALL contain only variables named by the
  dispatch spec's env allowlist plus backend-required entries
- **AND** developer credentials not on the allowlist (SSH agent sockets, cloud
  provider variables, unrelated API keys) SHALL be absent from the child.

#### Scenario: Rollback to inheritance is loud, never silent

- **WHEN** the environment allowlist is disabled via its rollback flag
- **THEN** dispatch SHALL proceed with inherited environment
- **AND** a warning SHALL be emitted and a coordinator audit event SHALL record
  that allowlisting was bypassed for the dispatch.

### Requirement: Remote dispatch state SHALL come from the completion ledger alone

For any backend whose process does not run on the dispatching host, dispatch state
SHALL be obtained exclusively from the coordinator completion ledger. Stdout
scraping SHALL NOT be a source of remote dispatch state.

#### Scenario: Cloud dispatch is observable from the ledger

- **WHEN** a dispatch executes on a remote backend
- **THEN** submission, progress, and completion SHALL be readable from the
  completion ledger without access to the remote process's stdout
- **AND** the dispatch result artifact SHALL arrive via the data plane (git push)
  referenced from the ledger record.

#### Scenario: Ledger unreachable parks the dispatch

- **WHEN** the completion ledger is unreachable at remote dispatch submission time
- **THEN** the dispatch SHALL NOT be started on the remote backend
- **AND** the work item SHALL be parked as blocked with an audit event rather than
  dispatched unobservably.
