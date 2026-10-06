## ADDED Requirements

### Requirement: Multiplayer collaboration guide is published and linked

The repository SHALL contain `docs/guides/multiplayer-collaboration.md`, and both
`AGENTS.md` and `docs/guides/documentation.md` SHALL contain a relative markdown link that
resolves to that file. The guide MUST NOT contain a markdown link whose target lies under
`openspec/changes/` or `openspec/roadmaps/`, because archival relocates those directories.

#### Scenario: Guide is reachable from both entry points

- **WHEN** a reader opens `AGENTS.md` or `docs/guides/documentation.md`
- **THEN** each file contains a markdown link whose target, resolved relative to the
  linking file, is `docs/guides/multiplayer-collaboration.md`
- **AND** that file exists

#### Scenario: A missing or broken inbound link fails the guard

- **WHEN** either link is removed, or its target no longer resolves to an existing file
- **THEN** `skills/tests/multiplayer-collaboration/test_multiplayer_guide.py` fails with a
  message naming the file whose link is missing or broken

#### Scenario: A link into an archivable OpenSpec path fails the guard

- **WHEN** the guide contains a markdown link whose resolved target lies under
  `openspec/changes/` or `openspec/roadmaps/`
- **THEN** the guard test fails and names the offending link

### Requirement: Principles are stated with implementers

The guide SHALL state principles P1 through P10 under the heading `## Principles`, each
under a heading of the form `### P<n>. <title>`, in numeric order, where `<title>` is the
bold lead sentence of that principle in the `multiplayer-collaboration` roadmap proposal
without its trailing period. The guard test checks the `### P<n>. ` prefix and order;
title wording is checked in review, because the roadmap proposal moves on archival and a
test must not read it. Each principle section MUST contain an `**Existing:**` line and a
`**Planned:**` line that together name at least one implementer. Every link target on an
`**Existing:**` line MUST resolve, relative to `docs/guides/`, to an existing file or
directory. Every backticked token on a `**Planned:**` line MUST be a change-id whose
directory exists either under `openspec/changes/` or under `openspec/changes/archive/`.

#### Scenario: Every principle names a resolvable implementer

- **WHEN** the guard test parses the guide
- **THEN** it finds exactly ten principle headings, P1 to P10 in order
- **AND** each principle has at least one existing-mechanism link or planned change-id
- **AND** every cited path exists and every cited change-id resolves through
  `change_dir()`

#### Scenario: A principle with no implementer fails the guard

- **WHEN** a principle's `**Existing:**` and `**Planned:**` lines are both `none`
- **THEN** the guard test fails and names that principle

#### Scenario: A stale reference fails the guard

- **WHEN** a cited path is deleted, or a cited change-id is renamed or removed without
  being archived
- **THEN** the guard test fails and names the principle and the unresolved reference

#### Scenario: Archival of a cited change does not fail the guard

- **WHEN** a cited sibling change is archived to `openspec/changes/archive/<date>-<id>/`
- **THEN** the guard test still passes without any edit to the guide
- **AND** this is demonstrated by a guard-test case that builds a `tmp_path` repository
  containing only `openspec/changes/archive/2026-01-01-<id>/` and asserts that the
  test's change-id resolution helper accepts `<id>`

### Requirement: Single-principal assumption table

The guide SHALL contain, under the heading `## Single-principal assumptions`, a table
with the columns *Assumption*, *Where it lives*, *Team failure mode*, and *Addressed by*, holding one row for each of the eight single-principal
assumptions listed in the `multiplayer-collaboration` roadmap proposal. Each *Addressed
by* cell MUST contain at least one backticked token, and every backticked token in that
cell MUST be a change-id that resolves through `change_dir()` (active or archived).

#### Scenario: All eight assumptions are present and addressed

- **WHEN** the guard test parses the assumption table
- **THEN** it finds the four required columns and eight data rows
- **AND** each row's *Addressed by* cell names at least one resolvable change-id

#### Scenario: A dropped assumption fails the guard

- **WHEN** a row is removed or its *Addressed by* cell names no resolvable change-id
- **THEN** the guard test fails and names the affected assumption or the row count found

### Requirement: Solo and team mode vocabulary

The guide SHALL contain a section headed `## Modes` that defines *principal*, *solo mode*, and
*team mode*, each introduced as a bold term (`**Principal**`, `**Solo mode**`,
`**Team mode**`) at the start of its definition. Solo mode MUST be defined as the ownership resolver yielding exactly one
distinct human principal for the repository, including when `openspec/owners.yaml` is
absent, and team mode as two or more. The section MUST contain the sentence
"Solo mode adds no new prompts, gates, or PR checkpoints." and MUST state that every
repository is in solo mode until the `ownership-map` change ships. The section MUST also
state that in solo mode a capability MAY add passive output that requires no human action
(for example commit trailers or a PR ledger section), so that the guarantee is consistent
with sibling changes that add such output.

#### Scenario: Vocabulary and guarantee are present

- **WHEN** the guard test reads the `## Modes` section
- **THEN** it finds the bold terms `**Principal**`, `**Solo mode**`, and `**Team mode**`
- **AND** it finds the exact sentence "Solo mode adds no new prompts, gates, or PR
  checkpoints."
- **AND** it finds the change-id `ownership-map` and the phrase "passive output"

#### Scenario: Weakening the guarantee fails the guard

- **WHEN** the guarantee sentence is removed or reworded
- **THEN** the guard test fails with a message quoting the expected sentence

### Requirement: Per-skill solo and team behavior table

The guide SHALL contain, under the heading `## Skills in solo and team mode`, a table
with the columns *Skill*, *Solo mode*, *Team mode*, and *Delivered by*, with one row for each of: `plan-feature`, `implement-feature`,
`validate-feature`, `autopilot`, `autopilot-roadmap`, `supervise`, `cleanup-feature`,
`reconcile`, and `install.sh`. A *Solo mode* cell
for a skill whose solo behavior does not change MUST read "Unchanged"; any other *Solo
mode* cell MUST describe only passive output that requires no human action, consistent
with the solo-mode guarantee. No *Solo mode* cell may be empty. Whether a cell's content
is accurate is checked in review; the guard test checks only non-emptiness. Each *Delivered by*
cell MUST contain at least one backticked token, and every backticked token in that cell
MUST be a change-id that resolves through `change_dir()` (active or archived).

#### Scenario: Every affected skill has a row

- **WHEN** the guard test parses the per-skill table
- **THEN** it finds a row for each of the nine named skills
- **AND** every *Solo mode* and *Team mode* cell is non-empty
- **AND** every *Delivered by* cell names a resolvable change-id

#### Scenario: A missing skill row fails the guard

- **WHEN** a row for one of the named skills is removed
- **THEN** the guard test fails and names the missing skill

### Requirement: Guide states its authority and maintenance rule

The guide SHALL contain a section headed `## Authority and maintenance` stating that (a) the guide
is descriptive and OpenSpec specs are normative, so a disagreement between the guide and a
shipped spec is resolved in favor of the spec; (b) a team-mode behavior counts as shipped
once its delivering change is archived; and (c) a change that alters a behavior the guide
describes updates the affected guide rows in the same pull request.

#### Scenario: Precedence and maintenance rules are present

- **WHEN** the guard test reads the `## Authority and maintenance` section
- **THEN** it finds the phrases "specs are normative", "archived", and "same pull request"

#### Scenario: Section removal fails the guard

- **WHEN** the `## Authority and maintenance` heading is absent
- **THEN** the guard test fails naming the missing section

### Requirement: Guard test runs in the default CI sweep

The directory `skills/tests/multiplayer-collaboration/` SHALL be listed in `testpaths` in
`skills/pyproject.toml`, so that the guard test is collected by a `pytest` run with no
path argument and the CI-coverage guard (`skills/tests/ci_coverage/`) recognises the
directory as reached by CI.

#### Scenario: Guard test is collected without naming its directory

- **WHEN** `cd skills && .venv/bin/python -m pytest --collect-only -q` runs with no path
  argument
- **THEN** the collected test ids include `tests/multiplayer-collaboration/test_multiplayer_guide.py`

#### Scenario: An unregistered test directory fails the CI-coverage guard

- **WHEN** the `testpaths` entry for `tests/multiplayer-collaboration` is absent
- **THEN** `skills/tests/ci_coverage/test_ci_test_coverage.py` fails and names
  `tests/multiplayer-collaboration`
