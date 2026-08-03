## ADDED Requirements

### Requirement: Isolation posture reports filesystem and network as independent dimensions

`EnvironmentProfile.detect()` SHALL return an isolation posture that reports filesystem isolation and network isolation as two independently-valued dimensions, so that a caller can act on one without asserting anything about the other.

A container provides strong filesystem isolation and entirely unrestricted egress. A single boolean cannot express that pairing, and every downstream consumer that needs to say "skip the filesystem sandbox here, still apply the network allowlist" is forced to guess.

#### Scenario: Container posture distinguishes the two dimensions

WHEN `EnvironmentProfile.detect()` runs inside a container that isolates the filesystem but applies no egress restriction
THEN the returned posture SHALL report filesystem isolation as provided
AND SHALL report network isolation as not provided.

#### Scenario: Dimensions are separately addressable

WHEN a caller inspects the returned posture
THEN the filesystem dimension SHALL be readable without consulting the network dimension
AND the network dimension SHALL be readable without consulting the filesystem dimension.

### Requirement: The `isolation_provided` boolean remains a supported compatibility surface

`EnvironmentProfile` SHALL continue to expose `isolation_provided` as a boolean-valued compatibility property whose value is the filesystem-isolation dimension, so that existing callers observe no behavior change.

The precedence ladder and short-circuit semantics already specified for `isolation_provided` continue to apply unchanged when read through this property.

#### Scenario: Existing boolean caller is unaffected

WHEN existing code reads `EnvironmentProfile.detect().isolation_provided`
THEN the value SHALL equal the filesystem-isolation dimension of the posture
AND no call site SHALL require modification to keep its current behavior.

#### Scenario: Worktree entrypoints read the filesystem dimension

WHEN `worktree.py` or `merge_worktrees.py` decides whether to short-circuit a git worktree mutation
THEN the decision SHALL be taken from the filesystem-isolation dimension
AND the observable short-circuit behavior SHALL be identical to the behavior specified for `isolation_provided`.

### Requirement: Detection SHALL identify cloud harnesses that expose no container heuristic

The container-heuristic stage of the detection ladder SHALL recognize cloud harness environments that expose none of `/.dockerenv`, `KUBERNETES_SERVICE_HOST`, or `CODESPACES`, and SHALL report filesystem isolation as provided in those environments.

This closes a demonstrated gap: a cloud harness exposing none of the three existing signals returned `isolation_provided=false, source="default"`, so `worktree.py setup` attempted a real worktree and failed against the already-checked-out branch.

#### Scenario: Cloud harness without the legacy signals is detected

WHEN `EnvironmentProfile.detect()` runs in a cloud harness that exposes none of `/.dockerenv`, `KUBERNETES_SERVICE_HOST`, or `CODESPACES`
AND no explicit `AGENT_EXECUTION_ENV` value is set
AND the coordinator reports nothing for the agent-id
THEN detection SHALL report filesystem isolation as provided
AND SHALL report a source other than `default`.

#### Scenario: Worktree setup no longer fails on the checked-out branch

WHEN `worktree.py setup` runs in that same cloud harness
THEN it SHALL short-circuit the worktree creation
AND SHALL NOT attempt a git worktree against the already-checked-out branch.

#### Scenario: Explicit configuration still outranks the heuristic

WHEN `AGENT_EXECUTION_ENV` is set explicitly
OR the coordinator reports a value for the agent-id
THEN that value SHALL take precedence over the added heuristic signals
AND the documented precedence order SHALL be preserved.
