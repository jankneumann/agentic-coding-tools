# skill-workflow — delta for add-agy-grok-pi-harnesses

Retires the `gemini` harness across dispatch, review, consensus, archetype-resolution, and
smoke-path requirements, replacing it with `antigravity`, `grok`, and `pi`. Also realigns the
skill-distribution requirements with what `skills/install.sh` actually does (proposal decision
D2) — they currently name a `.gemini/skills/` tree that has never existed.

## MODIFIED Requirements

### Requirement: Canonical Skill Distribution

Coordinator-integrated skill content SHALL be authored in the canonical `skills/` tree.

Runtime skill trees SHALL be treated as synced mirrors refreshed by the existing `skills/install.sh` workflow in `rsync` mode. The mirrors `install.sh` writes SHALL be exactly `.claude/skills/` and `.agents/skills/`.

Harnesses outside Claude Code SHALL consume one of those two existing mirrors rather than receiving a per-vendor runtime directory:

- `antigravity` and `pi` read `.agents/skills/`.
- `grok` reads Claude Code assets with no configuration, per https://docs.x.ai/build/features/skills-plugins-marketplaces — "Grok is fully compatible with Claude Code with zero configuration needed."

Pointing `grok` additionally at the project's `.agents/skills/` requires `[skills] paths` in `~/.grok/config.toml`, a machine-local operator file outside the repository. That configuration SHALL be documented as optional operator setup and SHALL NOT be a repository artifact.

No per-vendor runtime directory (`.gemini/`, `.grok/`, `.agy/`, `.pi/`) SHALL be committed to the repository.

#### Scenario: Canonical edit and sync
- **WHEN** coordinator integration changes are made to a skill
- **THEN** changes SHALL be applied to `skills/<skill-name>/SKILL.md`
- **AND** runtime mirror trees SHALL be updated by running `skills/install.sh --mode rsync`
- **AND** the refreshed mirrors SHALL be `.claude/skills/` and `.agents/skills/`

#### Scenario: Runtime mirror drift is detected
- **WHEN** runtime mirror skills differ from canonical `skills/` after sync
- **THEN** the differences SHALL be treated as parity defects
- **AND** the change SHALL NOT be considered ready until drift is resolved

#### Scenario: Existing sync workflow is preserved
- **WHEN** implementing this change
- **THEN** it SHALL reuse existing `skills/install.sh` behavior
- **AND** SHALL NOT introduce a second competing distribution mechanism

#### Scenario: No per-vendor runtime directory is committed
- **WHEN** the repository root is inspected after this change
- **THEN** no `.gemini/` directory SHALL exist
- **AND** no `.grok/`, `.agy/`, or `.pi/` directory SHALL have been added in its place

### Requirement: Coordination Detection

Each integrated skill SHALL detect coordinator access using a transport-aware model that works for both CLI and Web/Cloud agents.

Detection SHALL set:
- `COORDINATOR_AVAILABLE` (`true` or `false`)
- `COORDINATION_TRANSPORT` (`mcp`, `http`, or `none`)
- capability flags: `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

Detection rules:
- Local CLI agents (Claude Code, Codex, antigravity, grok, pi) inspect available MCP tools by function name
- Web/Cloud agents detect coordinator via HTTP API reachability/capability checks
- Coordination hooks execute only when their capability flag is true

#### Scenario: CLI runtime with MCP tools
- **WHEN** an integrated skill starts in a CLI runtime
- **AND** coordination MCP tools are present
- **THEN** the skill SHALL set `COORDINATION_TRANSPORT=mcp`
- **AND** set `COORDINATOR_AVAILABLE=true`
- **AND** set capability flags based on discovered tool availability

#### Scenario: Web/Cloud runtime with HTTP coordinator
- **WHEN** an integrated skill starts in a Web/Cloud runtime
- **AND** coordinator HTTP endpoint is reachable with valid credentials
- **THEN** the skill SHALL set `COORDINATION_TRANSPORT=http`
- **AND** set `COORDINATOR_AVAILABLE=true`
- **AND** set capability flags based on available HTTP endpoints/features

#### Scenario: Partial capability availability
- **WHEN** transport is available but some capabilities are not
- **THEN** the skill SHALL keep `COORDINATOR_AVAILABLE=true`
- **AND** set missing capability flags to false
- **AND** skip only unsupported hooks

#### Scenario: No coordinator access
- **WHEN** neither MCP nor HTTP coordinator access is available
- **THEN** the skill SHALL set `COORDINATOR_AVAILABLE=false`
- **AND** set `COORDINATION_TRANSPORT=none`
- **AND** continue standalone behavior without errors

#### Scenario: Coordinator becomes unreachable mid-execution
- **WHEN** a coordination call fails after detection succeeded
- **THEN** the skill SHALL log informationally
- **AND** continue standalone fallback behavior for that step
- **AND** NOT abort solely due to coordinator unavailability

### Requirement: Infrastructure Skills Are Synced

`install.sh` MUST sync infrastructure skills alongside SDLC skills to every runtime mirror it writes.

#### Scenario: install.sh syncs infrastructure skills
- **GIVEN** infrastructure skill directories exist under `skills/`
- **WHEN** `install.sh` is executed
- **THEN** infrastructure skills MUST appear in `.claude/skills/` and `.agents/skills/`
- **AND** no `.gemini/skills/` tree SHALL be produced or expected

### Requirement: Review Dispatcher Protocol

The system SHALL provide a `ReviewDispatcher` that can invoke review skills on different AI vendor CLIs (Claude Code, Codex, antigravity, grok, pi).

#### Scenario: Dispatch review to Codex

- GIVEN a completed implementation package
- WHEN the orchestrator dispatches a review to Codex
- THEN the Codex CLI is invoked with the review skill prompt and artifact paths
- AND a structured findings JSON file is produced at the expected output path

#### Scenario: Dispatch review to grok

- GIVEN a completed implementation package
- WHEN the orchestrator dispatches a review to grok
- THEN the grok CLI is invoked with the review skill prompt and artifact paths
- AND the invocation SHALL use `--output-format json` so the result is a structured envelope rather than scraped stdout
- AND a structured findings JSON file is produced at the expected output path

### Requirement: Reviewer Discovery Fallback

The `ReviewDispatcher` SHALL fall back to binary detection (`which codex`, `which agy`, `which grok`, `which pi`) when the coordinator is unavailable.

#### Scenario: Discover reviewers without coordinator

- GIVEN the coordinator is unavailable
- WHEN the dispatcher attempts to discover reviewers
- THEN it checks for CLI binaries on PATH via `which`
- AND returns available vendors based on binary presence
- AND it SHALL NOT probe for a `gemini` binary

### Requirement: Vendor Diversity

The `ReviewDispatcher` SHALL dispatch reviews to at least one vendor different from the implementing agent when multiple vendors are available.

#### Scenario: Ensure vendor diversity

- GIVEN Claude is the implementing agent and Codex and grok are available
- WHEN the dispatcher selects reviewers
- THEN at least one of Codex or grok is selected as a reviewer

### Requirement: Parallel Review Dispatch

The `ReviewDispatcher` SHALL execute vendor reviews in parallel (concurrent subprocess invocation).

#### Scenario: Parallel dispatch to multiple vendors

- GIVEN Codex and grok are both available
- WHEN the dispatcher dispatches reviews
- THEN both vendor subprocesses are started concurrently
- AND results are collected as each completes

### Requirement: Consensus Synthesizer

The system SHALL provide a `ConsensusSynthesizer` that merges findings from multiple vendor review outputs.

#### Scenario: Synthesize findings from two vendors

- GIVEN findings JSON from Codex and grok for the same package
- WHEN the synthesizer processes both
- THEN it produces a consensus report with matched and unmatched findings

### Requirement: Cross-Vendor Finding Matching

Findings SHALL be matched across vendors using file location, finding type, and description similarity.

#### Scenario: Match identical findings

- GIVEN Codex finding: security issue at `src/api.py:42`
- AND grok finding: security issue at `src/api.py:42`
- WHEN the matching algorithm runs
- THEN the findings are matched with high confidence (score >= 0.8)

### Requirement: Confirmed Finding Classification

A finding confirmed by 2+ vendors SHALL be classified as `confirmed` in the consensus report.

#### Scenario: Two vendors agree on finding

- GIVEN matching findings from Codex and grok
- WHEN consensus is computed
- THEN the finding status is `confirmed`

### Requirement: Unconfirmed Finding Classification

A finding reported by only one vendor SHALL be classified as `unconfirmed` in the consensus report.

#### Scenario: Single vendor finding

- GIVEN a finding from Codex with no match from grok
- WHEN consensus is computed
- THEN the finding status is `unconfirmed`

### Requirement: Disagreement Classification

When vendors disagree on disposition (e.g., `fix` vs `accept`), the finding SHALL be classified as `disagreement` and escalated.

#### Scenario: Vendors disagree on disposition

- GIVEN Codex says disposition=`fix` and grok says disposition=`accept` for matched findings
- WHEN consensus is computed
- THEN the finding status is `disagreement`
- AND the recommended disposition is `escalate`

### Requirement: Vendor Failure Resilience

If a vendor fails (timeout, invalid output, crash), the system SHALL skip that vendor's findings and proceed with available results.

#### Scenario: One vendor fails

- GIVEN Codex and grok are dispatched
- AND Codex times out
- WHEN results are collected
- THEN grok's findings are used alone
- AND the consensus report notes Codex's failure

### Requirement: Total Failure Warning

If all vendor dispatches fail, the system SHALL emit a warning and require manual human review before integration.

#### Scenario: All vendors fail

- GIVEN Codex and grok are both dispatched
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

#### Scenario: Alternative mode reads args from config

- GIVEN agents.yaml contains `pi-local.cli.dispatch_modes.alternative.args: [--provider, openrouter]`
- WHEN the adapter builds the command for alternative mode
- THEN the command is `["pi", "--provider", "openrouter", "<prompt>"]`

#### Scenario: Prompt delivered via stdin when configured

- GIVEN agents.yaml sets `prompt_via_stdin: true` for `grok-local`
- WHEN the adapter builds the command
- THEN the prompt SHALL NOT be appended as a trailing positional argument
- AND the prompt SHALL be written to the subprocess stdin instead

### Requirement: Model Fallback on Capacity Errors

When a vendor returns a 429 / MODEL_CAPACITY_EXHAUSTED error, the adapter SHALL retry with fallback models from the agent's `model_fallbacks` list in `agents.yaml` before marking the vendor as failed.

#### Scenario: Primary model exhausted, fallback succeeds

- GIVEN an agent's configured `model_fallbacks` list is non-empty
- AND the primary model returns 429 RESOURCE_EXHAUSTED
- WHEN the adapter detects the capacity error in stderr
- THEN it retries with the first entry of `model_fallbacks` via the agent's configured `model_flag`
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

- GIVEN agents.yaml declares `model` and `model_fallbacks` for `grok-local`
- WHEN the grok adapter initializes
- THEN it loads the fallback chain from the agent configuration
- AND uses these models in order when the primary model fails

### Requirement: Auth Error Surfacing

When a vendor fails due to authentication issues (expired token, missing login), the adapter SHALL surface a clear, actionable error message to the user with the vendor-specific re-login command.

The re-login command map SHALL carry an entry for every vendor in the roster. Where a vendor's re-login command has not been empirically confirmed, the adapter SHALL fall back to `<command> login` rather than omitting guidance.

#### Scenario: grok auth expired

- GIVEN grok returns a 401 UNAUTHENTICATED error
- WHEN the adapter parses the stderr
- THEN it prints a user-facing warning: "grok auth expired. Run: grok login"
- AND the vendor is marked as failed (no retry, no fallback)

#### Scenario: Codex login required

- GIVEN Codex returns a login-required error
- WHEN the adapter parses the stderr
- THEN it prints a user-facing warning: "Codex login required. Run: codex login"
- AND the vendor is marked as failed (no retry, no fallback)

#### Scenario: Vendor without a confirmed re-login command

- GIVEN a roster vendor whose re-login command is not present in the map
- WHEN an auth error is classified for that vendor
- THEN the adapter SHALL emit `<command> login` as the suggested remediation
- AND SHALL NOT emit a command referencing the retired gemini CLI

### Requirement: Review Manifest Generation

The review dispatcher SHALL produce a `reviews/review-manifest.json` file capturing dispatch metadata: which vendors were requested, which responded, timing, model used, quorum status, and error summaries for failed vendors.

#### Scenario: Manifest after mixed success

- GIVEN Codex review succeeded and grok review failed with 429
- WHEN the dispatcher completes
- THEN `reviews/review-manifest.json` contains entries for both vendors
- AND the Codex entry shows success=true with findings_count and elapsed_seconds
- AND the grok entry shows success=false with error_class="capacity_exhausted" and the models attempted

### Requirement: Review Convergence Loop

The convergence loop SHALL dispatch reviews to all available vendors via `ReviewOrchestrator.dispatch_and_wait()`, synthesize findings via `ConsensusSynthesizer.synthesize()`, and exit when no confirmed or unconfirmed findings at medium or higher severity remain AND quorum is met. The loop SHALL enforce a maximum iteration cap (default 3 rounds per phase).

#### Scenario: Multi-vendor review dispatch

- **GIVEN** 3 vendors are available (claude, codex, grok)
- **WHEN** a convergence review round begins
- **THEN** the system SHALL dispatch review requests to all 3 vendors

#### Scenario: Convergence achieved with quorum

- **GIVEN** consensus shows 3 low-severity findings and 0 medium+ findings
- **AND** at least 2 vendors returned valid results
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL be declared and the loop SHALL advance to the next phase

#### Scenario: Convergence blocked by insufficient quorum

- **GIVEN** only 1 vendor returned valid results with 0 findings
- **WHEN** the exit condition is checked
- **THEN** convergence SHALL NOT be declared
- **AND** the system SHALL pause with reason "quorum_lost"

#### Scenario: Max iterations reached

- **GIVEN** the plan review has run 3 rounds without convergence
- **WHEN** the 3rd round completes with remaining medium+ findings
- **THEN** the system SHALL transition to ESCALATE state

### Requirement: Per-Phase Archetype Resolution in Autopilot

The autopilot state machine SHALL resolve an archetype for every non-terminal phase before dispatching phase work, SHALL build a provider-neutral phase dispatch payload for sub-agent-capable phases, and SHALL apply the resolved archetype on the production execution path.

The resolution SHALL:

1. Be performed inside `skills/autopilot/scripts/phase_agent.py:_build_options(phase, state_dict)` or a compatibility wrapper that preserves that public behavior.
2. Extract per-phase signals from `state_dict` based on the `signals` field of the phase mapping.
3. Call the coordinator endpoint `POST /archetypes/resolve_for_phase` via `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)`.
4. Resolve a logical archetype and model tier to a provider-specific model identifier for the selected provider.
5. Record the resolved archetype name in `state_dict["_resolved_archetype"]` for downstream use by `LoopState.phase_archetype`.

The 13 non-terminal phases SHALL be: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR`.

The `skills/autopilot/SKILL.md` orchestration prose SHALL dispatch the following 7 phases through the provider-neutral dispatch adapter when an adapter is available: `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `VAL_REVIEW` (when enabled). For these phases the dispatch SHALL pass the provider-specific model ID and SHALL fold the resolved `system_prompt` into the prompt text using the fixed separator `\n\n---\n\n`.

State-only phases (`INIT`, `PLAN`, `SUBMIT_PR`) SHALL still record `LoopState.phase_archetype` for their resolved archetype via a state-only resolver, even though they do not dispatch a phase sub-agent.

Convergence-loop-driven phases (`PLAN_FIX`, `IMPL_FIX`, `VAL_FIX`) SHALL inherit or record `LoopState.phase_archetype` for audit purposes via the convergence loop's existing path, but SHALL NOT receive a separate provider-adapter dispatch block in SKILL.md.

#### Scenario: PLAN phase resolves to provider-specific architect model

- **GIVEN** autopilot is running under provider `codex`
- **AND** `phase_mapping.PLAN.archetype` is `"architect"`
- **AND** the provider model map resolves `architect` or its tier to `gpt-5.5`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** the resolved phase metadata SHALL contain `"archetype": "architect"`
- **AND** the dispatch metadata SHALL contain `"model": "gpt-5.5"`
- **AND** the dispatch metadata SHALL NOT contain Claude-only model aliases unless the Codex mapping explicitly declares them

#### Scenario: IMPLEMENT phase resolves with provider-specific escalation

- **GIVEN** autopilot is running under provider `antigravity`
- **AND** a work package with `loc_estimate=250` is being processed
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** the phase resolver SHALL extract `loc_estimate` from `state_dict` and pass it as a signal
- **AND** the resolved archetype SHALL be `"implementer"`
- **AND** the model tier SHALL escalate from `standard` to `premium`
- **AND** the provider-specific model SHALL be an antigravity model ID from the configured antigravity mapping

#### Scenario: Production autopilot run dispatches through provider adapter

- **GIVEN** a real autopilot run executing from `/autopilot <change-id>` against an available coordinator
- **AND** the active provider is `codex`
- **WHEN** the run reaches the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL invoke the provider-neutral dispatch adapter
- **AND** the adapter SHALL receive a payload conforming to `contracts/phase-dispatch-contract.md`
- **AND** the payload's `model` SHALL be provider-specific for Codex
- **AND** the prompt passed to the adapter SHALL begin with the resolved `system_prompt` followed by `\n\n---\n\n` followed by the per-phase task prompt
- **AND** after the adapter returns, `LoopState.phase_archetype` in `loop-state.json` SHALL equal `"implementer"`
- **AND** `LoopState.last_handoff_id` SHALL be updated to the `handoff_id` returned from the dispatched provider result

#### Scenario: Claude remains supported

- **GIVEN** autopilot is running under provider `claude_code`
- **AND** the Claude dispatch adapter is available
- **WHEN** autopilot dispatches a phase that previously used `Agent(...)`
- **THEN** the provider-neutral adapter MAY invoke the existing Claude harness `Agent(...)` surface internally
- **AND** the public SKILL.md contract SHALL still describe the provider-neutral adapter rather than requiring non-Claude providers to expose `Agent(...)`

### Requirement: Per-Phase Archetype Resolution Failure Mode

If the coordinator endpoint is unreachable or returns an error, OR if no provider adapter is available in the executing orchestrator, autopilot SHALL fall back to the existing inline-prose execution path for that phase and continue.

Fallback behavior:

- `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)` SHALL return `None` on any failure.
- When `None` is returned, phase dispatch SHALL omit provider-specific model and system prompt values unless an override is present.
- `LoopState.phase_archetype` SHALL be set to `None` for that phase.
- A structured warning SHALL be logged including the phase name, selected provider, error reason, and a hint that operators can use `AUTOPILOT_PHASE_MODEL_OVERRIDE` or provider config as temporary mitigation.
- The phase SHALL still complete normally by falling through to the existing inline slash-command path.

#### Scenario: Provider adapter unavailable falls back gracefully

- **GIVEN** `AUTOPILOT_PROVIDER=antigravity`
- **AND** no antigravity dispatch adapter is configured in the current runtime
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL detect the missing adapter
- **AND** it SHALL fall through to the inline `/implement-feature <change-id>` invocation
- **AND** `LoopState.phase_archetype` SHALL be `None` for that phase
- **AND** a structured warning SHALL identify the selected provider and adapter unavailability

#### Scenario: Retired provider is rejected rather than falling back

- **GIVEN** `AUTOPILOT_PROVIDER=gemini`
- **WHEN** autopilot resolves the provider before entering a phase
- **THEN** it SHALL fail with a structured configuration error naming `gemini` as a retired harness
- **AND** it SHALL NOT silently fall back to the inline path, because the provider selection itself is invalid

### Requirement: Lifecycle Skills Use Provider-Neutral Dispatch Terminology

The lifecycle skills called by `/autopilot` SHALL describe phase or task delegation using provider-neutral dispatch terminology rather than Claude-only `Agent(...)` terminology.

This requirement applies to:

- `skills/autopilot/SKILL.md`
- `skills/plan-feature/SKILL.md`
- `skills/implement-feature/SKILL.md`
- `skills/iterate-on-plan/SKILL.md`
- `skills/iterate-on-implementation/SKILL.md`
- `skills/parallel-review-plan/SKILL.md`
- `skills/parallel-review-implementation/SKILL.md`
- `skills/validate-feature/SKILL.md`

#### Scenario: Skill docs do not make Agent the canonical cross-provider path

- **WHEN** lifecycle skill docs are scanned for provider-dispatch instructions
- **THEN** Claude-specific `Agent(...)` references SHALL be labeled as Claude adapter internals or examples
- **AND** the canonical instruction SHALL refer to the provider-neutral dispatch adapter or inline fallback
- **AND** Codex, antigravity, grok, and pi SHALL be described as first-class providers where adapters are configured
- **AND** no lifecycle skill doc SHALL name Gemini or Jules as a dispatch provider

### Requirement: Manual Provider Smoke Path

The system SHALL provide an end-to-end smoke path that can be manually triggered by an operator from a specific agent CLI and verifies `/autopilot` provider-neutral dispatch behavior.

The smoke path SHALL:

- Accept a provider selector restricted to the supported roster (`claude_code`, `codex`, `antigravity`, `grok`, `pi`).
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

#### Scenario: Retired provider selector is rejected

- **GIVEN** the operator runs the smoke path with provider `gemini`
- **WHEN** the selector is parsed
- **THEN** the smoke SHALL exit non-zero with an error naming the supported roster
- **AND** it SHALL NOT attempt any dispatch
