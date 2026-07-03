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
- **THEN** the cli-augmented prompt sent to the configured CLI tool MUST contain a section titled exactly `# OpenSpec Scenarios (constraints)`
- **AND** within that section, exactly three scenario blocks MUST appear, each preceded by a line of the form `## <requirement-name> :: <scenario-name> [<file>:<line-start>-<line-end>]`
- **AND** the prompt MUST be capturable for assertion (gen-eval emits the resolved prompt to a debug-output file when invoked with `--debug-prompt-path <path>`)
- **AND** the generated `Scenario` Pydantic objects MUST include a `source.openspec_scenario` field populated with the exact `<file>:<line-start>-<line-end>` reference for the scenario that produced them

#### Scenario: change-id input rejected if it contains path separators or shell metacharacters

- **GIVEN** any interface descriptor exists
- **WHEN** the framework runs with `--openspec-change "../../../etc"` (or any value matching `[^a-zA-Z0-9_-]`)
- **THEN** the framework MUST exit with a non-zero status code
- **AND** the framework MUST log an error naming the regex constraint (`change-id MUST match ^[a-zA-Z0-9_-]+$`)
- **AND** the framework MUST NOT walk any directory or read any file based on the rejected input

#### Scenario: scenario WHEN/THEN text is escaped before injection into cli-augmented prompt

- **GIVEN** an OpenSpec scenario whose WHEN clause contains literal triple-backticks, the string `### Requirement:`, or other prompt-structure markers
- **WHEN** the framework builds the cli-augmented prompt for that scenario
- **THEN** the scenario's text MUST be wrapped inside fenced code blocks or another delimiter that prevents the embedded markers from changing prompt structure
- **AND** the prompt's overall section structure MUST remain unchanged (e.g., `# OpenSpec Scenarios (constraints)` heading still present and at the same nesting level)

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

Any behavioral validator (gen-eval invoked from `agent-coordinator/evaluation/gen_eval/__main__.py`, OR the Playwright validator implemented as the peer skill `skills/playwright-validator/`) SHALL emit findings to a per-vendor file conforming to the `review-findings.schema.json` schema defined at `openspec/schemas/review-findings.schema.json`.

Filename routing follows D2 (peer-skill packaging): when emitted by `agent-coordinator/evaluation/gen_eval/__main__.py` the file MUST be named `findings-gen-eval.json`; when emitted by `skills/playwright-validator/` the file MUST be named `findings-playwright.json`. The two filenames are mutually exclusive — a single change MUST NOT have both validators write under the same filename.

Each finding emitted by either validator MUST use `type: behavioral_failure` and MUST populate the schema's required `severity`, `description`, and `location` fields.

When the failing scenario originated from an OpenSpec scenario (per the OpenSpec-Seeded Scenario Generation requirement), the finding's `location` MUST reference the OpenSpec scenario's `file:line-range`, not the gen-eval scenario YAML or the generated Playwright `.spec.ts` file. This applies uniformly to gen-eval and Playwright outputs.

#### Scenario: Findings file produced and schema-valid

- **GIVEN** the framework runs with `--report-format json` and produces 2 failing scenarios and 5 passing scenarios
- **WHEN** the run completes
- **THEN** a file `findings-gen-eval.json` MUST exist in the `--output-dir`
- **AND** running `python -c "import json,jsonschema; jsonschema.validate(json.load(open('<file>')), json.load(open('openspec/schemas/review-findings.schema.json')))"` MUST exit zero
- **AND** the file MUST contain exactly 2 finding entries (one per failing scenario), all with `type: behavioral_failure`

#### Scenario: Concurrent gen-eval and Playwright validators write to distinct filenames

- **GIVEN** an OpenSpec change has both an HTTP/MCP/CLI descriptor AND a frontend descriptor
- **AND** `validate-feature --phase gen-eval` runs both validators against the same change
- **WHEN** both validators complete
- **THEN** `findings-gen-eval.json` (from gen-eval) MUST exist in the change directory
- **AND** `findings-playwright.json` (from Playwright) MUST exist in the change directory
- **AND** neither file MUST contain findings produced by the other validator
- **AND** `consensus_synthesizer.py` MUST merge both files as separate vendor sources and emit one `consensus.json`

#### Scenario: Playwright findings trace to OpenSpec scenarios

- **GIVEN** the Playwright validator runs against a frontend descriptor and an OpenSpec change with WHEN/THEN scenarios at `openspec/changes/foo/specs/ui/spec.md` lines 30-45
- **AND** one Playwright assertion fails for the scenario at lines 38-44
- **WHEN** the Playwright validator emits `findings-playwright.json`
- **THEN** the failing finding's `location.file` MUST be `openspec/changes/foo/specs/ui/spec.md`
- **AND** the failing finding's `location.line_start` MUST be 38 and `line_end` MUST be 44
- **AND** the finding's `metadata.scenario_id` MUST reference the originating scenario name (not the generated `.spec.ts` test name)

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

The pipeline MUST handle partial failures gracefully: when test-script generation fails for a subset of scenarios (malformed WHEN/THEN), browser-binary launch fails for a subset of browsers, or `npx playwright test` fails for a subset of generated tests, the pipeline MUST emit findings for the cases that DID run AND log warnings naming the failed cases AND exit zero only when zero scenarios produced findings (full-pipeline failure). Partial-failure scenarios surface as `severity: high` behavioral_failure findings with `description` naming the failure mode (`script_generation_failed`, `browser_launch_failed`, `test_execution_failed`).

The pipeline's local HTTP server (started for sample/test descriptors via `lifecycle.startup_command`) MUST bind to `127.0.0.1` rather than `0.0.0.0`. The frontend-descriptor schema enforces this default but does not override an explicit operator-supplied `--bind` flag; operators are responsible for any deliberate non-localhost binding.

The pipeline MUST NOT execute env-var-substituted `auth_flow.value` strings via shell expansion. Substitution MUST be performed using string-template replacement (Python's `string.Template.substitute` or equivalent), and missing env vars MUST cause the pipeline to fail fast with a clear error naming the missing variable rather than expanding to an empty string.

#### Scenario: Sample frontend exercise validates the full path

- **GIVEN** the sample frontend at `evaluation/gen_eval/fixtures/sample-frontend/index.html`
- **AND** the sample frontend descriptor at `evaluation/gen_eval/descriptors/sample-frontend.yaml`
- **AND** an OpenSpec change with at least one `#### Scenario` block describing a click-and-assert flow
- **WHEN** the Playwright pipeline runs with `--mode playwright --openspec-change <id>` (or the skill-equivalent invocation `/playwright-validator <id>`)
- **THEN** the pipeline MUST start a local HTTP server bound to `127.0.0.1` only (per design D7 — verifiable by `ss -tlnp` showing the listening socket on 127.0.0.1, not 0.0.0.0)
- **AND** the pipeline MUST generate a Playwright TypeScript test file under `skills/playwright-validator/test-results/generated/` that passes `npx playwright test --dry-run` (i.e., the script is syntactically valid Playwright TypeScript)
- **AND** the generated test MUST reference each OpenSpec WHEN step as a Playwright action (`page.click`, `page.fill`, `page.goto`, `page.waitForSelector`) and each OpenSpec THEN step as a Playwright assertion (`expect(...).toBeVisible()`, `expect(...).toHaveText(...)`, etc.)
- **AND** the generated test's selector arguments MUST resolve through the descriptor's `selectors` map (each selector alias MUST be expanded to the literal Playwright selector before script emission)
- **AND** the pipeline MUST execute `npx playwright test --reporter=json` against the generated script
- **AND** the pipeline MUST emit `findings-playwright.json` (per the Behavioral Findings Schema Conformance requirement) conforming to `review-findings.schema.json`

#### Scenario: Auth flow with missing env var fails fast

- **GIVEN** a frontend descriptor whose `auth_flow[].value` references `${MISSING_VAR}`
- **AND** the environment does not define `MISSING_VAR`
- **WHEN** the Playwright pipeline runs
- **THEN** the pipeline MUST exit with a non-zero status before starting any browser
- **AND** the pipeline MUST log "auth_flow: required env var MISSING_VAR not set" with that exact env var name
- **AND** the pipeline MUST NOT pass the literal string `${MISSING_VAR}` to any Playwright action

#### Scenario: Concurrent gen-eval and Playwright on same change

- **GIVEN** a change with both an HTTP descriptor (`evaluation/gen_eval/descriptors/api.yaml`) and a frontend descriptor (`evaluation/gen_eval/descriptors/sample-frontend.yaml`)
- **WHEN** `validate-feature --phase gen-eval <change-id>` runs
- **THEN** the phase MUST dispatch both gen-eval (for the HTTP descriptor) and the Playwright validator (for the frontend descriptor)
- **AND** the resulting findings files MUST be `findings-gen-eval.json` and `findings-playwright.json` — distinct files, no overwrite
- **AND** both files MUST validate against `openspec/schemas/review-findings.schema.json`
- **AND** the consensus synthesizer MUST treat both as separate vendor sources (per `contracts/findings-vendor-source.md`)

#### Scenario: Playwright dispatcher auto-detection in validate-feature

- **GIVEN** a change with a frontend descriptor at `evaluation/gen_eval/descriptors/*.yaml` that conforms to `frontend-descriptor.schema.json`
- **WHEN** `validate-feature --phase gen-eval <change-id>` runs
- **THEN** the phase handler MUST detect the descriptor as a frontend descriptor (by attempting to validate it against `frontend-descriptor.schema.json` rather than the HTTP/MCP descriptor schema)
- **AND** the handler MUST invoke the Playwright validator skill (e.g., `/playwright-validator <change-id>`) for that descriptor
- **AND** non-frontend descriptors in the same directory MUST still be dispatched to the HTTP/MCP gen-eval path (no regression)

#### Scenario: Playwright pipeline partial failure recovery

- **GIVEN** a Playwright run with 5 generated tests across 2 browsers (10 total executions)
- **AND** 3 of those executions fail (e.g., 2 in chromium, 1 in firefox), 7 pass
- **WHEN** the run completes
- **THEN** the pipeline MUST emit `findings-playwright.json` containing exactly 3 finding entries (one per failed execution)
- **AND** each finding MUST include `metadata.browser` identifying which browser produced it
- **AND** the pipeline MUST exit with a non-zero status code (test failures are not pipeline failures, but the calling skill needs to know tests failed)
- **AND** the pipeline MUST NOT abort early — all 10 executions must complete before the report is emitted


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
