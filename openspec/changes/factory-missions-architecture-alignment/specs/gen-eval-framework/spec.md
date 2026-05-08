# gen-eval-framework Spec Delta — Factory Missions Architecture Alignment

## ADDED Requirements

### Requirement: OpenSpec-Seeded Scenario Generation

The gen-eval framework SHALL accept an `--openspec-change <change-id>` flag in `cli-augmented` mode. When set, the framework MUST walk `openspec/changes/<change-id>/specs/**/*.md`, parse Requirement and Scenario blocks (WHEN/THEN/AND structure), and pass them as additional constraints to the scenario-generation prompt alongside the interface descriptor.

The framework MUST preserve the source location (file path + line number) of each parsed scenario so generated test scenarios can be traced back to the originating Requirement.

The framework MUST handle the absence of the change directory gracefully: log a warning and proceed with descriptor-only generation, rather than failing.

When invoked without the `--openspec-change` flag, the framework MUST behave identically to its prior behavior (no regression).

#### Scenario: OpenSpec scenarios augment cli-augmented prompt

- **GIVEN** an interface descriptor at `evaluation/gen_eval/descriptors/api.yaml`
- **AND** an OpenSpec change at `openspec/changes/example-feature/specs/example/spec.md` with two `### Requirement` blocks containing three total `#### Scenario` blocks in WHEN/THEN form
- **WHEN** the framework runs with `--mode cli-augmented --openspec-change example-feature`
- **THEN** the cli-augmented prompt sent to the configured CLI tool MUST include all three scenarios as constraints
- **AND** each scenario MUST be tagged with its source `<file>:<line-range>` in the prompt
- **AND** the generated `Scenario` Pydantic objects MUST include a `source.openspec_scenario` field populated with that file:line reference

#### Scenario: Missing OpenSpec change degrades to descriptor-only

- **GIVEN** an interface descriptor exists
- **AND** no directory at `openspec/changes/<id>/`
- **WHEN** the framework runs with `--mode cli-augmented --openspec-change <id>`
- **THEN** the framework MUST log a warning naming the missing path
- **AND** the framework MUST continue with descriptor-only scenario generation
- **AND** the framework MUST exit with the same status code as a descriptor-only run

#### Scenario: Backward compatibility without flag

- **GIVEN** any interface descriptor
- **WHEN** the framework runs with `--mode cli-augmented` and no `--openspec-change` flag
- **THEN** the framework MUST behave identically to the pre-change cli-augmented mode
- **AND** the generated prompt MUST NOT include any OpenSpec content
- **AND** generated `Scenario` objects MUST NOT include the `source.openspec_scenario` field

---

### Requirement: Behavioral Findings Schema Conformance

When invoked with `--report-format json` or `--report-format both`, the gen-eval framework SHALL emit a `findings-gen-eval.json` file conforming to the `review-findings.schema.json` schema defined under `openspec/schemas/`.

Each finding emitted by gen-eval MUST use `type: behavioral_failure` and MUST populate the schema's required `severity`, `description`, and `location` fields.

When the failing scenario originated from an OpenSpec scenario (per the OpenSpec-Seeded Scenario Generation requirement), the finding's `location` MUST reference the OpenSpec scenario's `file:line-range`, not the gen-eval scenario YAML.

#### Scenario: Findings file produced and schema-valid

- **GIVEN** the framework runs with `--report-format json` and produces 2 failing scenarios and 5 passing scenarios
- **WHEN** the run completes
- **THEN** a file `findings-gen-eval.json` MUST exist in the `--output-dir`
- **AND** the file MUST validate against `openspec/schemas/review-findings.schema.json`
- **AND** the file MUST contain exactly 2 finding entries (one per failing scenario), all with `type: behavioral_failure`

#### Scenario: OpenSpec-sourced finding points back to spec

- **GIVEN** a failing scenario whose `source.openspec_scenario` is `openspec/changes/foo/specs/api/spec.md:42-50`
- **WHEN** the framework emits the corresponding finding to `findings-gen-eval.json`
- **THEN** the finding's `location.file` MUST be `openspec/changes/foo/specs/api/spec.md`
- **AND** the finding's `location.line_start` MUST be 42 and `line_end` MUST be 50

---

### Requirement: Browser-Driving Behavioral Validation via Playwright CLI

The gen-eval framework SHALL support a `playwright` validator pipeline that drives a deployed frontend via the Playwright CLI (`npx playwright test --reporter=json`). The pipeline MAY be packaged either as a new gen-eval mode (`--mode playwright`) or as a peer skill (`skills/playwright-validator/`); the design.md decision will resolve this. Either packaging MUST satisfy the requirements below.

The pipeline MUST accept a frontend descriptor YAML conforming to a frontend descriptor schema (`contracts/frontend-descriptor.schema.json` introduced by this change), covering: base URL, auth flow steps, selector aliases, and a browser matrix (any subset of `chromium`, `firefox`, `webkit`).

The pipeline MUST generate Playwright test scripts from OpenSpec scenarios (per the OpenSpec-Seeded Scenario Generation requirement) plus the frontend descriptor's selector aliases, then execute the generated scripts via the Playwright CLI.

The pipeline MUST emit findings conforming to the Behavioral Findings Schema Conformance requirement, with one finding per failing Playwright assertion. The finding's `location` MUST reference the originating OpenSpec scenario when one exists.

The pipeline MUST exit non-zero if any Playwright test fails, but the calling skill MAY treat the failure as non-blocking (consistent with the existing template-only gen-eval phase's non-critical posture).

#### Scenario: Sample frontend exercise validates the full path

- **GIVEN** the sample frontend at `evaluation/gen_eval/fixtures/sample-frontend/index.html`
- **AND** the sample frontend descriptor at `evaluation/gen_eval/descriptors/sample-frontend.yaml`
- **AND** an OpenSpec change with at least one `#### Scenario` block describing a click-and-assert flow
- **WHEN** the Playwright pipeline runs with `--mode playwright --openspec-change <id>` (or the skill-equivalent invocation)
- **THEN** the pipeline MUST start a local HTTP server for the sample frontend
- **AND** the pipeline MUST generate a Playwright test script encoding the OpenSpec scenario's WHEN/THEN steps
- **AND** the pipeline MUST execute `npx playwright test --reporter=json` against the generated script
- **AND** the pipeline MUST emit `findings-gen-eval.json` (or `findings-playwright.json`) conforming to `review-findings.schema.json`

#### Scenario: Browser matrix executes all configured browsers

- **GIVEN** a frontend descriptor with `browsers: [chromium, firefox]`
- **WHEN** the Playwright pipeline runs
- **THEN** the pipeline MUST execute the test script in both Chromium and Firefox
- **AND** findings from both browsers MUST appear in the emitted findings file
- **AND** each finding MUST include a `metadata.browser` field identifying which browser produced it

#### Scenario: Missing Playwright CLI degrades cleanly

- **GIVEN** a project where `npx playwright` is not available on PATH (or playwright is not installed)
- **WHEN** the Playwright pipeline is invoked
- **THEN** the pipeline MUST log a clear error naming the missing dependency and the install command (`npx playwright install`)
- **AND** the pipeline MUST exit with a non-zero status code distinguishable from a test failure (e.g., 127 for missing dependency)
- **AND** the pipeline MUST NOT emit a findings file
