## ADDED Requirements

### Requirement: Sync Window Declarations

The trust posture contract front matter SHALL accept an optional top-level
`sync_windows` list. Each entry SHALL declare exactly these fields:

- `id`: a kebab-case string matching `^[a-z0-9]+(-[a-z0-9]+)*$`, unique within
  the list
- `cadence`: a five-field cron expression, interpreted in UTC
- `skills`: a non-empty list drawn from `merge-pull-requests`, `update-specs`,
  and `cleanup-feature`
- `allowed_sources`: a non-empty list of PR origins drawn from `openspec`,
  `sentinel`, `bolt`, `palette`, `jules`, `codex`, `dependabot`, `renovate`, and
  `other` (the origins that `skills/shared/github_classifier.classify_pr`
  emits)
- `auto_merge_ceiling`: one of `none`, `automation`, `plan`, or
  `implementation`, ordered from least to most permissive

The loader SHALL reject, as a validation error, a `sync_windows` value that is
not a list, an entry that is not a mapping, an unknown field, a missing field,
an empty list field, a repeated value inside a list field, an unknown skill,
source, or ceiling, a malformed cadence, or a duplicate `id`. When
`sync_windows` is absent, `null`, or an empty list, the posture SHALL declare no
sync windows (fail-closed). The posture digest SHALL cover the declared sync
windows independent of their declaration order, and a posture that declares
none SHALL produce the same digest as it did before this field existed.

A ceiling SHALL permit a PR kind only when the kind is one of `automation`,
`plan`, or `implementation` and ranks at or below the ceiling; any other kind,
including an unclassified one, SHALL NOT be permitted.

The loader SHALL expose an authorization check that, given a window id and a
sync-point skill, returns the declared window only when the window exists and
lists that skill, and otherwise fails with an error naming the missing
declaration.

#### Scenario: Absent sync windows declare nothing

- **WHEN** a trust posture is loaded whose front matter omits `sync_windows`,
  sets it to `null` or `[]`, or no contract file exists
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

- **WHEN** a sync window has an unknown field, omits a required field, has an
  empty or repeated-value list field, names an unknown skill, source, or
  ceiling, has a cadence that is not five cron fields, or repeats another
  window's `id`
- **THEN** validation SHALL fail with an error naming the window and the problem
- **AND** the loader SHALL NOT return a posture that omits the malformed window

#### Scenario: Malformed sync_windows container is rejected

- **WHEN** `sync_windows` is present but is not a list, or one of its entries is
  not a mapping
- **THEN** validation SHALL fail with an error naming `sync_windows` and the
  offending entry index

#### Scenario: Auto-merge ceiling orders PR kinds

- **WHEN** a window's `auto_merge_ceiling` is compared with a PR kind
- **THEN** `none` SHALL permit no kind
- **AND** `automation` SHALL permit only `automation`
- **AND** `plan` SHALL permit `automation` and `plan`
- **AND** `implementation` SHALL permit `automation`, `plan`, and
  `implementation`
- **AND** no ceiling SHALL permit an unknown or unclassified kind

#### Scenario: Digest is unchanged without windows and changes with them

- **WHEN** the posture digest is computed for a posture that declares no sync
  windows
- **THEN** it SHALL equal the digest computed over the `gates` map alone
- **AND** adding or editing a declared sync window SHALL change the digest
- **AND** reordering declared windows, or reordering values inside a window's
  list fields, SHALL NOT change the digest
