# Skill Workflow — Delta for add-timestamped-priorities-tree

## MODIFIED Requirements

### Requirement: Prioritization Report Persistence

The `prioritize-proposals` skill SHALL persist each report run as an accumulating event-artifact under `openspec/priorities/<YYYY-MM-DD>-HHMMSS-<short-git-sha>/`, with `report.md` always written and `report.json` written only when `--format json` is passed. Each run SHALL additionally rewrite `openspec/priorities/latest.md` (and `openspec/priorities/latest.json` when JSON was produced) so that consumers seeking the most recent report do not need to enumerate dated directories.

The skill SHALL NOT write to `openspec/changes/prioritized-proposals.{md,json}` after this change lands. That path is reserved exclusively for in-flight change proposals.

#### Scenario: Per-run dated artifact written

- **WHEN** the user invokes `/prioritize-proposals`
- **THEN** the skill SHALL construct a run directory at `openspec/priorities/<YYYY-MM-DD>-HHMMSS-<short-git-sha>/` using the current UTC date/time and the short SHA of HEAD
- **AND** SHALL write `report.md` into that directory
- **AND** SHALL write `report.json` into that directory if `--format json` was passed
- **AND** SHALL include a timestamp and analyzed git range in the report header

#### Scenario: Latest pointer rewritten on each run

- **WHEN** the skill finishes writing the dated artifact directory
- **THEN** it SHALL overwrite `openspec/priorities/latest.md` with the same content as the freshly-written `report.md`
- **AND** SHALL overwrite `openspec/priorities/latest.json` with the freshly-written `report.json` if JSON was produced
- **AND** SHALL NOT create symlinks; both `latest.md` and `latest.json` SHALL be regular files

#### Scenario: Legacy write path is rejected

- **WHEN** the skill is invoked after this change lands
- **THEN** the skill SHALL NOT write to `openspec/changes/prioritized-proposals.md` or `openspec/changes/prioritized-proposals.json`
- **AND** any attempt to do so SHALL fail loudly during skill execution

## ADDED Requirements

### Requirement: Priorities Run-ID Format

The `prioritize-proposals` skill SHALL identify each run by a deterministic `run_id` of the form `<YYYY-MM-DD>-HHMMSS-<short-git-sha>`, where `<short-git-sha>` is the first 7 characters of `HEAD`. This run-id SHALL appear in the dated directory name AND in the `run_id` field of the artifact header on `report.json`.

#### Scenario: Run-id construction

- **WHEN** the skill starts a run at UTC `2026-06-10T14:30:52Z` with `HEAD = a93fe59a8b...`
- **THEN** the run-id SHALL be `2026-06-10-143052-a93fe59`
- **AND** the dated directory SHALL be `openspec/priorities/2026-06-10-143052-a93fe59/`
- **AND** the `run_id` field in `report.json`'s header block SHALL be `2026-06-10-143052-a93fe59`

#### Scenario: Run-id stability under reruns

- **WHEN** the same skill invocation is retried after a transient failure
- **THEN** a fresh run-id MUST be generated using the *current* UTC second and HEAD
- **AND** the failed run's directory MUST NOT be reused (a new directory MUST be created)

### Requirement: Mandatory Artifact Header on Report JSON

Every `report.json` written by `prioritize-proposals` SHALL begin with a top-level `_header` object carrying the mandatory event-artifact header fields. The header schema SHALL match the codeviz event-artifact convention: `schema_version`, `generated_at`, `git_sha`, `generator`, `run_id`, `event_kind`. Until `skills/shared/artifact_header.py` is available (codeviz roadmap), this skill SHALL construct the header inline via a small private helper.

#### Scenario: Header fields populated

- **WHEN** `report.json` is written
- **THEN** the top-level `_header` object SHALL contain:
  - `schema_version` (integer, currently `1`)
  - `generated_at` (ISO-8601 UTC timestamp with `Z` suffix)
  - `git_sha` (full 40-character SHA of HEAD at run time)
  - `generator` (string, format `"prioritize-proposals@<version>"`)
  - `run_id` (string matching the dated-directory run-id)
  - `event_kind` (string, `"priorities-report"`)

#### Scenario: Header migration to shared helper

- **WHEN** `skills/shared/artifact_header.py` becomes available in a future change
- **THEN** `prioritize-proposals` SHALL migrate to that helper without changing the on-disk header schema
- **AND** existing dated artifacts SHALL remain readable without rewriting

### Requirement: Priorities Retention Policy

The `prioritize-proposals` skill SHALL keep the most recent `N` dated directories in `openspec/priorities/` (default `N=30`, overridable via `--retain N`). Directories that fall outside the retention window SHALL be moved to `openspec/priorities/archive/` rather than deleted. The retention scan SHALL run after each successful write of a new dated artifact directory.

#### Scenario: Default retention preserves 30 most recent

- **GIVEN** `openspec/priorities/` contains 31 dated directories
- **WHEN** `/prioritize-proposals` is invoked with no `--retain` flag
- **THEN** after writing the new run, exactly 30 directories SHALL remain in `openspec/priorities/`
- **AND** the oldest one SHALL be moved to `openspec/priorities/archive/`

#### Scenario: Custom retention

- **GIVEN** `openspec/priorities/` contains 11 dated directories
- **WHEN** `/prioritize-proposals --retain 5` is invoked
- **THEN** after writing the new run, exactly 5 directories SHALL remain in `openspec/priorities/`
- **AND** 7 directories SHALL have been moved to `openspec/priorities/archive/` (the 6 oldest existing + the newly-bumped-out one)

#### Scenario: Archive accumulates, never deletes

- **WHEN** a directory is moved to `openspec/priorities/archive/`
- **THEN** the skill SHALL NOT subsequently delete it
- **AND** the archive subdirectory SHALL preserve the original `<YYYY-MM-DD>-HHMMSS-<short-git-sha>/` directory name

### Requirement: Pre-Migration Header Allowance

Dated directories created before this change shipped (i.e., the one-time legacy migration entry at `openspec/priorities/2026-05-04-legacy/`) MAY omit the mandatory `_header` block on their `report.json`. The skill MUST NOT fail when reading or listing such entries, and any future header-validation lint SHALL whitelist the literal directory name `2026-05-04-legacy`.

#### Scenario: Legacy entry is readable

- **GIVEN** `openspec/priorities/2026-05-04-legacy/report.md` exists from the one-time migration
- **WHEN** a future tool enumerates the priorities tree
- **THEN** the legacy entry SHALL be listed normally
- **AND** any header-presence check SHALL skip directories whose name matches the literal string `2026-05-04-legacy`
