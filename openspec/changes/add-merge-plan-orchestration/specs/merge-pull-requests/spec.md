# merge-pull-requests — Delta Spec

## ADDED Requirements

### Requirement: Durable Merge Plan Artifact

The skill SHALL be able to emit a durable merge plan from the analysis round so triage
state survives a context clear and can seed fresh-context execution. The plan SHALL be
written as machine-readable `merge-plan.json` conforming to
`contracts/schemas/merge-plan.schema.json`, accompanied by a rendered human-readable
`merge-plan.md` projection. For each PR node the plan SHALL record: PR number, origin
classification, staleness, CI/gate state, unresolved-comment count, merge strategy, an
`auto_executable` flag, optional `gate` markers, dependency edges to other nodes, and a
mutable `outcome` (`pending`, `merged`, `closed`, `deferred`, or `failed`).

#### Scenario: Analysis round emits a durable plan

- **WHEN** the operator runs the analysis round with plan output enabled
- **THEN** the skill SHALL write `merge-plan.json` validating against the plan schema
- **AND** SHALL render a `merge-plan.md` projection of the same state
- **AND** each open PR SHALL appear as a node with `outcome` initialised to `pending`

#### Scenario: Dependency edges are derived from file overlap and base branch

- **WHEN** two PR nodes modify one or more of the same files, or one targets the other's branch
- **THEN** the plan SHALL record a dependency edge between them
- **AND** the rendered `merge-plan.md` SHALL surface conflicting-pair edges to the operator

### Requirement: Plan-Driven Single-PR Execution

The skill SHALL support executing a single PR from a plan with fresh context, decoupled
from the analysis round. Invoked as `--execute <plan> --pr <n>`, execution SHALL re-check
live PR and CI state (never trusting the snapshot alone), refresh the branch if stale, run
vendor review when eligible, merge using the node's strategy subject to gate rules, and
write the resulting `outcome` back to the plan. After a successful merge, execution SHALL
mark every downstream node depending on the merged node for re-validation before it is
executed. Execution SHALL invoke helper scripts via canonical `skills/...` paths and SHALL
NOT rely on the `.claude/skills` runtime mirror.

#### Scenario: Executing one node updates the plan and flags downstream nodes

- **WHEN** the operator runs `--execute <plan> --pr <n>` and the merge succeeds
- **THEN** the node's `outcome` SHALL be set to `merged` in the plan
- **AND** every node with a dependency edge to `n` SHALL be flagged for re-validation
- **AND** a subsequent execution of a flagged node SHALL recompute its mergeability before merging

#### Scenario: Gated node halts for human decision

- **WHEN** a node is marked `auto_executable: false` or carries a `requires_human_approval` gate
- **THEN** execution SHALL stop before merging and surface the gate to the operator
- **AND** SHALL NOT merge the node without explicit operator approval

#### Scenario: Execution respects the security-check backstop

- **WHEN** a node would be merged past a failing required security check
- **THEN** execution SHALL defer to the auto-mode classifier and SHALL NOT bypass it automatically
- **AND** the node `outcome` SHALL remain `pending` with the blocking reason recorded

### Requirement: Merge Plan Living Amendment

Plan-driven execution SHALL be able to amend the plan when it discovers a blocker that must
be resolved before other nodes can proceed. An amendment SHALL insert a new prerequisite
node and add dependency edges from the affected nodes, SHALL carry a human-readable reason,
and SHALL NOT silently remove existing nodes.

#### Scenario: A discovered blocker is inserted as a prerequisite

- **WHEN** execution of a node discovers a blocker that also affects other pending nodes
- **THEN** the skill SHALL insert a new prerequisite node into the plan with a reason
- **AND** SHALL add dependency edges from each affected node to the new prerequisite
- **AND** the affected nodes SHALL become blocked until the prerequisite's `outcome` is `merged`

### Requirement: Merge Plan Comment-Addressing Seam

When plan-driven execution encounters unresolved review comments on a node, it SHALL record
them on the node and SHALL present the operator with a delegation hand-off rather than
writing code itself. Automated code-writing to resolve comments is out of scope for this
capability.

#### Scenario: Unresolved comments produce a delegation hand-off

- **WHEN** execution finds unresolved review comments on the node being executed
- **THEN** the skill SHALL record the unresolved-comment summary on the node
- **AND** SHALL offer to delegate resolution to `iterate-on-implementation` or `quick-task`
- **AND** SHALL NOT modify the PR branch's code automatically
