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

#### Scenario: Coordinator identity is separate from provider authentication

- **WHEN** `prime-local` is projected into coordinator setup and dispatch configuration
- **THEN** its coordinator identity SHALL use the independently generated `prime_local_key` exposed by `--prime-local-key`
- **AND** that key SHALL be injected only as `COORDINATION_API_KEY`
- **AND** `PRIME_API_KEY` SHALL remain an operator-supplied Prime Inference credential referenced by `cli.api_key_env`
- **AND** neither credential SHALL be generated from, serialized as, or substituted for the other

#### Scenario: Cleanup is fail-closed across dispatch outcomes

- **GIVEN** a Prime CLI dispatch config declares a cleanup object
- **WHEN** a launched dispatch succeeds, exits non-zero, produces invalid output, is cancelled, or times out
- **THEN** the dispatcher SHALL run the cleanup argument vector exactly once with shell interpretation disabled and a bounded timeout
- **AND** it SHALL not expose coordinator credentials or unrelated provider secrets to the cleanup subprocess
- **AND** cleanup failure or timeout SHALL preserve the primary error, add structured cleanup diagnostics, and make the vendor result unsuccessful and ineligible for review quorum
- **AND** cleanup SHALL not terminate a concurrent unrelated Prime session
