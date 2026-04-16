# software-factory-tooling — Delta Spec for add-decision-index

## ADDED Requirements

### Requirement: Per-Capability Decision Index Emitter

The archive-intelligence pipeline SHALL extract Decision bullets tagged `architectural: <capability>` from every indexed `session-log.md` (including archived changes) and emit per-capability markdown files at `docs/decisions/<capability>.md`, one file per capability directory under `openspec/specs/`.

Each emitted capability file SHALL contain a reverse-chronological timeline of tagged Decisions, grouped by originating change. For each Decision, the emitter SHALL record:
- Decision title (from the bullet's `**bold**` title)
- Rationale (the prose following the `—` delimiter)
- Originating change-id
- Originating phase name (e.g., `Plan`, `Implementation`, `Plan Iteration 2`)
- Phase date (from the `## Phase: <name> (<YYYY-MM-DD>)` header)
- Back-reference link to the session-log phase entry
- Status: one of `active`, `superseded`, or `reverted`

When a later change explicitly supersedes or reverts an earlier tagged Decision — declared via a `supersedes:` marker in the later phase entry (e.g., `\`supersedes: 2026-02-06/add-worktree-isolation#D2\``) — the emitter SHALL:
- Mark the earlier Decision's status as `superseded` in its capability file
- Emit a `**Supersedes**: <earlier change-id>` line on the newer Decision
- Emit a `**Superseded by**: <later change-id>` line on the earlier Decision
- Preserve the earlier entry in the timeline rather than deleting it

The emitter SHALL be incremental: re-running after new changes are archived SHALL update only the affected capability files, matching the incremental behavior already required for `Archive Intelligence Index`.

The emitter SHALL produce deterministic output — running it twice on an unchanged archive SHALL produce byte-identical files, so CI staleness checks (`git diff`) are reliable.

The emitter SHALL populate `docs/decisions/README.md` explaining the purpose of the index, how it is generated, what "architectural" means for tagging purposes, and how to read the capability timelines. The README SHALL be generated (not hand-maintained) so it stays consistent with the current capability set.

#### Scenario: Tagged decisions aggregated by capability
- **GIVEN** three archived changes each with one Decision tagged `architectural: skill-workflow`
- **WHEN** the emitter runs
- **THEN** `docs/decisions/skill-workflow.md` SHALL contain exactly three timeline entries
- **AND** entries SHALL be ordered newest-first by phase date

#### Scenario: Supersession chain preserved
- **GIVEN** an archived change whose phase entry contains `\`supersedes: 2026-02-06/add-worktree-isolation#D2\``
- **AND** the referenced earlier Decision exists in the archive
- **WHEN** the emitter runs
- **THEN** the earlier Decision SHALL be rendered with `Status: superseded` and a `**Superseded by**: <later-change-id>` link
- **AND** the newer Decision SHALL be rendered with `**Supersedes**: <earlier-change-id>` link

#### Scenario: Untagged decisions excluded
- **GIVEN** an archived change with five Decisions, only two of which carry `architectural:` tags
- **WHEN** the emitter runs
- **THEN** only the two tagged Decisions SHALL appear in any `docs/decisions/*.md` file
- **AND** the three untagged Decisions SHALL NOT be surfaced in the index

#### Scenario: New capability directory auto-created
- **GIVEN** a session-log Decision tagged `architectural: new-capability` where `docs/decisions/new-capability.md` does not yet exist
- **AND** `openspec/specs/new-capability/` exists
- **WHEN** the emitter runs
- **THEN** `docs/decisions/new-capability.md` SHALL be created with the tagged Decision

#### Scenario: Incremental regeneration on re-run
- **GIVEN** a populated `docs/decisions/` directory and no new archived changes
- **WHEN** the emitter runs twice in succession
- **THEN** the second run SHALL produce byte-identical output to the first
- **AND** `git diff docs/decisions/` SHALL report no changes

#### Scenario: Make target regenerates and CI staleness check
- **GIVEN** a `make decisions` target that invokes the emitter
- **WHEN** CI runs `make decisions` followed by `git diff --exit-code docs/decisions/`
- **THEN** the step SHALL succeed if `docs/decisions/` is up to date
- **AND** the step SHALL fail with a non-zero exit code if any capability file would change, identifying stale indices before merge

#### Scenario: Malformed tag reported in strict mode
- **GIVEN** a session-log Decision tagged `architectural: no-such-capability` where the target capability directory does not exist
- **WHEN** the emitter runs with `--strict` (CI mode)
- **THEN** the emitter SHALL exit non-zero after emitting a warning identifying change-id, phase, and the invalid capability value
