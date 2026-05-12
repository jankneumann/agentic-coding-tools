# software-factory-tooling Specification

## Purpose
TBD - created by archiving change add-software-factory-tooling. Update Purpose after archive.
## Requirements
### Requirement: Archive Intelligence Index

The system SHALL provide an archive miner that indexes completed OpenSpec changes and normalizes their artifacts into a machine-readable archive-intelligence index.

The index SHALL support, at minimum, the following inputs when present:
- `proposal.md`
- `design.md`
- `tasks.md`
- spec deltas
- `change-context.md`
- `validation-report.md`
- `session-log.md`
- `process-analysis.md` / `process-analysis.json`
- merge logs

#### Scenario: Archive miner indexes completed change
Given an archived OpenSpec change with proposal, tasks, validation-report, and session-log artifacts
When archive mining runs
Then the change is added to the archive-intelligence index with normalized metadata

#### Scenario: Missing optional artifact does not fail indexing
Given an archived change without `process-analysis.json`
When archive mining runs
Then indexing succeeds and records the artifact as absent

#### Scenario: Index preserves change-level references
Given an archived change with linked requirement refs and change-id
When indexing completes
Then the normalized output preserves those references for downstream retrieval

#### Scenario: Incremental indexing skips already-indexed changes
Given an existing archive index with 10 indexed changes and 2 new archived changes
When archive mining runs
Then only the 2 new changes are processed and appended to the index

### Requirement: Exemplar Registry

The system SHALL derive reusable exemplars from the archive-intelligence index, including scenario seeds, repair patterns, DTU edge cases, and implementation patterns.

The exemplar registry SHALL expose confidence or quality metadata so downstream tools can prefer higher-signal exemplars.

#### Scenario: Scenario seed extracted from archived change
Given an archived change whose validation artifacts show a stable scenario pattern
When exemplar extraction runs
Then the pattern is added to the scenario-seed registry with a source change reference

#### Scenario: Repair pattern extracted from rework history
Given an archived change with validation failures followed by successful remediation
When exemplar extraction runs
Then the normalized fix pattern is added to the repair-pattern registry

#### Scenario: Low-signal exemplar is demoted
Given an archived artifact with incomplete data and no successful outcome evidence
When exemplar extraction runs
Then the exemplar receives a low-confidence score and is not marked preferred

### Requirement: External Project Bootstrap

The system SHALL provide a bootstrap flow for external projects adopting software-factory practices.

The bootstrap flow SHALL scaffold:
- scenario-pack manifests
- public and holdout pack locations
- DTU scaffold placeholders
- archive-intelligence directories
- CI or validation wiring guidance

#### Scenario: Bootstrap creates software-factory layout
Given a project with gen-eval enabled
When the software-factory bootstrap runs
Then it creates manifests, DTU placeholder directories, and archive-intelligence output locations

#### Scenario: Bootstrap references existing OpenSpec artifacts
Given a project already uses OpenSpec
When bootstrap runs
Then the generated guidance references the existing change workflow rather than creating a separate process

#### Scenario: Bootstrap fails gracefully without gen-eval
Given a project that has not enabled gen-eval (no descriptor or scenario directories)
When the software-factory bootstrap runs
Then it exits with a clear error indicating gen-eval must be configured first and provides setup guidance

#### Scenario: Bootstrap includes dogfood-ready example for this repository
Given this repository is the target project
When bootstrap runs
Then it creates scenario-pack manifests under `agent-coordinator/evaluation/gen_eval/manifests/`, DTU placeholder directories under `agent-coordinator/evaluation/gen_eval/dtu/`, and references existing scenario YAML files in the generated manifest

### Requirement: Per-Capability Decision Index Emitter

The archive-intelligence pipeline SHALL extract Decision bullets tagged `architectural: <capability>` from every indexed `session-log.md` (including archived changes) and emit per-capability markdown files at `docs/decisions/<capability>.md`, one file per capability that has at least one valid tagged Decision. Capabilities with zero tagged Decisions SHALL NOT have a file generated — sparse emission keeps the index noise-free.

Each emitted capability file SHALL contain a reverse-chronological timeline of tagged Decisions, grouped by originating change. For each Decision, the emitter SHALL record:
- Decision title (from the bullet's `**bold**` title)
- Rationale (the prose following the `—` delimiter)
- Originating change-id
- Originating phase name (e.g., `Plan`, `Implementation`, `Plan Iteration 2`)
- Phase date (from the `## Phase: <name> (<YYYY-MM-DD>)` header)
- Back-reference link to the session-log phase entry — a real navigable repo-relative path, not a glob placeholder
- Status: one of `active` or `superseded`

When a later change explicitly supersedes an earlier tagged Decision — declared via a `supersedes:` marker in the later phase entry (e.g., `\`supersedes: 2026-02-06/add-worktree-isolation#D2\``) — the emitter SHALL:
- Mark the earlier Decision's status as `superseded` in its capability file
- Emit a `**Supersedes**: <earlier change-id>` line on the newer Decision
- Emit a `**Superseded by**: <later change-id>` line on the earlier Decision
- Preserve the earlier entry in the timeline rather than deleting it

Cross-capability supersession SHALL be supported: the superseding and superseded decisions MAY be tagged for different capabilities; in that case, the emitter renders the correct bidirectional links across the two capability files.

The emitter SHALL produce deterministic output — running it twice on an unchanged archive SHALL produce byte-identical files, so CI staleness checks (`git diff`) are reliable. True incremental re-computation (skipping untouched capability files) is a future optimization; deterministic full-rewrite is the current contract.

The emitter SHALL delete capability files on re-run when the capability no longer has any tagged Decisions. Without this, removing a tag leaves an orphan `<capability>.md` on disk that the `git diff --exit-code` gate cannot detect (the file content is unchanged — it is the presence that is stale), while the regenerated `README.md` lists only currently-populated capabilities and drifts out of sync.

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

#### Scenario: Deterministic regeneration on re-run
- **GIVEN** a populated `docs/decisions/` directory and no new archived changes
- **WHEN** the emitter runs twice in succession
- **THEN** the second run SHALL produce byte-identical output to the first
- **AND** `git diff docs/decisions/` SHALL report no changes

#### Scenario: Stale capability file removed when tags disappear
- **GIVEN** `docs/decisions/<capability>.md` exists from a prior run with a tagged Decision
- **AND** the tag has since been removed from the source session-log
- **WHEN** the emitter runs
- **THEN** `docs/decisions/<capability>.md` SHALL be deleted
- **AND** the regenerated `docs/decisions/README.md` SHALL NOT list that capability

#### Scenario: Cross-capability supersession
- **GIVEN** an earlier Decision tagged `architectural: <capability-A>` in change `<id-earlier>`
- **AND** a later Decision tagged `architectural: <capability-B>` with a `\`supersedes: <id-earlier>#D<n>\`` marker (A ≠ B)
- **WHEN** the emitter runs
- **THEN** `docs/decisions/<capability-A>.md` SHALL render the earlier Decision with status `superseded` and a `**Superseded by**: <id-later>` backlink
- **AND** `docs/decisions/<capability-B>.md` SHALL render the later Decision with a `**Supersedes**: <id-earlier>` forward link

#### Scenario: Make target regenerates and CI staleness check
- **GIVEN** a `make decisions` target that invokes the emitter
- **WHEN** CI runs `make decisions` followed by `git diff --exit-code docs/decisions/`
- **THEN** the step SHALL succeed if `docs/decisions/` is up to date
- **AND** the step SHALL fail with a non-zero exit code if any capability file would change, identifying stale indices before merge

#### Scenario: Malformed tag reported in strict mode
- **GIVEN** a session-log Decision tagged `architectural: no-such-capability` where the target capability directory does not exist
- **WHEN** the emitter runs with `--strict` (CI mode)
- **THEN** the emitter SHALL exit non-zero after emitting a warning identifying change-id, phase, and the invalid capability value

