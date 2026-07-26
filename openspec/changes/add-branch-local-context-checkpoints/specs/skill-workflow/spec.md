# Skill Workflow — per-package context checkpoints

## ADDED Requirements

### Requirement: Implementation dispatch triggers context checkpoints per work package

The implementation workflow SHALL evaluate each completed work package for context impact
and run a branch-local context checkpoint when the package's context-impact surfaces
indicate that project context was invalidated.

The trigger is derived from the package's declared or inferred context-impact surfaces,
evaluated from the package's own changed-file list rather than from a git range, so the
decision holds for uncommitted work inside a feature worktree.

#### Scenario: A context-invalidating package produces a checkpoint

- **WHEN** a work package completes
- **AND** its context-impact surfaces include a context-invalidating surface
- **THEN** a branch-local context checkpoint runs for that package
- **AND** the checkpoint report is recorded against the change

#### Scenario: A package with no context impact produces no checkpoint

- **WHEN** a work package completes
- **AND** its declared context-impact surfaces are explicitly empty
- **THEN** no checkpoint runs for that package
- **AND** the implementation summary records that the package asserted no impact

#### Scenario: Checkpoint evaluation uses the package's changed-file list

- **WHEN** the workflow evaluates a package for context impact
- **THEN** it supplies the package's changed-file list directly
- **AND** the evaluation succeeds without requiring the changes to be committed

### Requirement: Unmigrated packages are reported as unmigrated rather than as impact-free

The implementation workflow SHALL distinguish a work package that declares no
context-impact block from one that declares an empty set of surfaces, and SHALL report the
former as unmigrated.

A missing declaration is absence of evidence; an explicit empty declaration is an
assertion that nothing is affected. Collapsing the two would let an unmigrated package
appear verified.

#### Scenario: Missing declaration is reported as unmigrated

- **WHEN** a work package completes and declares no context-impact block
- **THEN** the implementation summary records the package as unmigrated
- **AND** it does not record the package as having no context impact

#### Scenario: Empty declaration is reported as an assertion

- **WHEN** a work package completes and declares an empty context-impact surface list
- **THEN** the implementation summary records the package as asserting no impact
- **AND** it does not record the package as unmigrated

### Requirement: Checkpoint execution honours the work package scope

The implementation workflow SHALL pass the completed package's resolved read scope to the
checkpoint, so that checkpoint execution cannot read files the package was not permitted
to read.

#### Scenario: Package scope is supplied to the checkpoint

- **WHEN** the workflow runs a checkpoint for a package
- **THEN** it supplies that package's read-allow and deny globs
- **AND** the checkpoint restricts its execution to the resolved scope
