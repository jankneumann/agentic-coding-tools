## ADDED Requirements

### Requirement: Missing Validation Report Blocks Readiness

The expedite readiness check SHALL report the `validation_report` check as `fail`
when no `validation-report.md` exists at any probed path, and the overall verdict
SHALL be BLOCKED (exit code 1). The failing check's `detail` MUST name every path
that was probed, and its `action` MUST direct the operator to run `/validate-feature`.
A `skip` status MUST NOT be produced for the `validation_report` check.

The change directory passed to the pre-merge gate SHALL be derived from the change
id as `<repo-root>/openspec/changes/<change-id>`, not from the location of the
report file, so that a report found under `reports/` or in a worktree is evaluated
with the change's declared metadata.

<!-- Scenario ID: expedite.missing-report-blocks -->
#### Scenario: No validation report at any probed path

- **WHEN** `expedite.py <change-id>` runs and no `validation-report.md` exists at
  any of the three probed paths
- **THEN** the `validation_report` check status is `fail`
- **AND** its detail names each probed path
- **AND** its action contains `/validate-feature`
- **AND** the verdict is BLOCKED and the process exits 1

<!-- Scenario ID: expedite.passing-report-ready -->
#### Scenario: A passing report is READY regardless of deployable surface

- **WHEN** a `validation-report.md` whose hard gates pass exists for the change
- **AND** no other check fails
- **THEN** the verdict is READY and the process exits 0

<!-- Scenario ID: expedite.change-dir-from-id -->
#### Scenario: Report found under reports/ still reads the change directory

- **WHEN** the only report is at `openspec/changes/<change-id>/reports/validation-report.md`
- **THEN** the pre-merge gate is invoked with `change_dir` equal to
  `openspec/changes/<change-id>`

### Requirement: Recorded Override for a Missing Validation Report

The expedite readiness check SHALL accept `--accept-missing-validation "<reason>"`.
When the flag is given and no validation report exists, the `validation_report`
check SHALL report `pass` with a detail that begins
`OVERRIDE — no validation report accepted: ` followed by the reason, and the JSON
verdict SHALL include an `overrides` list whose entries name the overridden check
and carry the reason. The JSON verdict MUST always include the `overrides` key,
empty when no override applied. An empty or whitespace-only reason MUST be rejected
with exit code 2 before any check runs. When a validation report does exist, the
flag MUST NOT change the check's outcome and MUST NOT add an `overrides` entry.

<!-- Scenario ID: expedite.override-records-reason -->
#### Scenario: Override with a reason makes the missing report pass visibly

- **WHEN** `expedite.py <change-id> --accept-missing-validation "docs-only change" --json`
  runs and no validation report exists
- **THEN** the process exits 0 (assuming no other check fails)
- **AND** the `validation_report` detail begins with `OVERRIDE — no validation report accepted: docs-only change`
- **AND** `overrides` contains one entry with `check` equal to `validation_report`
  and `reason` equal to `docs-only change`

<!-- Scenario ID: expedite.override-empty-reason-rejected -->
#### Scenario: Empty override reason is rejected

- **WHEN** `expedite.py <change-id> --accept-missing-validation "  "` runs
- **THEN** the process exits 2
- **AND** no verdict is printed

<!-- Scenario ID: expedite.override-ignored-when-report-exists -->
#### Scenario: Override does not mask a failing report

- **WHEN** a validation report exists whose hard gates fail
- **AND** `--accept-missing-validation "<reason>"` is given
- **THEN** the `validation_report` check status is `fail`
- **AND** `overrides` is empty

### Requirement: Documented Status Table Matches the Code

The expedite SKILL.md status table SHALL list, for each check, the conditions
under which it fails, and a test MUST fail when the table and the code's
check-to-status mapping disagree. The SKILL.md MUST NOT state that a missing
validation report is non-blocking, and `skip` SHALL be documented as reachable
only for the rework-report check.

<!-- Scenario ID: expedite.skill-table-drift -->
#### Scenario: Drift between the SKILL table and the code fails a test

- **WHEN** the drift test parses the SKILL.md status table
- **THEN** every check name it lists is a check `expedite()` emits
- **AND** the `validation_report` (no file) row is present
- **AND** the only check for which the code can return `skip` is `rework_report`
- **AND** no SKILL.md sentence describes a missing validation report as non-blocking
