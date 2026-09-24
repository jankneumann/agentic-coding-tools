## ADDED Requirements

### Requirement: Local vendor CLI execution SHALL use one enforcement backend

Every local vendor CLI lifecycle command SHALL pass through one shared process backend. This
includes synchronous execution, asynchronous submission, asynchronous polling, and the autopilot
local-provider harness. Discovery and health probes are control-plane operations and are explicitly
excluded. No cancellation subprocess exists today; any future configured vendor cancellation
command SHALL use the same backend.

#### Scenario: Every vendor lifecycle command uses the backend

WHEN a configured local vendor CLI is submitted, polled, or run synchronously
THEN exactly one shared backend invocation SHALL own process creation
AND a structural guard SHALL reject new direct vendor subprocess sinks.

#### Scenario: Non-sandbox behavior remains compatible

WHEN effective isolation is `none` or `worktree`
THEN the backend SHALL preserve argv, stdin, cwd, timeout, and result behavior
AND no sandbox settings file SHALL be created.

### Requirement: Enforcement SHALL consume the immutable routing decision

The backend SHALL consume the dg-06 routing decision attached to dispatch context and SHALL NOT
call routing again. A standalone caller without routed context SHALL resolve dg-05's exact-lane
fallback once at the adapter boundary and record that provenance.

#### Scenario: Routed execution is not re-resolved

WHEN dispatch context carries a validated routing decision and isolation assignment
THEN the same decision identifier and assignment SHALL appear in the execution audit
AND no router request SHALL occur during rendering, preparation, or process execution.

#### Scenario: Standalone dispatch resolves the exact lane

WHEN a review-panel dispatch has no routed context
THEN effective isolation SHALL be resolved from its exact agent id and dispatch mode
AND an entry-level value SHALL be inherited only when that mode has no override.

### Requirement: Sandbox rendering SHALL be pure and mode-aware

The SRT renderer SHALL be deterministic and side-effect free. Review mode SHALL receive no project
worktree write access. Write-capable modes MAY write only beneath a strictly resolved canonical Git
worktree root. Per-launch vendor state SHALL be isolated from the operator's home. Reads of named
credential locations SHALL be denied except for explicit per-vendor credential inputs pending
dg-08.

#### Scenario: Review is read-only

WHEN a `sandbox` decision is rendered for review
THEN `filesystem.allowWrite` SHALL contain no project path
AND an attempted project write inside or outside the worktree SHALL fail
AND only the backend-owned ephemeral state root and SRT's documented internal paths MAY remain
writable.

#### Scenario: Write-capable work is root-confined

WHEN a `sandbox` decision is rendered for an alternative or quick dispatch
THEN the only project write root SHALL be the canonical worktree root
AND the worktree `.git` pointer and common Git metadata SHALL be denied for writes
AND writes through path or symlink escapes SHALL fail.

#### Scenario: Rendering has no effects

WHEN identical validated context and policy inputs are rendered twice
THEN the policy documents and digests SHALL be identical
AND rendering SHALL NOT write files, spawn processes, or contact a service.

### Requirement: Prepared sandbox commands SHALL own lifecycle and truthful state

The impure preparation layer SHALL own a unique mode-0600 settings file, sanitized child
environment, absolute executable paths, process group, applied/degraded metadata, and cleanup.
The wrapped argv SHALL separate SRT options from the vendor argv with `--`.

#### Scenario: Concurrent launches do not share policy material

WHEN two sandboxed commands are prepared concurrently
THEN each SHALL receive a distinct settings path
AND success, failure, and timeout SHALL remove only that command's material.

#### Scenario: Timeout terminates the complete process tree

WHEN a sandboxed vendor command exceeds its timeout
THEN the backend SHALL terminate its process group, wait, escalate if required, and clean up
AND no child process, listener, settings file, or owned mount artifact SHALL remain.

#### Scenario: Execution metadata is truthful

WHEN a sandbox was requested but not applied
THEN result and audit metadata SHALL report `requested=sandbox` and `applied=false`
AND the dispatch SHALL NOT describe itself as sandboxed.

### Requirement: Degradation SHALL be narrow, durable, and pre-launch

Unsandboxed fallback SHALL occur only for a preflight-proven unsupported platform, absent or
incompatible pinned runtime, or failed platform capability probe. A warning and durable audit or
outbox event SHALL exist before launch. Unsafe roots, malformed policies, and audit persistence
failure SHALL fail closed. No post-launch sandbox failure SHALL be retried unsandboxed.

#### Scenario: Missing runtime degrades visibly

WHEN isolation is `sandbox` and the pinned runtime is absent
THEN a durable `applied=false` event SHALL be recorded before the original command starts
AND the command MAY proceed unsandboxed with a warning.

#### Scenario: Audit failure blocks fail-open

WHEN neither coordinator audit persistence nor the local durable outbox succeeds
THEN the unsandboxed vendor command SHALL NOT start.

#### Scenario: Poll enforcement failure does not abandon remote work

WHEN an asynchronous poll is blocked before its vendor process starts by sandbox enforcement
THEN the collector SHALL retain the remote task and retry until its existing deadline
AND SHALL NOT classify the remote vendor task itself as failed.

#### Scenario: Runtime failure never duplicates work

WHEN SRT has started and exits nonzero or times out
THEN the backend SHALL return that failure
AND SHALL NOT retry the vendor command without the sandbox.

### Requirement: The runtime dependency SHALL be pinned and probed

The supported SRT package version and integrity SHALL be committed. Dispatch SHALL never install a
runtime. Runtime selection SHALL validate package metadata, Node's version floor, platform
dependencies, and a no-op launch before reporting `applied=true`.

#### Scenario: Incompatible runtime is not trusted

WHEN an executable named `srt` is present but its package metadata does not match the pin
THEN the preflight SHALL classify it as incompatible
AND degradation SHALL follow the durable pre-launch path.

#### Scenario: Known network-escape versions are rejected

WHEN the detected package version is older than 0.0.16
THEN it SHALL never be used for network enforcement.
