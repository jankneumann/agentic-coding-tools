## ADDED Requirements

### Requirement: Sync Window Declarations

The trust posture contract front matter SHALL accept an optional top-level
`sync_windows` list. Each entry SHALL declare exactly these fields:

- `id`: a non-empty kebab-case string, unique within the list
- `cadence`: a five-field cron expression, interpreted in UTC
- `skills`: a non-empty list drawn from `merge-pull-requests`, `update-specs`,
  and `cleanup-feature`
- `allowed_sources`: a non-empty list of PR origins drawn from `openspec`,
  `sentinel`, `bolt`, `palette`, `jules`, `codex`, `dependabot`, `renovate`, and
  `other`
- `auto_merge_ceiling`: one of `none`, `automation`, `plan`, or
  `implementation`, ordered from least to most permissive

The loader SHALL reject an unknown field, a missing field, an unknown skill,
source, or ceiling, a malformed cadence, or a duplicate `id` as a validation
error. When `sync_windows` is absent or empty, the posture SHALL declare no sync
windows (fail-closed). The posture digest SHALL cover the declared sync windows,
and a posture that declares none SHALL produce the same digest as it did before
this field existed.

The loader SHALL expose an authorization check that, given a window id and a
sync-point skill, returns the declared window only when the window exists and
lists that skill, and otherwise fails with an error naming the missing
declaration.

#### Scenario: Absent sync windows declare nothing

- **WHEN** a trust posture is loaded whose front matter omits `sync_windows`, or
  no contract file exists
- **THEN** the posture SHALL report no sync windows
- **AND** the authorization check SHALL fail for every window id and skill

#### Scenario: Declared window loads and authorizes its skills

- **WHEN** a trust posture declares a valid sync window listing
  `merge-pull-requests`
- **THEN** the loader SHALL resolve the window with its cadence, skills,
  allowed sources, and auto-merge ceiling
- **AND** the authorization check SHALL return that window for
  `merge-pull-requests`
- **AND** the authorization check SHALL fail for a skill the window does not list

#### Scenario: Malformed window is rejected

- **WHEN** a sync window has an unknown field, omits a required field, names an
  unknown skill, source, or ceiling, has a cadence that is not five cron fields,
  or repeats another window's `id`
- **THEN** validation SHALL fail with an error naming the window and the problem

#### Scenario: Auto-merge ceiling orders PR kinds

- **WHEN** a window's `auto_merge_ceiling` is compared with a PR kind
- **THEN** `none` SHALL permit no kind
- **AND** `automation` SHALL permit only `automation`
- **AND** `plan` SHALL permit `automation` and `plan`
- **AND** `implementation` SHALL permit `automation`, `plan`, and
  `implementation`

#### Scenario: Digest is unchanged without windows and changes with them

- **WHEN** the posture digest is computed for a posture that declares no sync
  windows
- **THEN** it SHALL equal the digest computed over the `gates` map alone
- **AND** adding or editing a declared sync window SHALL change the digest
