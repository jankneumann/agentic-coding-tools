# skill-workflow Delta: add-local-model-provider-tier

## ADDED Requirements

### Requirement: Local Provider Dispatch Adapter

The provider dispatch layer SHALL support a `local` provider whose adapter launches the existing Pi coding-agent harness. A one-shot Pi extension SHALL register the distinct `local` provider against the configured OpenAI-compatible endpoint so the model operates through a real file, command, edit, and handoff tool loop. The adapter SHALL:

- Read the endpoint from `LOCAL_INFERENCE_BASE_URL` and an optional `LOCAL_INFERENCE_API_KEY`.
- Probe endpoint health before the first dispatch of a session and surface probe failure as adapter unavailability, not a dispatch error.
- Enforce a configured concurrency cap (`LOCAL_INFERENCE_MAX_CONCURRENCY`) on simultaneous local dispatches; requests beyond the cap SHALL queue rather than error.
- Require an explicit real `handoff_id` from the agent harness and normalize it through the same `(outcome, handoff_id)` contract as every other provider adapter; plain model text MUST NOT count as a completed phase.

When the endpoint is unconfigured or unreachable, dispatch SHALL degrade to the existing structured `fallback` result with a warning naming the `local` provider, and the calling skill layer SHALL continue through its documented fallback path. The adapter MUST NOT block a phase indefinitely on a dead endpoint.

#### Scenario: Configured endpoint dispatches successfully

- **WHEN** a `runner` phase dispatches under provider `local` with `LOCAL_INFERENCE_BASE_URL` set and the health probe passing
- **THEN** the adapter SHALL launch Pi headlessly with the local endpoint registered as its `local` provider
- **AND** Pi SHALL retain its coding-agent tools so the phase can inspect files, run commands, make permitted changes, and write a durable handoff
- **AND** only an explicit `(outcome, handoff_id)` from the final agent message SHALL normalize with `dispatch_tier` recording a harness dispatch
- **AND** `model_used` SHALL be the roster model identifier

#### Scenario: Unreachable endpoint degrades to fallback

- **WHEN** a phase dispatches under provider `local` and the health probe fails or `LOCAL_INFERENCE_BASE_URL` is unset
- **THEN** the adapter SHALL return the structured `fallback` result with a warning naming provider `local`
- **AND** no phase SHALL hang waiting on the endpoint
- **AND** the usage-limit policy engine SHALL NOT select `local` as a switch target while the probe fails

#### Scenario: Concurrency cap respected under fan-out

- **WHEN** more simultaneous local dispatches are requested than `LOCAL_INFERENCE_MAX_CONCURRENCY` allows
- **THEN** excess dispatches SHALL queue until a slot frees
- **AND** no dispatch SHALL be dropped or failed solely due to the cap

## MODIFIED Requirements

### Requirement: Manual Provider Smoke Path

The system SHALL provide an end-to-end smoke path that can be manually triggered by an operator from a specific agent CLI and verifies `/autopilot` provider-neutral dispatch behavior.

The smoke path SHALL:

- Accept a provider selector restricted to the supported roster (`claude_code`, `codex`, `antigravity`, `grok`, `pi`, `local`).
- Use a fixture or minimal change-id.
- Exercise the same provider model mapping used by real phase dispatch.
- Exercise the provider dispatch adapter in dry-run or real mode.
- Verify normalized `outcome` and `handoff_id` handling.
- Fail if a non-Claude provider receives `opus`, `sonnet`, or `haiku` without explicit mapping.
- Reject `gemini` as an unknown provider selector.

#### Scenario: Codex CLI smoke succeeds

- **WHEN** the operator runs the smoke path with provider `codex` and the smoke reaches the provider dispatch step
- **THEN** the dispatch payload SHALL contain a Codex model ID
- **AND** the dispatch result SHALL normalize to `(outcome, handoff_id)`
- **AND** the smoke SHALL report a pass/fail summary suitable for manual verification

#### Scenario: grok CLI smoke succeeds in configured mode

- **WHEN** the operator runs the smoke path with provider `grok` configured for dry-run or sync CLI mode and the smoke reaches the provider dispatch step
- **THEN** the dispatch payload SHALL contain a grok model ID
- **AND** the dispatch result SHALL normalize to `(outcome, handoff_id)`
- **AND** the smoke SHALL report any adapter limitations as warnings rather than silently skipping the provider

#### Scenario: local smoke succeeds in configured mode

- **WHEN** the operator runs the smoke path with provider `local` in dry-run mode, or in real mode with a reachable endpoint
- **THEN** the dispatch payload SHALL contain a `local` roster model identifier
- **AND** the dispatch result SHALL normalize to `(outcome, handoff_id)`
- **AND** a real-mode run against an unreachable endpoint SHALL report the fallback degradation as the smoke outcome rather than hanging

#### Scenario: Gemini CLI smoke succeeds in configured mode

- **WHEN** the operator runs the smoke path with provider `gemini` and the smoke validates the provider selector
- **THEN** the smoke SHALL reject `gemini` as an unsupported selector before dispatch (the gemini CLI harness is retired)
- **AND** the smoke SHALL report the failure with the supported roster rather than attempting a gemini dispatch

#### Scenario: Retired provider selector is rejected

- **WHEN** the operator runs the smoke path with provider `gemini` and the selector is parsed
- **THEN** the smoke SHALL exit non-zero with an error naming the supported roster
- **AND** it SHALL NOT attempt any dispatch
