## ADDED Requirements

### Requirement: D7 — OpenSpec PR Delivery Stage SHALL Be Deterministically Classified

Merge triage SHALL classify each OpenSpec pull request as `proposal`,
`implementation`, `mixed`, or `ambiguous`. The classifier SHALL primarily use
the changed-file set together with the OpenSpec proposal state on the pull
request's base branch. It SHALL use branch naming and an exact PR-body marker
`OpenSpec-Delivery: proposal|implementation|mixed` only as corroborating
evidence. The four-way result, evidence, and warnings SHALL be deterministic and
serializable in the durable merge plan.

Conflicting, missing, or incomplete evidence MUST produce `ambiguous`; triage
MUST NOT silently infer completed implementation or archival from an
`openspec/*` branch name alone.

#### Scenario: AC-10 — Proposal, implementation, and mixed classification

- **WHEN** unit fixtures cover planning-artifact-only changes without a proposal on base, implementation changes with a governing proposal on base, and combined planning plus implementation changes
- **THEN** the classifier SHALL return `proposal`, `implementation`, and `mixed` respectively
- **AND** each result SHALL record changed-file, base-state, branch, and marker evidence

#### Scenario: AC-10 — Conflicting marker fails safe and warns

- **WHEN** changed files and base state indicate `proposal` but the PR body declares `OpenSpec-Delivery: implementation`
- **THEN** the classifier MUST return `ambiguous`
- **AND** merge triage SHALL emit an operator-visible warning describing the conflict
- **AND** it MUST require an explicit operator decision before merge or cleanup

#### Scenario: Legacy implementation PR remains processable

- **WHEN** an existing OpenSpec PR lacks the delivery marker but changes implementation files and its governing proposal is present on the base branch
- **THEN** the classifier SHALL classify it as `implementation` from primary evidence
- **AND** absence of the corroborating marker alone MUST NOT make it unprocessable

### Requirement: D8 — Author Identity, Origin, and Delivery Stage SHALL Remain Independent

Discovery and merge-plan records SHALL preserve OpenSpec origin, delivery stage,
GitHub author, and author vendor as separate fields. For a Claude-authored
OpenSpec PR, independent local review SHALL request each configured Codex, Grok,
and Pi reviewer. An unavailable reviewer SHALL be reported explicitly and MUST
NOT be silently substituted with Claude or another same-author review.

Proposal review context SHALL include proposal, design, delta specifications,
contracts, tasks, and work packages but no implementation-review prompt.
Implementation and mixed review context SHALL include governing planning
artifacts plus the implementation diff. Consensus and blocking dispositions
SHALL remain merge gates.

#### Scenario: AC-04 — Claude proposal dispatches Codex, Grok, and Pi on planning context

- **WHEN** a Claude-authored PR is classified as `proposal`
- **THEN** review dispatch SHALL target configured Codex, Grok, and Pi reviewers
- **AND** each prompt SHALL contain the available planning artifacts
- **AND** each prompt MUST omit implementation-diff review instructions

#### Scenario: AC-05 — Claude implementation and mixed PRs include plan plus diff

- **WHEN** a Claude-authored PR is classified as `implementation` or `mixed`
- **THEN** review dispatch SHALL target configured Codex, Grok, and Pi reviewers
- **AND** each prompt SHALL include governing OpenSpec context and the implementation diff

#### Scenario: Unavailable independent vendor is explicit

- **WHEN** one of configured Codex, Grok, or Pi is unavailable
- **THEN** merge evidence SHALL name that unavailable vendor and the resulting quorum
- **AND** the workflow MUST NOT record a same-author substitute as that vendor's review

### Requirement: D9 — Merge Validation, Cleanup, and Archival SHALL Follow Delivery Stage

A `proposal` PR SHALL run independent plan review and strict OpenSpec validation
against the PR head. After merge it SHALL run the once-per-pass main-context
convergence required for every merge, but MUST skip deployment, smoke, security,
e2e, implementation holdout/rework gates, `cleanup-feature`, archival, and active
change-directory deletion.

An `implementation` or `mixed` PR SHALL retain full implementation validation,
post-merge cleanup, archival, and main-context convergence. An `ambiguous` PR
MUST stop automatic stage-specific routing pending an explicit operator
decision. These decisions and their evidence SHALL be durable in merge-plan
orchestration so discovery, review, execution, and resume use the same stage.

#### Scenario: AC-02 — Proposal PR passes active guard into triage

- **WHEN** a completed standalone planning run has pushed its proposal PR and released its phase lease
- **THEN** `/merge-pull-requests` SHALL pass the active-agent guard without `--force`
- **AND** the proposal SHALL enter plan-review triage

#### Scenario: AC-03 — Proposal merge leaves active change on main

- **WHEN** a `proposal` PR passes strict OpenSpec validation and is merged
- **THEN** `openspec/changes/<change-id>/` SHALL remain active on `main`
- **AND** merge processing MUST NOT invoke `cleanup-feature` or archive/delete the change
- **AND** it SHALL run main-context convergence once for the merge pass

#### Scenario: Proposal routing skips implementation-only gates

- **WHEN** merge triage processes a PR classified as `proposal`
- **THEN** it MUST skip deploy, smoke, security, e2e, and implementation holdout/rework gates
- **AND** it SHALL still require strict OpenSpec validation and review consensus

#### Scenario: Implementation and mixed routing preserves cleanup

- **WHEN** an `implementation` or `mixed` PR passes full validation and is merged
- **THEN** merge processing SHALL invoke the existing cleanup and archival path
- **AND** it SHALL run main-context convergence once for the merge pass

#### Scenario: Durable merge plan preserves stage evidence on resume

- **WHEN** merge-plan orchestration records an OpenSpec PR and later resumes execution
- **THEN** the plan SHALL retain delivery stage, primary evidence, marker evidence, author vendor, and ambiguity warnings
- **AND** resumed execution MUST NOT reclassify from branch naming alone

### Requirement: D9 — OpenSpec Integration SHALL Be Delivery-Stage Aware

The skill SHALL route OpenSpec pull requests according to their deterministic
delivery stage. Proposal merges SHALL keep the change active and SHALL NOT
recommend or invoke archival. Implementation and mixed merges SHALL retain the
existing cleanup/archive behavior. Ambiguous delivery SHALL require explicit
operator disposition before merge-time validation or cleanup selection.

#### Scenario: Proposal OpenSpec PR is merged without cleanup recommendation

- **WHEN** an OpenSpec PR classified as `proposal` is merged
- **THEN** the skill SHALL report that the proposal remains active for implementation
- **AND** it MUST NOT recommend or invoke `/cleanup-feature <change-id>`

#### Scenario: AC-11 — Existing implementation PR retains cleanup behavior

- **WHEN** a legacy or current OpenSpec PR is deterministically classified as `implementation`
- **AND** it passes full validation and is merged
- **THEN** the skill SHALL safely process it through the existing cleanup/archive workflow
