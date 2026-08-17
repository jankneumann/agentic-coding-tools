## ADDED Requirements

### Requirement: Prime Harness Dispatch

The dispatch system SHALL support `prime-agent` (Prime Intellect) as a first-class CLI vendor under the canonical provider key `prime`, dispatched headlessly via `--mode json` through the generic CLI adapter.

Dispatch SHALL observe the subscription-lane policy: the `prime` vendor runs non-Anthropic models via Prime Inference (`PRIME_API_KEY`); Claude models remain reserved to the `claude_code` subscription harness.

#### Scenario: Headless dispatch parses the NDJSON stream

- **WHEN** the dispatcher invokes `prime-agent --mode json` with a prompt as trailing positional under a subprocess pipe
- **THEN** the dispatcher SHALL stream-parse the NDJSON event stream and extract the final assistant output
- **AND** structured findings SHALL be parsed from that output into the standard findings schema
- **AND** no resident `prime-agent` worker process SHALL remain after the dispatch completes

#### Scenario: Review mode requires positive read evidence

- **GIVEN** the `prime-local` entry declares a `review` dispatch mode
- **WHEN** the review-mode admission evidence is evaluated
- **THEN** a harness-native write-prevention mechanism SHALL be on record with empirical evidence
- **AND** the validation transcript SHALL show the harness actually read the repository files named in the prompt
- **AND** absent either piece of evidence, the `review` dispatch mode SHALL be withheld and the vendor SHALL NOT participate in review quorum

#### Scenario: Out-of-policy provider authentication is rejected in setup

- **WHEN** operator setup documentation for the `prime` vendor is consulted
- **THEN** it SHALL instruct authentication via `PRIME_API_KEY` (Prime Inference) only
- **AND** it SHALL document Anthropic, OpenAI, and Copilot OAuth inside prime-agent as out of policy for dispatched use, because those paths are metered rather than subscription-backed

#### Scenario: Vendor key does not collide with pi

- **WHEN** any roster gate, fixture, or dispatch filter evaluates vendor membership
- **THEN** `prime` and `pi` SHALL be matched as whole vendor keys
- **AND** an unanchored substring match of `pi` against `prime` SHALL be treated as a defect
