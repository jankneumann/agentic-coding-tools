# Harness Engineering — skills lint gate

## ADDED Requirements

### Requirement: Skill scripts are statically linted in CI

Continuous integration SHALL run a blocking lint check over the `skills/` tree, so that
skill scripts receive the same static analysis as the coordinator source tree.

`skills/` is the repository's largest Python tree. Leaving it unlinted allowed undefined
names, shadowed imports, and unused-result defects to reach the default branch.

#### Scenario: An undefined name in a skill script fails CI

- **WHEN** a skill script references a name that is never defined or imported
- **THEN** the lint check reports an error
- **AND** the continuous integration run fails

#### Scenario: A clean tree passes the lint check

- **WHEN** the lint check runs against a tree with no violations of the selected rules
- **THEN** it reports success
- **AND** the continuous integration run is not blocked by lint

#### Scenario: Lint failure is reported before slower checks

- **WHEN** a change introduces only a lint violation
- **THEN** the lint check fails without first running the full skill test suite

### Requirement: The lint rule set is declared explicitly

The lint configuration SHALL declare its selected rule set explicitly rather than relying
on the linter's default selection.

A linter's default rule set changes between releases. An implicit selection makes a
routine tool upgrade change what the gate enforces, so an unrelated dependency bump
arrives as a large set of new failures.

#### Scenario: The enforced rule set does not change with the linter version

- **WHEN** the lint check runs under a newer linter release that has changed its default
  rule selection
- **THEN** the enforced rule set is unchanged
- **AND** a tree that passed under the previous release still passes

### Requirement: Deliberate import placement is not reported as a violation

The lint configuration SHALL NOT report module-level imports that follow a required
`sys.path` modification as violations.

Skills install as standalone payloads and import sibling modules by flat module name,
which requires inserting the sibling's script directory onto the module search path before
the import executes. Reporting that placement would pressure authors away from a working
convention.

#### Scenario: A skill importing a sibling after a path insert passes lint

- **WHEN** a skill script inserts a sibling script directory onto the module search path
  and then imports a module by flat name
- **THEN** the lint check does not report the import placement as a violation
