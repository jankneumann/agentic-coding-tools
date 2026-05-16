# Vendor-Neutral Autopilot Dispatch

## Why

`/autopilot` is intended to orchestrate the full plan-review-implement-validate-PR lifecycle across Claude Code, Codex, and Gemini/Jules, but several current seams still assume a Claude-shaped runtime:

1. **Phase sub-agent dispatch is Claude-harness shaped.** `skills/autopilot/SKILL.md` documents dispatch through a harness `Agent(...)` tool, and `phase_agent.py` still describes production dispatch as Claude Code's `Agent(...)`. Codex exposes a different local sub-agent surface, and Gemini/Jules may be CLI/async rather than an in-process harness tool.
2. **Archetype model names are provider-specific.** `agent-coordinator/archetypes.yaml` resolves `architect`, `reviewer`, `implementer`, `analyst`, and `runner` to `opus`, `sonnet`, and `haiku`. Those are valid Claude-oriented aliases, but invalid or ambiguous for Codex and Gemini dispatch.
3. **Coordinator and dispatch config discovery has Claude-only fallbacks.** `check_coordinator.py` falls back to `claude mcp get coordination`, and `review_dispatcher.py` discovers coordinator config through `~/.claude.json`. Codex- or Gemini-only environments should still be able to use HTTP coordinator discovery or local `agent-coordinator/agents.yaml` fallback.
4. **Called skills inherit the same provider assumptions.** `/plan-feature`, `/implement-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/parallel-review-*`, and `/validate-feature` all participate in the autopilot lifecycle. If their sub-agent/task dispatch guidance, model resolution, or validation helpers remain provider-specific, `/autopilot` only becomes partially portable.
5. **Validation is currently too weak for this kind of change.** A unit-only change could pass while a real CLI session still cannot manually trigger `/autopilot` from Codex or Gemini. The success bar needs an end-to-end smoke path that proves the lifecycle can be manually run from a specific agent CLI, even if the smoke uses a tiny fixture change and stubs expensive external execution.

The goal is not to remove Claude support. The goal is to make Claude Code, Codex, and Gemini/Jules first-class providers behind a common lifecycle contract, while preserving graceful fallback when one provider is unavailable.

## What Changes

- Add a provider-neutral phase dispatch contract for lifecycle skills. The contract separates logical dispatch intent (`phase`, `archetype`, `prompt`, `isolation`, `expected_outcome`) from provider execution details (`Claude Agent(...)`, Codex sub-agent/spawn equivalent, Gemini/Jules CLI or async task).
- Introduce provider-aware model resolution. Archetypes remain logical roles, but dispatch receives provider-specific model IDs based on the selected provider and its configured model map.
- Extend coordinator/config discovery so scripts can find dispatch configuration through HTTP coordinator endpoints, explicit environment variables, local repo config, or provider-native MCP config. Claude config remains supported, but no longer the only non-HTTP path.
- Update `/autopilot` and the skills it calls so their SKILL.md guidance references the provider-neutral dispatch contract instead of Claude-only `Agent(...)` terminology.
- Update runtime helpers and tests around:
  - `skills/autopilot/scripts/phase_agent.py`
  - `skills/autopilot/scripts/runner.py`
  - `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  - `skills/coordination-bridge/scripts/check_coordinator.py`
  - `agent-coordinator/src/agents_config.py`
  - `agent-coordinator/agents.yaml`
  - called lifecycle skill docs under `skills/{plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,parallel-review-plan,parallel-review-implementation,validate-feature}/`
- Update token-budget and audit helpers so their defaults and output are provider-aware rather than Claude-family-only.
- Add an end-to-end smoke test or documented smoke harness that can be manually triggered from a chosen CLI provider and verifies that `/autopilot` can execute through the dispatch path without provider-name leakage or invalid model aliases.

## Out of Scope

- Removing Claude Code support or renaming Claude-specific runtime files that are valid for Claude.
- Replacing the existing multi-vendor review dispatcher wholesale; it is mostly generic and should be extended, not rewritten.
- Implementing a full remote Gemini/Jules production integration if the current CLI cannot provide stable status polling in test. The proposal should define the adapter contract and include the best available smoke coverage.
- Changing the OpenSpec lifecycle gates or removing human approval before merge.
- Solving unrelated active-change work in `harness-engineering-features` or `factory-missions-architecture-alignment`; this proposal should coordinate with those changes and avoid unnecessary overlap.

## Success Criteria

1. `/autopilot` no longer documents or requires a Claude-only `Agent(...)` surface as the canonical sub-agent dispatch path.
2. Provider-specific model IDs are selected from the active provider configuration; `opus`, `sonnet`, and `haiku` are not passed to Codex or Gemini unless explicitly configured as valid aliases for that provider.
3. Coordinator and dispatch config discovery works in at least these modes:
   - HTTP coordinator available.
   - Local repo fallback using `agent-coordinator/agents.yaml`.
   - Claude MCP config when running under Claude Code.
   - Codex/Gemini-compatible fallback that does not require `~/.claude.json`.
4. `/autopilot` and its called lifecycle skills share the same provider-neutral dispatch terminology and do not contradict each other.
5. Unit tests cover provider model mapping, discovery fallback order, adapter selection, and invalid-provider degradation.
6. An end-to-end smoke test or smoke script can be manually run from a selected agent CLI and demonstrates a minimal autopilot lifecycle using that provider's configured dispatch path.

## Approaches Considered

### Approach 1: Documentation and Fallback Cleanup

**Description.** Keep existing inline slash-command fallback as the only cross-provider path. Update docs to say `Agent(...)` is Claude-only, improve warnings, and ensure `--no-review` or inline mode keeps working under Codex and Gemini.

**Pros.**
- Smallest implementation footprint.
- Low risk to existing Claude Code behavior.
- Can land quickly without deep changes to coordinator model resolution.

**Cons.**
- Does not make provider-specific sub-agent dispatch first-class.
- Codex and Gemini would still mostly run via fallback rather than the intended phase-dispatch path.
- Does not solve provider-invalid model aliases except by avoiding the dispatch path.
- Fails the requested end-to-end bar for autopilot running through a provider-specific adapter.

**Effort.** S.

### Approach 2: Provider-Neutral Dispatch Adapter Layer (Recommended)

**Description.** Introduce a small dispatch adapter layer used by `/autopilot` and lifecycle skills. The adapter accepts logical dispatch kwargs from `phase_agent.py`, resolves a provider-specific model from the active agent/provider config, invokes the provider's runtime surface, and returns the normalized `(outcome, handoff_id)` result. Claude Code, Codex, and Gemini/Jules each get an adapter implementation or explicit degradation path.

**Pros.**
- Directly addresses the core portability problem.
- Preserves current archetype concepts while making model IDs provider-specific.
- Lets Claude Code keep using `Agent(...)` while Codex and Gemini use their own execution surfaces.
- Gives tests a clear contract boundary: logical dispatch in, normalized result out.
- Supports the requested manual CLI smoke path.

**Cons.**
- Medium-sized change across autopilot, coordinator config, bridge discovery, and skill docs.
- Requires careful backward compatibility for existing `phase_agent.build_phase_dispatch_kwargs()` callers.
- Gemini/Jules async behavior may need a best-effort adapter with explicit limitations.

**Effort.** M.

### Approach 3: Coordinator-Owned Dispatch Broker

**Description.** Move phase dispatch selection into the coordinator. Skills submit phase-dispatch requests to the coordinator, which chooses provider, model, transport, isolation, and polling strategy based on registered agents and `agents.yaml`.

**Pros.**
- Cleanest long-term architecture for multi-vendor dispatch.
- Centralizes provider availability, model mapping, audit, and routing.
- Makes remote/cloud agent support more natural.

**Cons.**
- Larger cross-system change touching coordinator APIs, work queue semantics, dispatch config, skill runners, and tests.
- Higher migration risk for current local skill execution.
- More likely to conflict with active `factory-missions-architecture-alignment` and `harness-engineering-features` work.
- Overkill for the immediate need to make autopilot manually runnable from current CLIs.

**Effort.** L.

## Recommended Approach

Proceed with **Approach 2: Provider-Neutral Dispatch Adapter Layer**.

This approach directly matches the requested scope: include `/autopilot` and the lifecycle skills it calls, support Claude Code, Codex, and Gemini/Jules, map archetypes to provider-specific model names, and include an end-to-end smoke path that can be manually triggered from a specific agent CLI. It avoids a coordinator rewrite while creating a stable contract that a future coordinator-owned broker could reuse.

### Selected Approach

The operator selected **Approach 2: Provider-Neutral Dispatch Adapter Layer** at Gate 1.

Implementation planning should therefore:

- Treat provider-neutral dispatch as a runtime contract, not only documentation.
- Include `/autopilot` and the lifecycle skills it calls.
- Preserve logical archetypes while resolving provider-specific model IDs for the selected provider.
- Include a manual end-to-end CLI smoke path that can be run from a specific agent CLI to prove `/autopilot` works in that runtime.

### Gate 2 Approval

The operator approved this plan for implementation. The operator also noted that the Gemini model names in the design were updated to match the latest models available via the API, and implementation should preserve those configured model IDs unless a later source check proves they changed again.

## Conflict Notes

- `factory-missions-architecture-alignment` already includes worker/validator vendor diversity work in `review_dispatcher.py`. This proposal should build on that policy, not duplicate it.
- `harness-engineering-features` touches convergence and harness docs. This proposal should avoid broad harness-doc rewrites and focus on provider-neutral dispatch contracts and model/config discovery.
- Existing `skill-workflow` requirements explicitly name `Agent(...)` and Claude model aliases. This proposal will likely need `MODIFIED Requirements` in `skill-workflow` and `agent-archetypes` rather than only adding new requirements.
