# Spec Delta: Multi-Vendor Review Orchestration

Extends `openspec/specs/skill-workflow/spec.md` with multi-vendor review requirements.

## ADDED Requirements

### Requirement: Review Dispatcher Protocol

The system SHALL provide a `ReviewDispatcher` that can invoke review skills on different AI vendor CLIs (Claude, Codex, Gemini).

#### Scenario: Dispatch review to Codex

- GIVEN a completed implementation package
- WHEN the orchestrator dispatches a review to Codex
- THEN the Codex CLI is invoked with the review skill prompt and artifact paths
- AND a structured findings JSON file is produced at the expected output path

### Requirement: Reviewer Discovery via Coordinator

The `ReviewDispatcher` SHALL discover available reviewers via coordinator `discover_agents()` when the coordinator is available.

#### Scenario: Discover available reviewers

- GIVEN the coordinator is running and agents are registered
- WHEN the dispatcher calls `discover_agents(capability="review")`
- THEN it receives a list of agents with review capability and their vendor types

### Requirement: Reviewer Discovery Fallback

The `ReviewDispatcher` SHALL fall back to binary detection (`which codex`, `which gemini`) when the coordinator is unavailable.

#### Scenario: Discover reviewers without coordinator

- GIVEN the coordinator is unavailable
- WHEN the dispatcher attempts to discover reviewers
- THEN it checks for CLI binaries on PATH via `which`
- AND returns available vendors based on binary presence

### Requirement: Vendor Diversity

The `ReviewDispatcher` SHALL dispatch reviews to at least one vendor different from the implementing agent when multiple vendors are available.

#### Scenario: Ensure vendor diversity

- GIVEN Claude is the implementing agent and Codex and Gemini are available
- WHEN the dispatcher selects reviewers
- THEN at least one of Codex or Gemini is selected as a reviewer

### Requirement: Parallel Review Dispatch

The `ReviewDispatcher` SHALL execute vendor reviews in parallel (concurrent subprocess invocation).

#### Scenario: Parallel dispatch to multiple vendors

- GIVEN Codex and Gemini are both available
- WHEN the dispatcher dispatches reviews
- THEN both vendor subprocesses are started concurrently
- AND results are collected as each completes

### Requirement: Config-Driven Generic Adapter

A single `CliVendorAdapter` class SHALL handle all vendors, parameterized by CLI configuration from `agents.yaml`. There SHALL NOT be per-vendor adapter subclasses.

#### Scenario: Adapter constructed from config

- GIVEN agents.yaml contains a `cli` section for `codex-local` with `command: codex` and dispatch modes
- WHEN the ReviewOrchestrator loads agent config
- THEN it creates a `CliVendorAdapter` instance for `codex-local` using the config
- AND `dispatch_review()` returns a `DispatchResult` with vendor, process handle, output path, and timing

### Requirement: Vendor Timeout Enforcement

The `ReviewDispatcher` SHALL enforce a configurable per-vendor timeout (default: 300 seconds) and terminate timed-out processes.

#### Scenario: Vendor times out

- GIVEN a vendor review is dispatched with a 300-second timeout
- WHEN the vendor process exceeds the timeout
- THEN the process is terminated
- AND the result is marked as timed out with an error message

### Requirement: Consensus Synthesizer

The system SHALL provide a `ConsensusSynthesizer` that merges findings from multiple vendor review outputs.

#### Scenario: Synthesize findings from two vendors

- GIVEN findings JSON from Codex and Gemini for the same package
- WHEN the synthesizer processes both
- THEN it produces a consensus report with matched and unmatched findings

### Requirement: Cross-Vendor Finding Matching

Findings SHALL be matched across vendors using file location, finding type, and description similarity.

#### Scenario: Match identical findings

- GIVEN Codex finding: security issue at `src/api.py:42`
- AND Gemini finding: security issue at `src/api.py:42`
- WHEN the matching algorithm runs
- THEN the findings are matched with high confidence (score >= 0.8)

### Requirement: Confirmed Finding Classification

A finding confirmed by 2+ vendors SHALL be classified as `confirmed` in the consensus report.

#### Scenario: Two vendors agree on finding

- GIVEN matching findings from Codex and Gemini
- WHEN consensus is computed
- THEN the finding status is `confirmed`

### Requirement: Unconfirmed Finding Classification

A finding reported by only one vendor SHALL be classified as `unconfirmed` in the consensus report.

#### Scenario: Single vendor finding

- GIVEN a finding from Codex with no match from Gemini
- WHEN consensus is computed
- THEN the finding status is `unconfirmed`

### Requirement: Disagreement Classification

When vendors disagree on disposition (e.g., `fix` vs `accept`), the finding SHALL be classified as `disagreement` and escalated.

#### Scenario: Vendors disagree on disposition

- GIVEN Codex says disposition=`fix` and Gemini says disposition=`accept` for matched findings
- WHEN consensus is computed
- THEN the finding status is `disagreement`
- AND the recommended disposition is `escalate`

### Requirement: Consensus Report Schema Conformance

The consensus report SHALL conform to `openspec/schemas/consensus-report.schema.json`.

#### Scenario: Valid consensus report

- GIVEN synthesized consensus findings
- WHEN the report is generated
- THEN it validates against the consensus-report JSON schema

### Requirement: Integration Gate Uses Consensus

The integration gate SHALL use consensus findings: `confirmed` findings with disposition `fix` SHALL block integration.

#### Scenario: Confirmed fix finding blocks gate

- GIVEN a consensus report with a confirmed finding (disposition=`fix`)
- WHEN the integration gate checks
- THEN the gate returns BLOCKED_FIX

### Requirement: Unconfirmed Findings Warn Only

`Unconfirmed` findings SHALL generate warnings but SHALL NOT block integration.

#### Scenario: Unconfirmed finding passes gate

- GIVEN a consensus report with only unconfirmed findings
- WHEN the integration gate checks
- THEN the gate returns PASS with warnings

### Requirement: Disagreement Findings Escalate

`Disagreement` findings SHALL trigger escalation (BLOCKED_ESCALATE).

#### Scenario: Disagreement finding escalates

- GIVEN a consensus report with a disagreement finding
- WHEN the integration gate checks
- THEN the gate returns BLOCKED_ESCALATE

### Requirement: Quorum Reporting

The integration gate SHALL report quorum status (how many vendors reviewed vs. how many were requested).

#### Scenario: Quorum met

- GIVEN 2 vendors requested and 2 returned findings
- WHEN the consensus report is generated
- THEN `quorum_met` is true and `quorum_received` equals `quorum_requested`

### Requirement: Single Vendor Fallback

If no secondary vendors are available, the system SHALL proceed with single-vendor review and emit a warning.

#### Scenario: Only primary vendor available

- GIVEN Claude is the only available agent
- WHEN the dispatcher attempts multi-vendor review
- THEN it proceeds with Claude self-review
- AND emits a warning that vendor diversity was not achieved

### Requirement: Vendor Failure Resilience

If a vendor fails (timeout, invalid output, crash), the system SHALL skip that vendor's findings and proceed with available results.

#### Scenario: One vendor fails

- GIVEN Codex and Gemini are dispatched
- AND Codex times out
- WHEN results are collected
- THEN Gemini's findings are used alone
- AND the consensus report notes Codex's failure

### Requirement: Total Failure Warning

If all vendor dispatches fail, the system SHALL emit a warning and require manual human review before integration.

#### Scenario: All vendors fail

- GIVEN Codex and Gemini are both dispatched
- AND both fail
- WHEN results are collected
- THEN the system emits a warning requiring manual review
- AND the integration gate returns BLOCKED_ESCALATE

### Requirement: Dispatch Modes from Config

Dispatch modes and their CLI args SHALL be read from `agents.yaml` under `cli.dispatch_modes`. The adapter SHALL NOT hardcode CLI flags for any vendor.

#### Scenario: Review mode reads args from config

- GIVEN agents.yaml contains `codex-local.cli.dispatch_modes.review.args: [exec, -s, read-only]`
- WHEN the adapter builds the command for review mode
- THEN the command is `["codex", "exec", "-s", "read-only", "<prompt>"]`

#### Scenario: Alternative impl mode reads args from config

- GIVEN agents.yaml contains `gemini-local.cli.dispatch_modes.alternative_impl.args: [--approval-mode, yolo]`
- WHEN the adapter builds the command for alternative_impl mode
- THEN the command is `["gemini", "--approval-mode", "yolo", "<prompt>"]`

### Requirement: CLI Configuration Schema

Each agent entry in `agents.yaml` SHALL support an optional `cli` section with: `command` (binary name), `dispatch_modes` (map of mode name to args list), `model_flag` (flag syntax for model override), `model` (primary model or null), and `model_fallbacks` (ordered fallback list).

#### Scenario: Agent with no cli section

- GIVEN an agent entry in agents.yaml without a `cli` section
- WHEN the ReviewOrchestrator loads agent config
- THEN no adapter is created for that agent
- AND the agent is excluded from CLI dispatch (may still be available via other transports)

### Requirement: Non-Interactive Execution Guarantee

The `cli.dispatch_modes` config for each agent SHALL include non-interactive flags. The adapter enforces a hard timeout on every subprocess to catch misconfigured modes.

#### Scenario: Timeout kills hung process

- GIVEN a vendor process is dispatched with a 300-second timeout
- WHEN the process does not complete within 300 seconds
- THEN the dispatcher kills the process
- AND marks the result as timed out

### Requirement: Adapter Capability Check

The `CliVendorAdapter` SHALL implement a `can_dispatch(mode)` method that verifies: (1) the CLI binary exists on PATH, (2) the requested dispatch mode exists in `cli.dispatch_modes`.

#### Scenario: Missing CLI binary detected

- GIVEN the `codex` binary is not on PATH
- WHEN the adapter's `can_dispatch("review")` is called
- THEN it returns False
- AND the dispatcher skips this agent and proceeds with others

#### Scenario: Missing dispatch mode

- GIVEN an agent's cli config has no `alternative_impl` dispatch mode
- WHEN `can_dispatch("alternative_impl")` is called
- THEN it returns False

### Requirement: Model Fallback on Capacity Errors

When a vendor returns a 429 / MODEL_CAPACITY_EXHAUSTED error, the adapter SHALL retry with fallback models from the agent's `model_fallbacks` list in `agents.yaml` before marking the vendor as failed.

#### Scenario: Primary model exhausted, fallback succeeds

- GIVEN Gemini's configured model_fallbacks are `[gemini-2.5-pro, gemini-2.5-flash]`
- AND the primary model returns 429 RESOURCE_EXHAUSTED
- WHEN the adapter detects the capacity error in stderr
- THEN it retries with `-m gemini-2.5-pro` as the first fallback
- AND if the fallback succeeds, the findings are used normally

#### Scenario: All models exhausted

- GIVEN both primary and all fallback models return 429
- WHEN the adapter exhausts the fallback chain
- THEN the vendor is marked as failed with error details listing all models attempted
- AND the dispatcher proceeds with other available vendors

#### Scenario: No fallbacks configured

- GIVEN an agent entry with an empty `model_fallbacks` list
- WHEN the primary model returns 429
- THEN the vendor is marked as failed immediately (no retry)

### Requirement: Configurable Model Fallback Chains

Model fallback chains SHALL be configured per-agent in `agents.yaml` via `model` (primary, null for CLI default) and `model_fallbacks` (ordered list of fallback model names) fields. The adapter SHALL NOT hardcode model names.

#### Scenario: Read fallback config from agents.yaml

- GIVEN agents.yaml contains `model_fallbacks: [gemini-2.5-pro, gemini-2.5-flash]` for gemini-local
- WHEN the Gemini adapter initializes
- THEN it loads the fallback chain from the agent configuration
- AND uses these models in order when the primary model fails

### Requirement: Auth Error Surfacing

When a vendor fails due to authentication issues (expired token, missing login), the adapter SHALL surface a clear, actionable error message to the user with the vendor-specific re-login command.

#### Scenario: Gemini auth expired

- GIVEN Gemini returns a 401 UNAUTHENTICATED error
- WHEN the adapter parses the stderr
- THEN it prints a user-facing warning: "Gemini auth expired. Run: gemini login"
- AND the vendor is marked as failed (no retry, no fallback)

#### Scenario: Codex login required

- GIVEN Codex returns a login-required error
- WHEN the adapter parses the stderr
- THEN it prints a user-facing warning: "Codex login required. Run: codex login"
- AND the vendor is marked as failed (no retry, no fallback)

### Requirement: Review Manifest Generation

The review dispatcher SHALL produce a `reviews/review-manifest.json` file capturing dispatch metadata: which vendors were requested, which responded, timing, model used, quorum status, and error summaries for failed vendors.

#### Scenario: Manifest after mixed success

- GIVEN Codex review succeeded and Gemini review failed with 429
- WHEN the dispatcher completes
- THEN `reviews/review-manifest.json` contains entries for both vendors
- AND the Codex entry shows success=true with findings_count and elapsed_seconds
- AND the Gemini entry shows success=false with error_class="capacity_exhausted" and the models attempted
