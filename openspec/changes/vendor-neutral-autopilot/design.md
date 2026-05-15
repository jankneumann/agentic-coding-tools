# Vendor-Neutral Autopilot Dispatch Design

## Context

`/autopilot` already has a layered state machine, per-phase archetype resolution, and a multi-vendor review dispatcher. The remaining portability problem is that phase sub-agent dispatch and model naming still leak Claude-specific assumptions into the lifecycle contract. Codex and Gemini/Jules should be able to run the same lifecycle without receiving Claude model aliases or requiring Claude MCP configuration.

This design keeps the existing OpenSpec workflow, coordinator service, and review dispatcher architecture. It adds a provider-neutral adapter boundary around lifecycle dispatch, extends model resolution to provider-specific model IDs, and broadens configuration discovery so the system does not depend on `~/.claude.json`.

## Goals

- Make Claude Code, Codex, and Gemini/Jules first-class providers for autopilot phase dispatch.
- Keep logical archetypes (`architect`, `implementer`, `reviewer`, `analyst`, `runner`) as the planning vocabulary.
- Translate logical archetype model intents to provider-specific model IDs at dispatch time.
- Let `/autopilot` and called lifecycle skills use one dispatch contract.
- Provide a manually runnable end-to-end smoke path from a chosen provider CLI.

## Non-Goals

- Replacing the coordinator with a full dispatch broker.
- Removing Claude Code-specific runtime support where it is valid.
- Changing the lifecycle approval gates.
- Hardening remote Gemini/Jules polling beyond the contract and smoke coverage needed for this change.

## Decisions

### D1: Provider-Neutral Phase Dispatch Contract

Create a dispatch contract with provider-neutral fields:

- `phase`
- `change_id`
- `archetype`
- `prompt`
- `system_prompt`
- `isolation`
- `expected_outcomes`
- `provider`
- `model`

The existing `phase_agent.build_phase_dispatch_kwargs()` should remain backward compatible but should also produce enough metadata for a dispatch adapter to select provider-specific behavior.

Rationale: this keeps the current prose-to-Python boundary intact while preventing SKILL.md prose from hardcoding `Agent(...)` as the only path.

### D2: Dispatch Adapter Per Provider

Add a small provider adapter layer, owned by autopilot or shared lifecycle infrastructure, with a common interface:

```python
dispatch_phase(payload: PhaseDispatchPayload) -> PhaseDispatchResult
```

Provider adapters normalize results to:

- `outcome`
- `handoff_id`
- `provider`
- `model_used`
- `dispatch_tier`
- `warnings`

Initial adapters:

- Claude Code: wraps the existing harness `Agent(...)` semantics where exposed.
- Codex: wraps the local Codex sub-agent or CLI-compatible execution surface available to the runtime.
- Gemini/Jules: wraps Gemini CLI or Jules async dispatch where configured, with explicit unsupported-mode warnings when polling is unavailable.

Rationale: the adapter is small enough to implement now and creates a stable boundary for a future coordinator-owned broker.

### D3: Provider-Specific Model Mapping

Keep archetypes as logical roles, but move concrete model IDs behind provider mapping.

Example structure:

```yaml
model_aliases:
  claude_code:
    premium: opus
    standard: sonnet
    economy: haiku
  codex:
    premium: gpt-5.5
    standard: gpt-5.4
    economy: gpt-5.4-mini
  gemini:
    premium: gemini-2.5-pro
    standard: gemini-2.5-flash
    economy: gemini-2.5-flash
```

Archetypes can then refer to logical tiers (`premium`, `standard`, `economy`) or retain legacy aliases that are translated for non-Claude providers.

Rationale: `opus`, `sonnet`, and `haiku` are useful shorthand for Claude operators, but they should not leak into Codex or Gemini dispatch.

### D4: Discovery Order Is Provider-Neutral

Dispatch config discovery should use this order:

1. Explicit env vars or CLI args (`AGENT_COORDINATOR_DIR`, `AGENTS_YAML`, `COORDINATION_API_URL`).
2. HTTP coordinator endpoint for dispatch configs.
3. Local repo `agent-coordinator/agents.yaml`.
4. Provider-native config discovery, including Claude MCP config when running under Claude.
5. Empty config with a structured warning.

Rationale: Claude config remains supported but no longer blocks Codex/Gemini-only environments.

### D5: Lifecycle Skills Share Vocabulary

Update `/autopilot` and called skills to refer to provider-neutral "phase dispatch" and "provider adapter" terminology. Provider-specific examples should be clearly labeled as examples, not normative behavior.

Rationale: the user-facing workflow should not imply that Codex or Gemini are fallback-only providers.

### D6: Smoke Test Exercises Manual CLI Entry

Add a smoke harness that can be run by an operator from a selected provider CLI. The smoke should:

1. Select provider via env var or CLI flag.
2. Load provider model mapping.
3. Build one or more autopilot phase dispatch payloads from a fixture change.
4. Route through the provider adapter.
5. Verify normalized `(outcome, handoff_id)` handling and no invalid model aliases.

The smoke may use a tiny fixture and dry-run mode for expensive or remote execution, but it must prove the same adapter and model-resolution path that real `/autopilot` uses.

Rationale: provider-neutral dispatch is a runtime behavior, not just a static configuration exercise.

## Open Questions

- Whether the Codex adapter should prefer the in-process harness sub-agent surface when available or the Codex CLI for maximum operator reproducibility.
- Whether Gemini/Jules async dispatch should be smoke-tested in submit-only mode when polling is unavailable.
- Whether logical model tiers should replace `model` in `archetypes.yaml` immediately, or whether a compatibility layer should translate existing `opus`/`sonnet`/`haiku` values first.

