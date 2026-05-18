## ADDED Requirements

### Requirement: Documentation Sync Skill

The skills system SHALL provide a `user_invocable: true` skill named `update-documentation` at `skills/update-documentation/SKILL.md` that mechanically syncs documentation inventories (skills table, specs table, docs index, project tree) from filesystem reality into generated blocks within `README.md`, `CLAUDE.md`, and `docs/skills-catalogue.md`. Hand-authored prose outside the generated blocks SHALL be preserved byte-for-byte across re-runs.

Generated blocks SHALL be delimited by `<!-- GENERATED: begin docs:<block-id> -->` and `<!-- GENERATED: end docs:<block-id> -->` HTML comment markers, using the same convention established by `coordinator-task-status-renderer`.

The skill SHALL be invokable in two modes:

- **Write mode** (default): apply changes to disk and exit `0`.
- **Check mode** (`--check`): compute the diff in memory and exit `2` if drift exists, `0` if clean, `1` on internal error.

The skill SHALL be wired into the following integration points:

1. `.githooks/pre-commit` runs `--check` if any staged file is under `skills/`, `openspec/specs/`, or `docs/`. A non-zero exit blocks the commit.
2. `.githooks/post-merge` runs write mode after merges touching those paths and auto-commits a follow-up sync commit if needed.
3. `/cleanup-feature` runs `--check` as a pre-merge gate; drift blocks the merge.
4. `/validate-feature` exposes a `--phase docs` selector that runs `--check`.

#### Scenario: Skill inventory scan

**WHEN** the skill is invoked
**THEN** it SHALL scan every directory under `skills/` for a `SKILL.md` file
**AND** SHALL parse each frontmatter for `name`, `description`, `user_invocable`, `triggers`, `related`
**AND** SHALL emit a warning to stderr for any `SKILL.md` whose frontmatter cannot be parsed
**AND** SHALL skip the unparseable file without aborting the overall scan

#### Scenario: Spec inventory scan

**WHEN** the skill is invoked
**THEN** it SHALL scan every directory under `openspec/specs/` for a `spec.md` file
**AND** SHALL count `### Requirement:` headers per spec
**AND** SHALL capture the spec title from the first H1 or frontmatter

#### Scenario: Docs inventory scan

**WHEN** the skill is invoked
**THEN** it SHALL list every `*.md` file under `docs/` (non-recursive)
**AND** SHALL extract a one-line summary from each file's frontmatter `description:` or first paragraph
**AND** SHALL list immediate subdirectories under `docs/` with their `README.md` summary if present

#### Scenario: Generated block round-trip

**WHEN** the skill runs against a clean target file with valid markers
**THEN** the rendered content SHALL appear between the matching `begin`/`end` markers
**AND** a subsequent run with no filesystem changes SHALL produce a byte-identical file

#### Scenario: Preserves prose verbatim

**WHEN** the skill runs against a target file with hand-authored prose surrounding the markers
**THEN** every byte outside the marker pairs SHALL be unchanged after the run
**AND** the order, count, and identity of marker pairs SHALL be unchanged

#### Scenario: README blocks rendered

**WHEN** the skill renders `README.md`
**THEN** the `docs:project-tree` block SHALL contain the top-level directory listing
**AND** the `docs:specs-table` block SHALL contain the headline specs table
**AND** the `docs:skill-summary` block SHALL contain a count plus a link to `docs/skills-catalogue.md`

#### Scenario: CLAUDE.md blocks rendered

**WHEN** the skill renders `CLAUDE.md`
**THEN** the `docs:documentation-index` block SHALL contain categorized bullet lists of all `docs/*.md` files and subdirectories

#### Scenario: Catalogue blocks rendered

**WHEN** the skill renders `docs/skills-catalogue.md`
**THEN** the `docs:quick-map-counts` block SHALL contain accurate per-group skill counts
**AND** the `docs:skill-tables` block SHALL contain per-group tables of skills with name, summary, invoke trigger, and user_invocable marker

#### Scenario: Slash mentions resolve

**WHEN** the skill runs the cross-link check
**THEN** every `/skill-name` mention in `README.md`, `CLAUDE.md`, `docs/skills-workflow.md`, and `docs/skills-catalogue.md` SHALL resolve to an existing `skills/<name>/SKILL.md`
**AND** unresolved mentions SHALL be reported as `broken_links` in the JSON report

#### Scenario: Doc links resolve

**WHEN** the skill runs the cross-link check
**THEN** every `docs/*.md` link in the same four files SHALL resolve to an existing file
**AND** unresolved links SHALL be reported as `broken_links` in the JSON report

#### Scenario: Pre-commit blocks drift

**WHEN** a commit stages a new file under `skills/`, `openspec/specs/`, or `docs/` without running the sync
**THEN** the pre-commit hook SHALL run the skill in `--check` mode
**AND** the hook SHALL exit non-zero, blocking the commit
**AND** the hook SHALL print a one-line instruction to run `/update-documentation`

#### Scenario: Post-merge syncs

**WHEN** a merge brings in changes under `skills/`, `openspec/specs/`, or `docs/`
**THEN** the post-merge hook SHALL run the skill in write mode
**AND** SHALL create a `chore(docs): sync generated blocks after merge` commit if any target file changed

#### Scenario: Cleanup-feature blocks drift

**WHEN** `/cleanup-feature` runs its pre-merge phase
**THEN** it SHALL invoke `/update-documentation --check`
**AND** SHALL block the merge if drift is detected
**AND** SHALL surface the broken_links and drift_blocks from the JSON report

#### Scenario: Validate-feature docs phase

**WHEN** `/validate-feature --phase docs` is invoked
**THEN** it SHALL run `/update-documentation --check`
**AND** SHALL return the report alongside the other validation phase outputs

#### Scenario: Exit code semantics

**WHEN** the skill is invoked in `--check` mode and no drift exists
**THEN** it SHALL exit `0`

**WHEN** the skill is invoked in `--check` mode and drift exists
**THEN** it SHALL exit `2`

**WHEN** the skill is invoked in write mode and changes are applied successfully
**THEN** it SHALL exit `0`

**WHEN** the skill encounters a filesystem or parse error preventing any output
**THEN** it SHALL exit `1` with a diagnostic to stderr

#### Scenario: JSON report schema

**WHEN** the skill completes a run
**THEN** it SHALL write `docs/architecture-analysis/documentation-sync-report.json` containing fields: `skill_count`, `spec_count`, `doc_count`, `drift_blocks` (list of `{target, block_id}`), `broken_links` (list of `{source_file, link, target}`)
