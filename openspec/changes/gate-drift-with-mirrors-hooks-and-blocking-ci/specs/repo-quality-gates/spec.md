## ADDED Requirements

### Requirement: Skill Mirror Drift Gate

The repository SHALL fail CI when the runtime skill mirrors (`.claude/skills/`, `.agents/skills/`) drift from the canonical `skills/` sources.

#### Scenario: Mirror edit without sync fails CI

WHEN a commit modifies a runtime mirror file without a matching change to the canonical `skills/` source
THEN the drift-check CI job SHALL fail
AND the failure output SHALL identify the drifted paths.

#### Scenario: install.sh check mode passes on clean tree

WHEN `install.sh --check` runs with mirrors in sync
THEN it SHALL exit 0 without modifying any file.

### Requirement: Active Git Hooks by Default

Repository bootstrap paths SHALL configure `core.hooksPath=.githooks` so pre-commit and post-merge hooks are active without manual steps.

#### Scenario: Fresh clone gets hooks

WHEN a developer runs any documented bootstrap path on a fresh clone
THEN `git config core.hooksPath` SHALL report `.githooks`.

### Requirement: No Orphaned Test Suites

All test files in the repository SHALL be executed by at least one CI job or be removed.

#### Scenario: Quality steps are blocking

WHEN CI runs on a pull request
THEN gen-eval `mypy --strict` and the kanban-viz test suite SHALL run as blocking steps.
