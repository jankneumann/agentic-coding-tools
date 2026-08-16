## MODIFIED Requirements

### Requirement: Repository-Mutating Workflow Entrypoint Invariant

Every repository-mutating entrypoint classified in the canonical
`mutating-skill-inventory.yaml` SHALL follow its declared standalone-owner,
continuous-parent, child-owner, hybrid-sync-point, sync-point, registry-reader,
or inherited-only lifecycle. The inventory SHALL cover every canonical consumer
of setup, heartbeat, pin, active-agent, and registry state and automated tests
MUST fail for an unclassified consumer. A repository-mutating entrypoint SHALL
operate only in a managed worktree or an explicitly inherited fenced worktree,
never the shared checkout. A direct write-capable phase SHALL
enter its phase worktree, acquire a fenced activity lease, and finalize it
through the shared executable lifecycle controller. Continuous mode SHALL be
explicit and parent-owned; retention or an existing worktree MUST NOT imply
continuous ownership.

#### Scenario: Two direct planning sessions use disposable proposal worktrees

- **WHEN** two direct planning sessions create different changes from one shared checkout
- **THEN** each SHALL use its own `openspec/<change-id>--proposal` branch and managed worktree
- **AND** neither SHALL mutate the shared checkout or pin its worktree as activity

#### Scenario: Reviewed proposal is not reused as an idle implementation checkout

- **WHEN** a direct proposal PR has merged and its planning worktree was disposed
- **THEN** implementation SHALL create or adopt `openspec/<change-id>` from the reviewed proposal on `main` or its durable remote implementation branch
- **AND** it MUST NOT depend on the deleted proposal worktree

### Requirement: Planning Skills Use Feature-Level Worktrees

Direct planning SHALL create a feature-level managed worktree on
`openspec/<change-id>--proposal`, acquire a standalone fenced PLAN lease, create
and strictly validate all required plan artifacts, commit and push them, create a
proposal-only PR carrying delivery and author-vendor trailers, then safely
dispose the local worktree while the lease still fences acquisition. Continuous
autopilot planning SHALL instead use its explicit parent-owned
`openspec/<change-id>` worktree and MUST NOT release or dispose it.

#### Scenario: AC-01 — Direct plan feature delivers a disposable proposal branch

- **WHEN** a user directly runs `plan-feature` for change `add-user-auth`
- **THEN** the skill SHALL create `openspec/add-user-auth--proposal`
- **AND** all validated plan artifacts SHALL be committed and pushed on that branch
- **AND** the proposal PR SHALL contain `OpenSpec-Delivery: proposal`
- **AND** finalization SHALL leave no live lease or automatically adoptable dirty worktree

#### Scenario: Proposal artifacts fail strict validation

- **WHEN** strict OpenSpec validation fails before proposal delivery
- **THEN** the workflow MUST NOT create a proposal PR
- **AND** finalization SHALL dispose clean durable state or atomically quarantine and clear its exact lease

### Requirement: Implementation Orchestrator Worktree Setup

The implementation orchestrator SHALL create a dedicated worktree and fenced
lease for every root or parallel work package before mutation. Each package
lease SHALL be independent from the parent phase lease, included in dispatch
context, asserted before integration, and disposed after integration or
atomically quarantined-and-cleared on failure. Retention aliases MUST NOT be used as
activity protection.

#### Scenario: Package worktrees use leases rather than pins

- **WHEN** an orchestrator dispatches three implementation packages
- **THEN** each registered worktree SHALL have its own exact owner, lease id, controller id, and entry generation
- **AND** each dispatch SHALL receive its exact worktree, branch, ownership triple, and entry generation
- **AND** no package SHALL rely on `pinned: true` to block concurrent writers

#### Scenario: Worktrees are finalized after integration

- **WHEN** package integration completes successfully
- **THEN** the orchestrator SHALL push the parent feature ref and prove the exact package HEAD is reachable from the package entry's stored durability target
- **AND** it SHALL assert each package lease and safely dispose its clean remotely durable worktree without requiring the child branch name itself to be pushed
- **AND** a dirty or non-durable package SHALL be quarantined rather than force-deleted

## ADDED Requirements

### Requirement: Protection SHALL Be Phase-Scoped Around Durable Handoffs

Directly invoked write-capable lifecycle skills SHALL use an explicit standalone
mode by default. Each phase SHALL create or adopt its managed worktree, acquire
an owner/lease/controller-scoped activity lease before mutation, maintain its
heartbeat through the executable lifecycle controller, push its durable branch
output, and finalize the local worktree without a release-then-remove race. A workflow MUST NOT return
`awaiting review` while it owns a live local activity lease.

Continuous ownership SHALL be opt-in and SHALL require an explicit parent owner
token; nested skills MUST NOT infer continuous mode from an existing worktree.

#### Scenario: Durable push precedes phase teardown

- **WHEN** a standalone phase completes successfully
- **THEN** it SHALL commit and push its durable output before teardown
- **AND** it SHALL safely tear down its phase worktree while the exact lease remains live before returning `awaiting review`

#### Scenario: Failed phase still finalizes activity

- **WHEN** a standalone phase fails after acquiring its lease
- **THEN** executable finalization SHALL attempt exact-triple-and-generation-checked teardown
- **AND** unsafe teardown SHALL atomically quarantine and clear the lease without a follow-up release
- **AND** dirty or unmerged state MUST NOT be force-deleted
- **AND** recovery information SHALL identify any preserved worktree

### Requirement: Standalone Implementation and Validation Phases SHALL Own Independent Worktrees

Direct `iterate-on-plan`, `implement-feature`, `iterate-on-implementation`, and
`validate-feature` invocations SHALL each create or adopt a phase-specific
managed worktree and owner-scoped lease. Each phase SHALL push its commits or
reports to the appropriate proposal or implementation PR branch before fenced
teardown. A later phase SHALL be able to recreate its worktree from the
remote branch.

This contract SHALL apply to sequential, local-parallel, and coordinated tiers.
Package child worktrees SHALL remain isolated and SHALL be safely torn down after
integration or atomically quarantined-and-cleared on failure.

#### Scenario: AC-06 — Every implementation tier finalizes its phase lease

- **WHEN** `implement-feature` runs in the sequential, local-parallel, or coordinated tier
- **AND** the tier reaches pushed completion or a terminal failure
- **THEN** that tier SHALL execute the same exact-triple-and-generation teardown-or-quarantine contract
- **AND** it SHALL safely tear down the parent phase worktree and integrated package children
- **AND** it MUST NOT release a lease owned by a continuous parent

#### Scenario: Later phase recreates from durable remote state

- **WHEN** implementation output has been pushed and its local worktree removed
- **AND** standalone validation begins later
- **THEN** validation SHALL recreate or adopt an isolated worktree from the remote implementation branch
- **AND** validation SHALL acquire a distinct validation owner lease

### Requirement: Autopilot SHALL Hold One Continuous Owner Lease Through Submission

Autopilot SHALL resolve and persist the change id and continuous
`openspec/<change-id>` worktree before PLAN mutation, create an owner token of
the form `autopilot:<run-id>` plus a lease and controller id, acquire one
continuous activity lease, and pass that fenced identity and explicit continuous
lifecycle mode to all nested write-capable skills. The parent controller alone
SHALL renew the lease at every write-capable phase transition through
PLAN, PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, VALIDATE,
optional VAL_REVIEW, and SUBMIT_PR. Nested skills SHALL only assert the inherited
triple and MUST NOT renew, release, or replace the parent-owned lease.

Autopilot SHALL retain canonical workflow state at the existing feature-branch
`loop-state.json` path and persist a schema-valid recovery envelope outside the
disposable checkout, including branch, stored durability target, durable HEAD,
canonical loop-state path and digest, generation, finalization intent, and
checkout state. Before any I/O, the reader SHALL validate safe identifiers and
prove that the envelope directory, owner, branch, loop-state path, and remote ref
derive from its run/change identity. After fetching and hashing the exact blob,
it SHALL validate the canonical loop-state change id before worktree creation or
lease acquisition. All
envelope writes SHALL use a per-run lock, generation CAS, atomic replace, file
fsync, and directory fsync; present/pending writes SHALL additionally prove the
exact live registry triple plus entry generation, and post-removal CAS SHALL be
bound to the unchanged pending identity. The envelope SHALL locate and verify restored canonical state
but SHALL NOT independently authorize a phase or lease. After the pull request and checkpoint
are durable, autopilot SHALL CAS teardown intent, safely tear down while its
exact lease is live, and record removal before entering DONE or presenting any human merge
gate. Terminal failure and ESCALATE use the same checkpoint-before-teardown
protocol; a non-durable checkpoint MUST quarantine rather than delete the
checkout.

#### Scenario: AC-07 — One autopilot owner remains stable and is gone before the merge gate

- **WHEN** autopilot proceeds from PLAN through VALIDATE and SUBMIT_PR
- **THEN** every renewal SHALL retain the same `autopilot:<run-id>` owner
- **AND** nested skills SHALL leave that lease owned by autopilot
- **AND** autopilot SHALL remove it through fenced teardown or quarantine-plus-clear before DONE presents the human merge gate

#### Scenario: Replacement controller resumes without duplicating a live writer

- **WHEN** an autopilot run resumes from a durable loop-state checkpoint with its owner token
- **THEN** the same live controller MAY retry its exact triple idempotently
- **AND** a replacement controller SHALL reject live or indeterminate old evidence and rotate the lease/controller only after stale evidence and safe durable state are proven
- **AND** it MUST NOT create a second phase-owned lease

#### Scenario: Released or removed autopilot checkout resumes from durable state

- **WHEN** ESCALATE or exception finalization recorded `checkout_state=removed` outside the worktree
- **AND** the configured remote URL digest still matches and the freshly fetched stored ref tip equals the recorded durable HEAD exactly
- **THEN** resume SHALL hash and schema-validate the loop-state blob at that exact OID before recreating the checkout and registry entry, acquire a new lease/controller under the stable owner, checkpoint them, and continue from the phase derived from canonical state
- **AND** advanced, rewound, missing, URL-mismatched, quarantined, or partially present state SHALL remain escalated

#### Scenario: Fresh description bootstraps before PLAN mutation

- **WHEN** autopilot starts from a feature description without a pre-existing worktree
- **THEN** it SHALL deterministically resolve and checkpoint the change id, branch, owner, and lease id before PLAN writes
- **AND** it SHALL ask the operator before mutation if the change id cannot be resolved uniquely

#### Scenario: Escalation checkpoints before releasing activity

- **WHEN** autopilot transitions to ESCALATE after acquiring its continuous lease
- **THEN** it SHALL first persist loop state and recovery context
- **AND** it SHALL then attempt exact-triple-and-generation-checked teardown while the lease remains live
- **AND** unsafe teardown SHALL quarantine and clear ownership atomically
- **AND** preserved files MUST NOT remain a permanent sync-point blocker

### Requirement: Session Finalization SHALL Provide a Best-Effort Lease Backstop

Executable orchestration paths SHALL use `finally`-style teardown-or-quarantine. Session
end and stop hooks SHALL additionally attempt local, owner-scoped release for all
leases belonging to the terminating session when that identity is available.
The hook SHALL work without coordinator connectivity, SHALL be idempotent, and
MUST NOT release another session's or run's lease. It SHALL NOT invoke teardown
or mutate an autopilot recovery envelope.

#### Scenario: Session end releases only matching owners

- **WHEN** session `session-7` ends with two matching leases and a third autopilot lease whose session id is different or null
- **THEN** the session hook SHALL best-effort release the two matching leases
- **AND** it MUST leave `autopilot:run-9` unchanged
- **AND** coordinator unavailability SHALL NOT prevent the local attempt
- **AND** every matching checkout not already removed by explicit finalization SHALL be quarantined before its lease is cleared
- **AND** its exact prior controller identity and process evidence SHALL remain bound to recovery context until safe adoption or teardown
- **AND** the hook MUST NOT delete a worktree or make preserved state ordinarily adoptable
- **AND** a later autopilot resume that observes a present-envelope/quarantined-registry mismatch SHALL remain escalated rather than silently reacquire

### Requirement: Prerequisite Evidence SHALL Be Visible Before Dependent Dispatch

The authoritative prerequisite preflight SHALL execute as a root package in the
managed shared feature worktree. Completion SHALL require the declared
feature-HEAD barrier to revalidate committed evidence while holding the branch
lock and record that exact HEAD as the minimum base for every dependent
worktree. The scheduler MUST NOT mark the preflight complete, satisfy its DAG
edges, or create a dependent checkout from an earlier feature HEAD.

#### Scenario: Verified preflight commit is the dependent worktree base

- **WHEN** the preflight resolves both authoritative prerequisite merges and commits schema-valid evidence
- **THEN** the scheduler SHALL revalidate that evidence on feature HEAD under the branch lock
- **AND** every unblocked dependent worktree SHALL record and contain that exact feature HEAD as its base
- **AND** a failed verification, changed HEAD, or lost CAS SHALL keep dependent packages blocked until locked re-verification succeeds

### Requirement: Canonical Lifecycle Skills SHALL Generate Consistent Runtime Mirrors

Lifecycle behavior SHALL be authored in canonical `skills/` sources. The
repository installer SHALL regenerate supported runtime mirrors, and drift
checks SHALL compare generated copies with canonical sources. Implementations
MUST NOT hand-maintain divergent `.agents/skills/` or `.claude/skills/` copies.

#### Scenario: AC-12 — Installed mirrors pass drift checks

- **WHEN** canonical lifecycle skills and helpers are updated and `skills/install.sh` regenerates runtime mirrors
- **THEN** repository drift checks SHALL pass for every installed target
- **AND** a manually divergent runtime copy MUST cause the drift check to fail with its path
