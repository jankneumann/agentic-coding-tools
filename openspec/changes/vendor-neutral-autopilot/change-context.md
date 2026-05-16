# Change Context: vendor-neutral-autopilot

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| configuration.1 | specs/configuration/spec.md | Discover provider dispatch configuration without depending on Claude-specific config files. | --- | D4 | skills/parallel-infrastructure/scripts/review_dispatcher.py; skills/coordination-bridge/scripts/check_coordinator.py | skills/tests/vendor-neutral-autopilot/test_config_discovery.py | pass local validation |
| configuration.2 | specs/configuration/spec.md | Define provider model mappings for Claude Code, Codex, and Gemini/Jules. | contracts/provider-model-map.schema.json | D3 | agent-coordinator/archetypes.yaml; agent-coordinator/src/agents_config.py | skills/tests/vendor-neutral-autopilot/test_contracts.py; skills/tests/vendor-neutral-autopilot/test_model_resolution.py | pass local validation |
| agent-archetypes.1 | specs/agent-archetypes/spec.md | Resolve archetype model values through provider-aware model mapping before dispatch. | contracts/provider-model-map.schema.json | D3 | agent-coordinator/src/agents_config.py; agent-coordinator/src/coordination_api.py | skills/tests/vendor-neutral-autopilot/test_model_resolution.py | pass local validation |
| agent-archetypes.2 | specs/agent-archetypes/spec.md | Predefined archetypes map to logical model tiers that translate per provider. | contracts/provider-model-map.schema.json | D3 | agent-coordinator/archetypes.yaml; agent-coordinator/agents.yaml | skills/tests/vendor-neutral-autopilot/test_model_resolution.py | pass local validation |
| agent-archetypes.3 | specs/agent-archetypes/spec.md | Provider model selection integrates with same-provider fallback chains. | contracts/provider-model-map.schema.json | D3 | agent-coordinator/agents.yaml; skills/parallel-infrastructure/scripts/review_dispatcher.py | agent-coordinator/tests/test_archetypes_config.py; skills/tests/vendor-neutral-autopilot/test_model_resolution.py | pass local validation |
| agent-archetypes.4 | specs/agent-archetypes/spec.md | Work queue routing supports archetype and provider requirements. | --- | D3 | agent-coordinator/agents.yaml; agent-coordinator/src/agents_config.py | agent-coordinator/tests/test_phase_archetype_resolution.py | pass local validation |
| skill-workflow.1 | specs/skill-workflow/spec.md | Autopilot resolves per-phase archetypes and builds provider-neutral dispatch payloads. | contracts/phase-dispatch-contract.md | D1, D2, D3 | skills/autopilot/scripts/phase_agent.py; skills/autopilot/scripts/provider_dispatch.py | skills/tests/vendor-neutral-autopilot/test_dispatch_adapter.py; skills/tests/autopilot/test_build_phase_dispatch_kwargs.py | pass local validation |
| skill-workflow.2 | specs/skill-workflow/spec.md | Phase model override forces provider model IDs without changing archetype. | contracts/phase-dispatch-contract.md | D1, D3 | skills/autopilot/scripts/phase_agent.py; skills/autopilot/scripts/runner.py | skills/tests/autopilot/test_build_phase_dispatch_kwargs.py | pass local validation |
| skill-workflow.3 | specs/skill-workflow/spec.md | Bridge or adapter failure falls back gracefully with structured warnings. | contracts/phase-dispatch-contract.md | D2, D4 | skills/autopilot/scripts/provider_dispatch.py; skills/coordination-bridge/scripts/coordination_bridge.py | skills/tests/vendor-neutral-autopilot/test_dispatch_adapter.py; skills/tests/coordination-bridge/test_archetype_resolve.py | pass local validation |
| skill-workflow.4 | specs/skill-workflow/spec.md | Expose helper entry points for provider-neutral phase dispatch payloads and outcome application. | contracts/phase-dispatch-contract.md | D1, D2 | skills/autopilot/scripts/phase_agent.py; skills/autopilot/scripts/runner.py | skills/tests/vendor-neutral-autopilot/test_dispatch_adapter.py; skills/tests/autopilot/test_runner_cli.py | pass local validation |
| skill-workflow.5 | specs/skill-workflow/spec.md | Joined prompt token budget reporting is provider aware. | --- | D3 | skills/autopilot/scripts/token_budget_check.py | skills/tests/autopilot/test_token_budget_check.py | pass local validation |
| skill-workflow.6 | specs/skill-workflow/spec.md | Lifecycle skills use provider-neutral dispatch terminology. | --- | D5 | skills/autopilot/SKILL.md; skills/plan-feature/SKILL.md; skills/implement-feature/SKILL.md; skills/iterate-on-plan/SKILL.md; skills/iterate-on-implementation/SKILL.md; skills/parallel-review-plan/SKILL.md; skills/parallel-review-implementation/SKILL.md; skills/validate-feature/SKILL.md | skills/tests/vendor-neutral-autopilot/test_lifecycle_docs.py | pass local validation |
| skill-workflow.7 | specs/skill-workflow/spec.md | Manual provider smoke path exercises model mapping and adapter normalization. | contracts/phase-dispatch-contract.md; contracts/provider-model-map.schema.json | D6 | skills/autopilot/scripts/smoke_provider_dispatch.py; docs/autopilot-provider-smoke.md | skills/tests/vendor-neutral-autopilot/test_smoke_provider_dispatch.py | pass local validation |
| coordination-bridge.1 | specs/coordination-bridge/spec.md | Coordinator detection does not require Claude Code and preserves capability flags. | --- | D4 | skills/coordination-bridge/scripts/check_coordinator.py | skills/tests/vendor-neutral-autopilot/test_config_discovery.py | pass local validation |
| coordination-bridge.2 | specs/coordination-bridge/spec.md | HTTP bridge helpers use uniform failure envelopes with provider context in warnings. | --- | D4 | skills/coordination-bridge/scripts/coordination_bridge.py | skills/tests/vendor-neutral-autopilot/test_config_discovery.py; skills/tests/coordination-bridge/test_archetype_resolve.py | pass local validation |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Keep the prose-to-Python boundary stable while removing Claude-only dispatch assumptions. | `build_phase_dispatch_payload()` and runner `--provider` support. | Smallest compatible extension to existing helpers. |
| D2 | Normalize provider execution behind a common adapter result. | `provider_dispatch.py` and smoke dry-run adapter path. | Lets CLI/harness specifics stay internal to adapters. |
| D3 | Prevent Claude model aliases from leaking to Codex or Gemini. | Provider model maps and provider-aware archetype resolution. | Preserves legacy Claude aliases while translating for other providers. |
| D4 | Make discovery work without `~/.claude.json`. | HTTP-first/local `agents.yaml` config discovery and provider-aware bridge warnings. | Keeps Claude config as fallback, not a dependency. |
| D5 | Keep lifecycle skills consistent for all providers. | Documentation scan and lifecycle skill wording updates. | Prevents future skills from reintroducing Claude-only normative language. |
| D6 | Prove behavior through a manual CLI smoke path. | `smoke_provider_dispatch.py` dry-run and tests for Codex/Gemini. | Exercises the same model-resolution and adapter-normalization path without requiring paid remote execution. |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 15/15
- **Tests mapped**: 15 requirements have at least one test
- **Evidence collected**: 15/15 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
