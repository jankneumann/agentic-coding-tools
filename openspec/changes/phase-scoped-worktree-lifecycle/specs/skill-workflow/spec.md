## ADDED Requirements

### Requirement: D1 — Protection SHALL Be Phase-Scoped Around Durable Handoffs

Directly invoked write-capable lifecycle skills SHALL use an explicit standalone
mode by default. Each phase SHALL create or adopt its managed worktree, acquire
an owner-scoped activity lease before mutation, maintain its heartbeat, push its
durable branch output, and release its lease plus safely tear down the local
worktree in executable `finally`-style finalization. A workflow MUST NOT return
`awaiting review` while it owns a live local activity lease.

Continuous ownership SHALL be opt-in and SHALL require an explicit parent owner
token; nested skills MUST NOT infer continuous mode from an existing worktree.

#### Scenario: Durable push precedes phase release

- **WHEN** a standalone phase completes successfully
- **THEN** it SHALL commit and push its durable output before releasing its lease
- **AND** it SHALL safely tear down its phase worktree before returning `awaiting review`

#### Scenario: Failed phase still finalizes activity

- **WHEN** a standalone phase fails after acquiring its lease
- **THEN** executable finalization SHALL attempt owner-checked release and safe teardown
- **AND** dirty or unmerged state MUST NOT be force-deleted
- **AND** recovery information SHALL identify any preserved worktree

### Requirement: D2 — Standalone Planning SHALL Deliver a Proposal-Only PR

A direct `plan-feature` run SHALL use a proposal branch named
`openspec/<change-id>--proposal`. It SHALL create and strictly validate the
proposal, design, delta specifications, tasks, contracts, and work packages;
commit and push those artifacts; create a pull request whose body contains
`OpenSpec-Delivery: proposal`; and then finalize its phase-owned lease and
worktree on both success and failure.

Implementation SHALL later begin from the reviewed proposal on `main` using the
normal `openspec/<change-id>` implementation branch, not from an idle proposal
worktree.

#### Scenario: AC-01 — Proposal PR leaves no active or permanently pinned worktree

- **WHEN** standalone planning creates and pushes a proposal pull request
- **THEN** the proposal artifacts SHALL be on `openspec/<change-id>--proposal`
- **AND** the PR body SHALL contain `OpenSpec-Delivery: proposal`
- **AND** no live activity lease or legacy permanent activity pin SHALL remain
- **AND** the local planning worktree SHALL be absent unless safe teardown explicitly reports dirty or unmerged state

#### Scenario: Proposal artifacts fail strict validation

- **WHEN** strict OpenSpec validation fails before proposal delivery
- **THEN** the workflow MUST NOT create a proposal PR
- **AND** finalization SHALL release the planning owner's lease
- **AND** unsafe local state SHALL be preserved with operator-visible recovery instructions

### Requirement: D3 — Standalone Implementation and Validation Phases SHALL Own Independent Worktrees

Direct `iterate-on-plan`, `implement-feature`, `iterate-on-implementation`, and
`validate-feature` invocations SHALL each create or adopt a phase-specific
managed worktree and owner-scoped lease. Each phase SHALL push its commits or
reports to the appropriate proposal or implementation PR branch before release
and safe teardown. A later phase SHALL be able to recreate its worktree from the
remote branch.

This contract SHALL apply to sequential, local-parallel, and coordinated tiers.
Package child worktrees SHALL remain isolated and SHALL be safely torn down after
integration or failure.

#### Scenario: AC-06 — Every implementation tier releases its phase lease

- **WHEN** `implement-feature` runs in the sequential, local-parallel, or coordinated tier
- **AND** the tier reaches pushed completion or a terminal failure
- **THEN** that tier SHALL execute the same owner-checked release contract
- **AND** it SHALL safely tear down the parent phase worktree and integrated package children
- **AND** it MUST NOT release a lease owned by a continuous parent

#### Scenario: Later phase recreates from durable remote state

- **WHEN** implementation output has been pushed and its local worktree removed
- **AND** standalone validation begins later
- **THEN** validation SHALL recreate or adopt an isolated worktree from the remote implementation branch
- **AND** validation SHALL acquire a distinct validation owner lease

### Requirement: D4 — Autopilot SHALL Hold One Continuous Owner Lease Through Submission

Autopilot SHALL create an owner token of the form `autopilot:<run-id>`, acquire
one continuous activity lease before PLAN, and pass that owner and explicit
continuous lifecycle mode to all nested write-capable skills. It SHALL renew the
same lease at every write-capable phase transition and when resuming through
PLAN, PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, VALIDATE,
optional VAL_REVIEW, and SUBMIT_PR. Nested skills MUST NOT release or replace the
parent-owned lease.

After the pull request and a recoverable checkpoint are durable, autopilot SHALL
release its lease and safely tear down before entering DONE or presenting any
human merge gate. On terminal failure or ESCALATE, it SHALL persist a recoverable
checkpoint before owner-checked release.

#### Scenario: AC-07 — One autopilot owner remains stable and is gone before the merge gate

- **WHEN** autopilot proceeds from PLAN through VALIDATE and SUBMIT_PR
- **THEN** every renewal SHALL retain the same `autopilot:<run-id>` owner
- **AND** nested skills SHALL leave that lease owned by autopilot
- **AND** autopilot SHALL release it before DONE presents the human merge gate

#### Scenario: Resume renews rather than reacquires under another owner

- **WHEN** an autopilot run resumes from a durable loop-state checkpoint with its owner token
- **THEN** it SHALL renew the matching lease when still live or reacquire it under the same owner when expired
- **AND** it MUST NOT create a second phase-owned lease

#### Scenario: Escalation checkpoints before releasing activity

- **WHEN** autopilot transitions to ESCALATE after acquiring its continuous lease
- **THEN** it SHALL first persist loop state and recovery context
- **AND** it SHALL then attempt owner-checked release and safe teardown
- **AND** preserved files MUST NOT remain a permanent sync-point blocker

### Requirement: D6 — Session Finalization SHALL Provide a Best-Effort Lease Backstop

Executable orchestration paths SHALL use `finally`-style owner release. Session
end and stop hooks SHALL additionally attempt local, owner-scoped release for all
leases belonging to the terminating session when that identity is available.
The hook SHALL work without coordinator connectivity, SHALL be idempotent, and
MUST NOT release another session's or run's lease.

#### Scenario: Session end releases only matching owners

- **WHEN** session `session-7` ends with two leases owned by that session and one lease owned by `autopilot:run-9`
- **THEN** the session hook SHALL best-effort release the two matching leases
- **AND** it MUST leave `autopilot:run-9` unchanged
- **AND** coordinator unavailability SHALL NOT prevent the local attempt

### Requirement: Canonical Lifecycle Skills SHALL Generate Consistent Runtime Mirrors

Lifecycle behavior SHALL be authored in canonical `skills/` sources. The
repository installer SHALL regenerate supported runtime mirrors, and drift
checks SHALL compare generated copies with canonical sources. Implementations
MUST NOT hand-maintain divergent `.agents/skills/` or `.claude/skills/` copies.

#### Scenario: AC-12 — Installed mirrors pass drift checks

- **WHEN** canonical lifecycle skills and helpers are updated and `skills/install.sh` regenerates runtime mirrors
- **THEN** repository drift checks SHALL pass for every installed target
- **AND** a manually divergent runtime copy MUST cause the drift check to fail with its path
