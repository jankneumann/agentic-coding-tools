## ADDED Requirements

### Requirement: The isolation vocabulary SHALL be specified once and referenced by both producer and consumer

The isolation vocabulary — `none`, `worktree`, and `sandbox` — SHALL be defined in exactly one location, and both the task router that emits an isolation value and the dispatch layer that consumes it SHALL reference that definition rather than restating the value set.

The router already emits an isolation value and the dispatch layer already consumes one, but no artifact defines what the values mean. Two independent restatements of a vocabulary drift silently, and the first divergence is a dispatch that runs under a posture nobody intended.

#### Scenario: Producer and consumer share one definition

WHEN the task router emits an isolation value
AND the dispatch layer resolves that value
THEN both SHALL derive the accepted value set from the same definition
AND neither SHALL hard-code an independent copy of the vocabulary.

#### Scenario: An unrecognized isolation value is rejected

WHEN a value outside the defined vocabulary reaches the dispatch layer
THEN resolution SHALL fail with an explicit error naming the offending value
AND dispatch SHALL NOT proceed under a silently substituted posture.

### Requirement: Isolation resolution SHALL follow a documented precedence ladder

Effective isolation SHALL be resolved by a documented precedence ladder: the task router when it is reachable, then `get_agent_isolation()` reading `agents.yaml`, then `none`.

This mirrors the precedence structure already established for execution-environment detection, so that one mental model covers both.

#### Scenario: Router value wins when the router is reachable

WHEN the task router is reachable
AND it returns an isolation value for the dispatch
THEN that value SHALL be the effective isolation
AND `agents.yaml` SHALL NOT override it.

#### Scenario: agents.yaml supplies the value when the router is silent

WHEN the task router is reachable but returns no isolation value for the dispatch
THEN `get_agent_isolation()` SHALL supply the effective isolation from `agents.yaml`.

#### Scenario: Coordinator-unreachable yields a decision, not an error

WHEN the coordinator is unreachable
THEN resolution SHALL yield a defined isolation decision rather than raising
AND the decision SHALL fall through to `agents.yaml`, then to `none`
AND the resolved decision SHALL record which rung of the ladder produced it.

### Requirement: Isolation SHALL resolve for an (agent_type, dispatch_mode) pair

Effective isolation SHALL resolve for an `(agent_type, dispatch_mode)` pair rather than for an agent type alone, and `agents.yaml` SHALL be able to express a per-mode override within a single agent entry.

`agents.yaml` already implies per-mode postures — a `review` mode carrying read-only flags beside an `alternative` mode carrying write flags — and today cannot express the difference.

#### Scenario: Review and alternative modes resolve differently under one entry

WHEN one agent entry declares a per-mode isolation override for `review`
AND the same entry declares a different posture for `alternative`
THEN resolving `(agent_type, "review")` SHALL return the review posture
AND resolving `(agent_type, "alternative")` SHALL return the alternative posture.

#### Scenario: Entry-level posture applies when no per-mode override exists

WHEN an agent entry declares an isolation posture with no per-mode override
THEN every dispatch mode for that entry SHALL resolve to the entry-level posture.
