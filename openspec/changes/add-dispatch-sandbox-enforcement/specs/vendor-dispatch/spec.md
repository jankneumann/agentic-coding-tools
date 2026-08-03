## ADDED Requirements

### Requirement: Isolation SHALL be enforced at the dispatch chokepoint

Every dispatched vendor CLI invocation SHALL pass through a single argv-wrapping seam between command construction and process execution, so that one injection site covers every vendor adapter.

`CliVendorAdapter.build_command()` constructs the argv and `subprocess.run()` executes it. Wrapping between those two points is what makes the control total; wrapping inside individual adapters would leave each new vendor unprotected by default.

#### Scenario: Every vendor passes through the same seam

WHEN any vendor CLI is dispatched, synchronously or asynchronously
THEN the constructed argv SHALL be passed through the wrapping seam before execution
AND no adapter SHALL execute an argv that bypassed the seam.

#### Scenario: Non-sandbox postures pass the argv through unchanged

WHEN the resolved isolation decision is not `sandbox`
THEN the seam SHALL return the argv unchanged
AND dispatch behavior SHALL be identical to dispatch before this change.

### Requirement: The sandbox profile renderer SHALL be pure and runtime-seamed

The sandbox profile renderer SHALL be free of side effects, taking a resolved isolation decision together with the coordinator's network policy and the worktree root, and returning a runtime-specific policy document plus an argv wrapper.

Both candidate runtimes are pre-1.0, so the renderer SHALL expose a per-runtime rendering seam such that supporting an additional runtime is an addition rather than a rewrite.

#### Scenario: Rendering performs no side effects

WHEN the renderer is invoked
THEN it SHALL NOT mutate the filesystem, spawn a process, or contact the network
AND the same inputs SHALL produce the same policy document.

#### Scenario: Write scope is confined to the worktree root

WHEN a policy document is rendered for a `sandbox` decision
THEN write access SHALL be scoped to the supplied worktree root
AND read access SHALL be denied for credential paths
AND permitted network destinations SHALL be taken from the coordinator's network policy.

#### Scenario: A second runtime is added without rewriting the renderer

WHEN support for an additional sandbox runtime is introduced
THEN it SHALL be added as an additional rendering function at the existing seam
AND the resolution and wrapping logic SHALL remain unchanged.

### Requirement: The authored network policy SHALL remain the single source of enforced destinations

The coordinator's network policy SHALL remain authored in one place, and enforcement SHALL be a rendering of that policy rather than a second, independently-maintained allowlist.

#### Scenario: Enforced destinations derive from the authored policy

WHEN a sandbox policy document is rendered
THEN its permitted network destinations SHALL be derived from the active coordinator network policy
AND no destination SHALL be introduced that the authored policy does not permit.

### Requirement: Unsupported platforms SHALL degrade openly rather than fail closed

When the sandbox runtime is absent or the host platform is unsupported, dispatch SHALL proceed unsandboxed, SHALL emit a warning, and SHALL write a coordinator audit event recording that isolation was requested but not applied.

Failing closed would break every developer on an unsupported platform for a control that is, by its authors' own account, a defense against confused agents rather than determined ones. Degrading silently would be worse: an operator would believe a containment control was active when it was not.

#### Scenario: Missing runtime degrades with a warning and an audit event

WHEN the resolved isolation decision is `sandbox`
AND the sandbox runtime is not installed or the platform is unsupported
THEN dispatch SHALL proceed without the sandbox
AND a warning SHALL be emitted
AND a coordinator audit event SHALL record that `sandbox` was requested and not applied.

#### Scenario: Degradation is never silent

WHEN dispatch proceeds unsandboxed after a `sandbox` decision
THEN the outcome SHALL be observable from the audit trail alone
AND the dispatch SHALL NOT report itself as sandboxed.
