# skill-workflow — delta for add-atomic-harness

Adds the atomic experimental vendor to reviewer discovery, defines the headless
workflow-executor dispatch contract piloted in `fix-scrub`, and teaches the manual
provider smoke path about experimental providers.

## ADDED Requirements

### Requirement: Workflow-Executor Dispatch

The system SHALL provide a workflow-executor dispatch adapter
(`skills/parallel-infrastructure/scripts/workflow_dispatch.py`) that runs a named Atomic
workflow headlessly and returns a structured result.

The adapter SHALL:

- Construct the command as `atomic -p --mode json --approve '/workflow <name> <key>=<value> …'` with `--provider` and `--model` always pinned explicitly (empirical finding A10).
- Execute inside a managed worktree, never the shared checkout (finding A19: atomic has no sandbox).
- Parse the NDJSON event stream and treat the `workflow.run.end` custom event as the authoritative terminal result, extracting `runId`, `status`, and the typed `result` payload (finding A14).
- Classify `status`: `completed` is success; `blocked` is retryable after reauthentication or provider recovery; `failed` is terminal for the attempt.
- Apply a first-run timeout of at least 300 seconds to absorb TypeScript workflow compile warm-up (finding A13), with configured per-mode timeouts thereafter.
- Reject, at command-build time, dispatch of workflow definitions known to contain interactive human-input gates, because headless runs fail at the prompt.
- Record `runId` and the terminal status in the dispatch audit trail.

#### Scenario: Completed workflow run returns typed outputs

- **GIVEN** a registered Atomic workflow `<name>` with declared outputs
- **WHEN** the adapter dispatches it headlessly and the run completes
- **THEN** the adapter SHALL return `status="completed"` with the workflow's `result` object and `runId`
- **AND** the subprocess exit code SHALL be 0

#### Scenario: Blocked run is distinguished from failure

- **GIVEN** a dispatched workflow run that stops on a recoverable provider or auth block
- **WHEN** the terminal event reports `status="blocked"`
- **THEN** the adapter SHALL classify the attempt as retryable and surface the reauthentication hint "set OPENROUTER_API_KEY in the environment or run interactive `/login`"
- **AND** it SHALL NOT report the run as completed

#### Scenario: Human-input workflow is rejected before dispatch

- **GIVEN** a workflow definition that requires interactive human input
- **WHEN** headless dispatch is requested for it
- **THEN** the adapter SHALL refuse at command-build time with a structured error naming the workflow and the headless limitation
- **AND** no subprocess SHALL be started

### Requirement: Fix-Scrub Workflow Executor Opt-In

`fix-scrub` SHALL accept an opt-in `--executor atomic-workflow` flag that routes a fix
batch through the workflow-executor dispatch adapter instead of the default vendor
dispatch. The default executor SHALL remain unchanged, and no other lifecycle skill
SHALL switch executors in this change.

#### Scenario: Default execution is unchanged

- **WHEN** `fix-scrub` runs without `--executor`
- **THEN** it SHALL use the existing vendor dispatch path
- **AND** no atomic workflow SHALL be invoked

#### Scenario: Opt-in executor routes through workflow dispatch

- **GIVEN** `fix-scrub --executor atomic-workflow` and a discoverable `atomic` binary
- **WHEN** a fix batch is executed
- **THEN** the batch SHALL be dispatched as a named Atomic workflow via the workflow-executor adapter
- **AND** verification of the fixes SHALL still run through the skill's existing verify step, not the workflow's self-report

#### Scenario: Opt-in fails soft when atomic is unavailable

- **GIVEN** `fix-scrub --executor atomic-workflow` and no `atomic` binary on PATH
- **WHEN** the skill starts the batch
- **THEN** it SHALL log a structured warning and fall back to the default executor
- **AND** the fallback SHALL be reported in the run summary

## MODIFIED Requirements

### Requirement: Reviewer Discovery Fallback

The `ReviewDispatcher` SHALL fall back to binary detection (`which codex`, `which agy`, `which grok`, `which pi`, `which atomic`) when the coordinator is unavailable. Binary detection SHALL cover experimental vendors declared in the loaded dispatch config.

#### Scenario: Discover reviewers without coordinator

- GIVEN the coordinator is unavailable
- WHEN the dispatcher attempts to discover reviewers
- THEN it checks for CLI binaries on PATH via `which`
- AND returns available vendors based on binary presence, including the experimental `atomic` vendor when its binary is present
- AND it SHALL NOT probe for a `gemini` binary

### Requirement: Manual Provider Smoke Path

The system SHALL provide an end-to-end smoke path that can be manually triggered by an operator from a specific agent CLI and verifies `/autopilot` provider-neutral dispatch behavior.

The smoke path SHALL:

- Accept a provider selector restricted to the supported roster (`claude_code`, `codex`, `antigravity`, `grok`, `pi`) plus providers declared experimental in the loaded dispatch config.
- Emit an explicit experimental-provider warning when an experimental selector is used, and support dry-run mode for experimental providers without network access.
- Use a fixture or minimal change-id.
- Exercise the same provider model mapping used by real phase dispatch.
- Exercise the provider dispatch adapter in dry-run or real mode.
- Verify normalized `outcome` and `handoff_id` handling.
- Fail if a non-Claude provider receives `opus`, `sonnet`, or `haiku` without explicit mapping.
- Reject `gemini` as an unknown provider selector.

#### Scenario: Codex CLI smoke succeeds

- **GIVEN** the operator runs the smoke path with provider `codex`
- **WHEN** the smoke reaches the provider dispatch step
- **THEN** the dispatch payload SHALL contain a Codex model ID
- **AND** the dispatch result SHALL normalize to `(outcome, handoff_id)`
- **AND** the smoke SHALL report a pass/fail summary suitable for manual verification

#### Scenario: grok CLI smoke succeeds in configured mode

- **GIVEN** the operator runs the smoke path with provider `grok`
- **AND** grok dispatch is configured for dry-run or sync CLI mode
- **WHEN** the smoke reaches the provider dispatch step
- **THEN** the dispatch payload SHALL contain a grok model ID
- **AND** the dispatch result SHALL normalize to `(outcome, handoff_id)`
- **AND** the smoke SHALL report any adapter limitations as warnings rather than silently skipping the provider

#### Scenario: Experimental atomic smoke runs dry with warning

- **GIVEN** the operator runs the smoke path with provider `atomic` in dry-run mode
- **WHEN** the smoke reaches the provider dispatch step
- **THEN** the smoke SHALL emit an experimental-provider warning naming `atomic`
- **AND** the dispatch payload SHALL contain an explicitly pinned OpenRouter model slug distinct from the `pi` tier map
- **AND** the smoke SHALL complete without requiring network access

#### Scenario: Undeclared provider selector is rejected

- **GIVEN** a provider selector that is neither first-class nor declared experimental
- **WHEN** the smoke path is invoked with it
- **THEN** the smoke SHALL fail with a structured error listing the first-class roster and registered experimental providers
- **AND** no dispatch SHALL be attempted

#### Scenario: Gemini CLI smoke succeeds in configured mode

- **GIVEN** the operator runs the smoke path with provider `gemini`
- **WHEN** the smoke validates the provider selector
- **THEN** the smoke SHALL reject `gemini` as an unsupported selector before dispatch (the gemini CLI harness is retired)
- **AND** the smoke SHALL report the failure with the supported roster rather than attempting a gemini dispatch

#### Scenario: Retired provider selector is rejected

- **GIVEN** the operator runs the smoke path with provider `gemini`
- **WHEN** the selector is parsed
- **THEN** the smoke SHALL exit non-zero with an error naming the supported roster
- **AND** it SHALL NOT attempt any dispatch
