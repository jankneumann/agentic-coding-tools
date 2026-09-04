# evaluation-framework — Delta

## ADDED Requirements

### Requirement: Archive Replay Task Conversion

The system SHALL convert an archived OpenSpec change into a Harbor task directory
containing an instruction derived from the change's `proposal.md`, a container
environment definition checked out at the change's pre-implementation commit, and a
verifier — while withholding the original implementation diff from the task
environment.

#### Scenario: convert an archived change

- WHEN the converter is invoked on `openspec/changes/archive/<date>-<id>/`
- THEN it SHALL emit a task directory with `task.toml`, `instruction.md`, an
  `environment/` definition pinned to the pre-implementation commit, and a
  `tests/` verifier that writes a reward in Harbor's expected format
- AND the original implementation diff SHALL NOT be present anywhere in the task
  environment or instruction

#### Scenario: conversion is reproducible

- WHEN the converter is re-run on the same archived change at the same repo state
- THEN the emitted task directory SHALL be identical to the prior run apart from
  generation timestamps

#### Scenario: unconvertible change is excluded, not degraded

- WHEN the converter cannot derive a deterministic (tier-1 or tier-2) verifier for
  an archived change
- THEN it SHALL exclude that change from the corpus with a recorded exclusion
  reason rather than emitting a judge-only task by default

### Requirement: Deterministic Change-Level Task Type

The converter SHALL assign each converted task exactly one `task_type` from the
`package_kind` vocabulary by a deterministic reduction over the source change's
declared work packages, and SHALL record on every emitted trial both how that value
was derived and the per-kind weights the reduction consumed. Out-of-vocabulary
`package_kind` values SHALL NOT be remapped onto vocabulary values.

#### Scenario: single declared kind

- WHEN every in-vocabulary `package_kind` declared by the source change's
  `work-packages.yaml` is the same value
- THEN `task_type` SHALL be that value and the trial SHALL carry
  `task_type_source: declared`

#### Scenario: multiple declared kinds reduce by weight

- WHEN the source change declares two or more distinct in-vocabulary `package_kind`
  values
- THEN `task_type` SHALL be the kind with the greatest summed `metadata.loc_estimate`
  across the declaring packages, ties broken by the fixed precedence
  `algorithm > data_model > migration > integration > crud > config`
- AND the trial SHALL carry `task_type_source: declared_dominant` and a
  `task_type_mix` of the normalized per-kind weights

#### Scenario: missing size estimates fall back to package count

- WHEN no package in the source change declares `metadata.loc_estimate`
- THEN each declaring package SHALL contribute equal weight so the reduction yields a
  package-count plurality rather than failing

#### Scenario: legacy kinds are excluded, not remapped

- WHEN a source change declares a `package_kind` outside the controlled vocabulary
  (for example the legacy value `feature`)
- THEN that package SHALL contribute no weight to the reduction, the value SHALL be
  recorded on the trial as an excluded legacy kind, and it SHALL NOT be rewritten to
  any vocabulary value

#### Scenario: no usable declaration falls through to inference

- WHEN the source change has no `work-packages.yaml`, declares no `package_kind`, or
  every kind it declares is out of vocabulary
- THEN `task_type` SHALL be inferred deterministically from the change's delta-spec
  capability and the trial SHALL carry `task_type_source: inferred`
- AND re-running the inference on the same change SHALL yield the same value

#### Scenario: unmappable capability is excluded, not guessed

- WHEN inference cannot map a change's delta-spec capability to exactly one
  vocabulary value
- THEN the change SHALL be excluded from the corpus with a recorded exclusion reason
  rather than assigned an arbitrary `task_type`

### Requirement: Sealed Benchmark Corpus Manifest

The system SHALL partition the converted archive corpus into a development split and
a sealed holdout split, recorded in a checksummed manifest, and SHALL refuse to
execute holdout tasks unless an explicit decision-run flag is provided.

#### Scenario: manifest generation

- WHEN the manifest generator runs over the current archive
- THEN it SHALL produce a dev/holdout assignment with the holdout biased toward
  entries dated after 2026-05-01, plus a SHA-256 checksum over the assignment

#### Scenario: holdout protection

- WHEN a sweep run requests a task assigned to the holdout split without the
  decision-run flag
- THEN the runner SHALL refuse the run and report the sealing violation

#### Scenario: manifest tamper detection

- WHEN the manifest content does not match its recorded checksum
- THEN any runner or importer consuming it SHALL fail closed

### Requirement: Combo Sweep Execution

The system SHALL execute benchmark trials over a configured matrix of combos, where a
combo is the tuple `{vendor, model, thinking, harness}`, recording every trial with
its combo, task identifier, task_type, attempt index, reward, token usage, duration,
and cost fields.

#### Scenario: sweep over configured combos

- WHEN a sweep job is started with a combo matrix and a task list from the dev split
- THEN the runner SHALL execute each (task, combo) pair for the configured number of
  attempts and persist one trial record per execution carrying the full combo tuple

#### Scenario: five-vendor coverage

- WHEN the v1 pilot sweep configuration is loaded
- THEN it SHALL include combos for all five configured vendors (claude_code, codex,
  grok, antigravity, pi), using Harbor built-in agent adapters where available and
  custom adapters otherwise

#### Scenario: podman execution

- WHEN the runner provisions trial environments on the local host
- THEN it SHALL target podman's Docker-compatible API socket and SHALL NOT require
  a Docker Engine installation

### Requirement: Sweep Budget Enforcement

The system SHALL enforce a per-job USD spend cap for metered vendors and a per-vendor
trial-rate throttle for subscription vendors, refusing to *start* any trial that could
carry the job past either bound. The metered cap SHALL be enforced against a
conservative pre-launch cost estimate for the candidate trial plus the estimates of
all metered trials still in flight, not against completed spend alone, so that the
cap bounds the job's worst case rather than its already-realized cost.

#### Scenario: admission accounts for in-flight trials

- WHEN the runner considers starting a metered trial
- THEN it SHALL admit the trial only if completed spend plus the reserved estimates of
  all in-flight metered trials plus a conservative upper-bound estimate for the
  candidate trial is within the configured cap (default 50 USD)
- AND the estimate SHALL be derived from the combo's per-token pricing and the trial's
  configured maximum token budget with the configured safety factor applied

#### Scenario: metered cap reached

- WHEN admitting a metered trial would carry the job's reserved-plus-spent total past
  the configured cap
- THEN the runner SHALL start no further metered-vendor trials in that job and SHALL
  record the cap event in the job summary together with the spent, reserved, and
  estimated amounts that produced the refusal

#### Scenario: reservation released on completion

- WHEN a metered trial completes
- THEN its reservation SHALL be released and its actual cost SHALL be added to the
  job's completed spend, freeing headroom for subsequent admissions

#### Scenario: estimate overrun is recorded

- WHEN a completed metered trial's actual cost exceeds the estimate reserved for it
- THEN the runner SHALL record a cost-estimate-overrun event in the job summary rather
  than silently absorbing the difference

#### Scenario: subscription throttle

- WHEN a subscription vendor has reached its configured max trials per window
- THEN the runner SHALL defer further trials for that vendor until the window resets

### Requirement: Deterministic-First Verifier Ladder

Verifiers SHALL score trials preferentially from executable checks (scenario-derived
tests and repository quality gates); LLM-judge scoring SHALL be opt-in per task,
blind to combo identity, and marked on the trial record.

#### Scenario: deterministic reward

- WHEN a task has scenario-derived tests available
- THEN the reward SHALL be computed from test outcomes and repo gates without any
  LLM-judge involvement

#### Scenario: judge blinding

- WHEN a judge-flagged task is scored
- THEN the judge input SHALL contain the diff and scenarios but no vendor, model,
  thinking, or harness identity, and the trial record SHALL carry `graded_by: judge`

### Requirement: Combo Scorecard

The system SHALL produce a scorecard aggregating trials per combo × task_type over
the dev split, reporting quality, cost (USD for metered vendors, token counts for
subscription vendors), latency, sample size, and variance.

#### Scenario: scorecard generation

- WHEN a sweep job completes
- THEN the scorecard generator SHALL emit a report with one row per
  (combo, task_type) including mean reward, reward variance, attempts count, token
  totals, cost fields, and mean duration

#### Scenario: small-sample marking

- WHEN a (combo, task_type) cell has fewer than 5 trials
- THEN the scorecard SHALL mark the cell as low-confidence
