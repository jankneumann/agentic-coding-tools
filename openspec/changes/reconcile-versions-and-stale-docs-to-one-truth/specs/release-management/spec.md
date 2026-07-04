## ADDED Requirements

### Requirement: Single-Source Version

The repository SHALL derive all component versions from the root `VERSION` file.

#### Scenario: Component manifests agree with VERSION

WHEN the root `VERSION` file is bumped
THEN the agent-coordinator, packages/gen-eval, skills, and apps/kanban-viz manifests and the coordinator `/health` report SHALL reflect the same version without further manual edits.

### Requirement: Tag-Triggered Releases

Releases SHALL be published from git tags by a tag-triggered workflow that verifies the changelog.

#### Scenario: Tag triggers release

WHEN a `v*` tag is pushed
THEN the release workflow SHALL verify `CHANGELOG.md` contains a matching entry
AND publish a GitHub release for that tag.

### Requirement: Canonical Memory Tag Schema

The D4 memory tag schema SHALL be defined authoritatively in exactly one file; all other documents SHALL reference it.

#### Scenario: One authoritative statement

WHEN the repository is searched for the memory tag schema definition
THEN exactly one canonical source SHALL define the schema
AND all other mentions SHALL link to that source instead of restating it.
