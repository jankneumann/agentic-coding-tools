## ADDED Requirements

### Requirement: Schema-Derived Review Prompt

Every review prompt the dispatcher, `converge()`, plan/implementation review
skills, or PR vendor-review path sends SHALL be built from the canonical
`review-findings.schema.json` via a shared helper. The prompt SHALL list every
required finding field and every enum value. The prompt SHALL NOT carry a
hand-copied field list that can drift from the schema.

#### Scenario: Converge prompt includes axis and severity

- **WHEN** `build_review_prompt()` is invoked
- **THEN** the returned prompt SHALL include the fields `axis` and `severity`
- **AND** SHALL include the enum values defined on those fields in
  `openspec/schemas/review-findings.schema.json`

#### Scenario: Skill prompt uses the same helper

- **WHEN** a plan or implementation review skill writes `review-prompt.md`
- **THEN** the required-field list in that prompt SHALL be produced by the
  same helper `vendor_review.py` uses
- **AND** a test SHALL fail if the helper's required-field set and the schema
  required-field set differ

### Requirement: Finding Coercion Before Validation

The dispatcher SHALL apply a contracted alias table to a parsed findings
payload before schema validation. Coercion SHALL NOT invent findings. Coercion
SHALL be logged. After coercion, schema validation remains mandatory and
fail-closed.

#### Scenario: Known type alias is coerced

- **WHEN** a vendor finding has `"type": "bug"`
- **THEN** coercion SHALL set `type` to `correctness`
- **AND** the wrapper SHALL record that a coercion occurred
- **AND** schema validation SHALL then pass for that field

#### Scenario: Iterate-on-plan axis rejected as type is coerced

- **WHEN** a vendor finding has `"type": "completeness"` or `"type": "testability"`
- **THEN** coercion SHALL replace `type` with a legal review-findings `type`
  enum value and SHALL set `axis` to `architecture` (completeness) or
  `correctness` (testability) when `axis` is missing
- **AND** schema validation SHALL NOT fail solely because of the original
  illegal `type`

#### Scenario: Missing severity filled from criticality

- **WHEN** a finding has `criticality` but omits `severity`
- **THEN** coercion SHALL fill `severity` from the contracted map
- **AND** the reverse fill SHALL apply when `severity` is present and
  `criticality` is omitted

#### Scenario: Unknown enum still fails closed

- **WHEN** a finding has `"type": "not-a-real-type"` that is not in the alias
  table
- **THEN** schema validation SHALL fail
- **AND** the dispatcher SHALL proceed to the repair retry rather than
  accepting the payload

### Requirement: Schema Repair Retry

On parse failure or post-coercion schema failure, the dispatcher SHALL
re-dispatch that vendor exactly once with the validator (or parse) errors and
an instruction to emit only a findings JSON object. A second failure SHALL
mark the vendor unsuccessful. The retry SHALL use the same timeout budget as
the original dispatch.

#### Scenario: Invalid JSON is repaired

- **WHEN** the first dispatch returns stdout that does not parse as a findings
  object
- **THEN** the dispatcher SHALL send one repair dispatch whose prompt includes
  the parse error
- **AND** if the repair stdout parses and validates, the vendor SHALL be
  `success=True`

#### Scenario: Repair is not unbounded

- **WHEN** the repair dispatch also fails to parse or validate
- **THEN** the vendor SHALL be `success=False`
- **AND** the dispatcher SHALL NOT send a third dispatch for that vendor in
  that round

### Requirement: Raw Vendor Output Sidecar

The dispatcher and in-process `converge()` checkpoint SHALL persist the full
stdout (and stderr if non-empty) of every vendor dispatch next to the findings
file, for both success and failure. The sidecar SHALL NOT be truncated to 500
characters.

#### Scenario: Failed dispatch keeps full stdout

- **WHEN** a vendor returns invalid JSON longer than 500 characters
- **THEN** a sidecar file under the output / checkpoint directory SHALL contain
  the complete stdout
- **AND** the `ReviewResult.error` message MAY still be a short summary

#### Scenario: Successful dispatch also keeps stdout

- **WHEN** a vendor returns valid findings
- **THEN** the sidecar SHALL still be written
- **AND** the findings file SHALL still be written as today

### Requirement: Per-Vendor Dispatch Timeout Budget

`dispatch_and_wait` and `CliVendorAdapter.dispatch` SHALL take a per-vendor
timeout from a versioned budget table. `converge()` SHALL pass that budget (or
an explicit override) into `dispatch_and_wait` and SHALL NOT rely on the
function's default `timeout_seconds=300`. A CLI `--timeout` flag SHALL override
the table for every vendor in that invocation.

#### Scenario: Converge passes a timeout

- **WHEN** `converge()` dispatches a review round
- **THEN** the call to `dispatch_and_wait` SHALL include a `timeout_seconds`
  argument derived from the budget table or an override
- **AND** it SHALL NOT omit the argument

#### Scenario: Claude uses a longer budget than the historical 300s default

- **WHEN** a `claude_code` review is dispatched with the default table
- **THEN** the subprocess timeout SHALL be at least 720 seconds

#### Scenario: CLI override wins

- **WHEN** the dispatcher CLI is invoked with `--timeout 120`
- **THEN** every vendor in that invocation SHALL be killed at 120 seconds

### Requirement: Judgment Ingest for Model Reviewers

Findings produced by CLI or SDK model-review dispatch SHALL be ingested with
`evidence_class=judgment` unless the caller explicitly declares the ingest as
deterministic. A findings payload SHALL NOT be allowed to promote itself to
`deterministic`. Deterministic emitters (tests, linters, playwright-validator,
gen-eval) SHALL pass `evidence_class=deterministic` at ingest.

#### Scenario: CLI review findings are judgment

- **WHEN** `CliVendorAdapter.dispatch` returns a valid findings object
- **THEN** each finding that the caller did not declare deterministic SHALL
  have `evidence_class` equal to `judgment` after ingest

#### Scenario: Payload cannot self-promote

- **WHEN** a model returns `"evidence_class": "deterministic"`
- **AND** the caller did not declare deterministic ingest
- **THEN** the ingested finding SHALL still be `judgment`

### Requirement: Empty Or Blinded Review Is Not Success

A vendor dispatch SHALL be `success=True` only when a findings object parsed
and validated (after coercion and optional repair). An empty `findings` array
SHALL NOT count as success if the elapsed time is below a configured floor
(default 15 seconds) or if the raw output classified as AUTH, UNAVAILABLE, or
CAPACITY.

#### Scenario: Fast empty findings do not meet quorum

- **WHEN** a vendor returns `{"findings": []}` in under 15 seconds
- **THEN** `success` SHALL be false
- **AND** the vendor SHALL NOT increment `quorum_received`

#### Scenario: Timeout does not produce a successful empty review

- **WHEN** a vendor is killed by the timeout
- **THEN** `success` SHALL be false
- **AND** if at least two other vendors returned valid findings, synthesis
  SHALL proceed
- **AND** `converge()` SHALL NOT return `reason="quorum_lost"` solely because
  of that timeout

## MODIFIED Requirements

### Requirement: Vendor Timeout Enforcement

The `ReviewDispatcher` SHALL enforce a configurable **per-vendor** timeout from
the dispatch-timeout budget table (default table values replace the previous
global 300-second default) and terminate timed-out processes. The result SHALL
be marked timed out with an error message and `error_class=transient`. A timed
out vendor SHALL NOT be treated as a successful review.

#### Scenario: Vendor times out

- **GIVEN** a vendor review is dispatched with that vendor's budget (or an
  override)
- **WHEN** the vendor process exceeds the timeout
- **THEN** the process is terminated
- **AND** the result is marked as timed out with an error message
- **AND** `success` is false

### Requirement: Vendor Failure Resilience

If a vendor fails (timeout, invalid output after repair, crash, blinded-empty,
classified AUTH/UNAVAILABLE/CAPACITY), the system SHALL skip that vendor's
findings and proceed with available **valid** results. A failed vendor SHALL
not be recorded as a successful empty review.

#### Scenario: One vendor fails

- **GIVEN** Codex and grok are dispatched
- **AND** Codex times out
- **WHEN** results are collected
- **THEN** grok's findings are used
- **AND** the consensus report notes Codex's failure
- **AND** Codex does not contribute `findings: []` as a successful vote

### Requirement: Review Dispatcher Protocol

The system SHALL provide a `ReviewDispatcher` that can invoke review skills on
different AI vendor CLIs (Claude Code, Codex, antigravity, grok, pi). Parsed
stdout SHALL be coerced, schema-validated, and optionally repair-retried
before it is written as a findings file.

#### Scenario: Dispatch review to Codex

- **GIVEN** a completed implementation package
- **WHEN** the orchestrator dispatches a review to Codex
- **THEN** the Codex CLI is invoked with the schema-derived review skill prompt
  and artifact paths
- **AND** a structured findings JSON file is produced at the expected output
  path if Codex returns a valid (after coercion/repair) document

#### Scenario: Dispatch review to grok

- **GIVEN** a completed implementation package
- **WHEN** the orchestrator dispatches a review to grok
- **THEN** the grok CLI is invoked with the review skill prompt and artifact
  paths
- **AND** the invocation SHALL use `--output-format json` so the result is a
  structured envelope rather than scraped stdout
- **AND** a structured findings JSON file is produced at the expected output
  path
