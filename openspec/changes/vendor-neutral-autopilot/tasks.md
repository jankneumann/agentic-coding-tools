# Tasks - vendor-neutral-autopilot

## Phase 1 - Contracts (wp-contracts)

- [x] 1.1 Write contract validation tests for provider model map schema
  **Spec scenarios**: configuration (Provider map includes all first-class providers)
  **Contracts**: contracts/provider-model-map.schema.json
  **Design decisions**: D3
  **Dependencies**: None
  **Size**: S

- [x] 1.2 Write contract validation tests for phase dispatch payload schema
  **Spec scenarios**: skill-workflow (build_phase_dispatch_payload returns provider-neutral payload)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D1, D2
  **Dependencies**: None
  **Size**: S

- [x] 1.3 Implement reusable contract fixtures for provider mappings
  **Spec scenarios**: configuration (Provider map includes all first-class providers)
  **Contracts**: contracts/provider-model-map.schema.json
  **Dependencies**: 1.1
  **Size**: S

- [x] 1.4 Checkpoint: run contract tests plus `openspec validate vendor-neutral-autopilot --strict`
  **Dependencies**: 1.1, 1.2, 1.3

## Phase 2 - Model Resolution (wp-model-resolution)

- [x] 2.1 Write tests for Claude provider archetype mapping
  **Spec scenarios**: agent-archetypes (Architect archetype maps per provider), skill-workflow (Claude remains supported)
  **Contracts**: contracts/provider-model-map.schema.json
  **Design decisions**: D3
  **Dependencies**: 1.4
  **Size**: S

- [x] 2.2 Write tests for Codex provider archetype mapping
  **Spec scenarios**: agent-archetypes (Archetype resolves for Codex provider), configuration (Non-Claude provider rejects unmapped Claude alias)
  **Contracts**: contracts/provider-model-map.schema.json
  **Design decisions**: D3
  **Dependencies**: 1.4
  **Size**: S

- [x] 2.3 Write tests for Gemini provider archetype mapping
  **Spec scenarios**: agent-archetypes (Archetype resolves for Gemini provider), configuration (Provider map includes all first-class providers)
  **Contracts**: contracts/provider-model-map.schema.json
  **Design decisions**: D3
  **Dependencies**: 1.4
  **Size**: S

- [x] 2.4 Checkpoint: confirm provider model tests fail before implementation
  **Dependencies**: 2.1, 2.2, 2.3

- [x] 2.5 Add provider model map support to agent config loading
  **Spec scenarios**: configuration (Provider map includes all first-class providers), agent-archetypes (Architect archetype maps per provider)
  **Contracts**: contracts/provider-model-map.schema.json
  **Design decisions**: D3
  **Dependencies**: 2.4
  **Size**: M

- [x] 2.6 Resolve archetypes to provider-specific model IDs
  **Spec scenarios**: agent-archetypes (Archetype resolves for Codex provider), agent-archetypes (Archetype resolves for Gemini provider)
  **Contracts**: contracts/provider-model-map.schema.json
  **Design decisions**: D3
  **Dependencies**: 2.5
  **Size**: M

- [x] 2.7 Confirm model resolution tests pass
  **Dependencies**: 2.5, 2.6
  **Size**: XS

## Phase 3 - Config Discovery (wp-config-discovery)

- [x] 3.1 Write tests for HTTP-first coordinator detection without Claude CLI
  **Spec scenarios**: coordination-bridge (HTTP transport available without Claude CLI)
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Size**: S

- [x] 3.2 Write tests for local agents.yaml dispatch config fallback
  **Spec scenarios**: configuration (Local agents.yaml fallback), configuration (Explicit config path wins)
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Size**: S

- [x] 3.3 Write tests for provider-context warnings
  **Spec scenarios**: coordination-bridge (Archetype helper includes provider context in warnings)
  **Design decisions**: D4
  **Dependencies**: 1.4
  **Size**: S

- [x] 3.4 Checkpoint: confirm config discovery tests fail before implementation
  **Dependencies**: 3.1, 3.2, 3.3

- [x] 3.5 Make coordinator detection provider-neutral
  **Spec scenarios**: coordination-bridge (HTTP transport available without Claude CLI), coordination-bridge (No provider-native MCP config exists)
  **Design decisions**: D4
  **Dependencies**: 3.4
  **Size**: M

- [x] 3.6 Add dispatch config discovery fallback order
  **Spec scenarios**: configuration (Local agents.yaml fallback), configuration (Explicit config path wins)
  **Design decisions**: D4
  **Dependencies**: 3.4
  **Size**: M

- [x] 3.7 Confirm config discovery tests pass
  **Dependencies**: 3.5, 3.6
  **Size**: XS

## Phase 4 - Dispatch Adapter (wp-dispatch-adapter)

- [x] 4.1 Write tests for provider-neutral dispatch payload creation
  **Spec scenarios**: skill-workflow (build_phase_dispatch_payload returns provider-neutral payload)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D1, D2
  **Dependencies**: 2.7, 3.7
  **Size**: S

- [x] 4.2 Write tests for Claude adapter compatibility
  **Spec scenarios**: skill-workflow (Claude remains supported)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D2
  **Dependencies**: 2.7, 3.7
  **Size**: S

- [x] 4.3 Write tests for Codex adapter result normalization
  **Spec scenarios**: skill-workflow (Production autopilot run dispatches through provider adapter), skill-workflow (Codex CLI smoke succeeds)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D2, D6
  **Dependencies**: 2.7, 3.7
  **Size**: S

- [x] 4.4 Write tests for Gemini adapter result normalization
  **Spec scenarios**: skill-workflow (Gemini CLI smoke succeeds in configured mode), skill-workflow (Provider adapter unavailable falls back gracefully)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D2, D6
  **Dependencies**: 2.7, 3.7
  **Size**: S

- [x] 4.5 Checkpoint: confirm adapter tests fail before implementation
  **Dependencies**: 4.1, 4.2, 4.3, 4.4

- [x] 4.6 Implement dispatch payload builder in autopilot runner
  **Spec scenarios**: skill-workflow (build_phase_dispatch_payload returns provider-neutral payload)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D1
  **Dependencies**: 4.5
  **Size**: M

- [x] 4.7 Implement provider dispatch adapter module
  **Spec scenarios**: skill-workflow (Production autopilot run dispatches through provider adapter), skill-workflow (Provider adapter unavailable falls back gracefully)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D2
  **Dependencies**: 4.6
  **Size**: M

- [x] 4.8 Wire autopilot SKILL.md dispatch blocks to adapter contract
  **Spec scenarios**: skill-workflow (Production autopilot run dispatches through provider adapter), skill-workflow (Skill docs do not make Agent the canonical cross-provider path)
  **Design decisions**: D5
  **Dependencies**: 4.7
  **Size**: S

- [x] 4.9 Confirm dispatch adapter tests pass
  **Dependencies**: 4.6, 4.7, 4.8
  **Size**: XS

## Phase 5 - Lifecycle Skill Updates (wp-skill-docs)

- [x] 5.1 Write scan test for Claude-only dispatch terminology
  **Spec scenarios**: skill-workflow (Skill docs do not make Agent the canonical cross-provider path)
  **Design decisions**: D5
  **Dependencies**: 1.4
  **Size**: S

- [x] 5.2 Write scan test for provider-neutral lifecycle terminology
  **Spec scenarios**: skill-workflow (Skill docs do not make Agent the canonical cross-provider path)
  **Design decisions**: D5
  **Dependencies**: 1.4
  **Size**: S

- [x] 5.3 Checkpoint: confirm lifecycle doc scan tests fail before updates
  **Dependencies**: 5.1, 5.2

- [x] 5.4 Update autopilot lifecycle skill documentation
  **Spec scenarios**: skill-workflow (Skill docs do not make Agent the canonical cross-provider path)
  **Design decisions**: D5
  **Dependencies**: 5.3, 4.8
  **Size**: M

- [x] 5.5 Update called lifecycle skill documentation
  **Spec scenarios**: skill-workflow (Skill docs do not make Agent the canonical cross-provider path)
  **Design decisions**: D5
  **Dependencies**: 5.3
  **Size**: M

- [x] 5.6 Confirm lifecycle doc scan tests pass
  **Dependencies**: 5.4, 5.5
  **Size**: XS

## Phase 6 - Smoke Harness (wp-smoke)

- [x] 6.1 Write smoke harness tests for Codex dry-run
  **Spec scenarios**: skill-workflow (Codex CLI smoke succeeds)
  **Contracts**: contracts/phase-dispatch-contract.md, contracts/provider-model-map.schema.json
  **Design decisions**: D6
  **Dependencies**: 4.9
  **Size**: S

- [x] 6.2 Write smoke harness tests for Gemini dry-run
  **Spec scenarios**: skill-workflow (Gemini CLI smoke succeeds in configured mode)
  **Contracts**: contracts/phase-dispatch-contract.md, contracts/provider-model-map.schema.json
  **Design decisions**: D6
  **Dependencies**: 4.9
  **Size**: S

- [x] 6.3 Write smoke harness test for invalid model alias rejection
  **Spec scenarios**: configuration (Non-Claude provider rejects unmapped Claude alias)
  **Contracts**: contracts/provider-model-map.schema.json
  **Design decisions**: D3, D6
  **Dependencies**: 4.9
  **Size**: S

- [x] 6.4 Checkpoint: confirm smoke tests fail before implementation
  **Dependencies**: 6.1, 6.2, 6.3

- [x] 6.5 Implement provider smoke harness
  **Spec scenarios**: skill-workflow (Manual Provider Smoke Path), skill-workflow (Codex CLI smoke succeeds), skill-workflow (Gemini CLI smoke succeeds in configured mode)
  **Contracts**: contracts/phase-dispatch-contract.md
  **Design decisions**: D6
  **Dependencies**: 6.4
  **Size**: M

- [x] 6.6 Document manual smoke invocation
  **Spec scenarios**: skill-workflow (Manual Provider Smoke Path)
  **Design decisions**: D6
  **Dependencies**: 6.5
  **Size**: S

- [x] 6.7 Confirm smoke harness tests pass
  **Dependencies**: 6.5, 6.6
  **Size**: XS

## Phase 7 - Integration (wp-integration)

- [x] 7.1 Run focused model resolution tests
  **Dependencies**: 2.7
  **Size**: XS

- [x] 7.2 Run focused config discovery tests
  **Dependencies**: 3.7
  **Size**: XS

- [x] 7.3 Run focused adapter tests
  **Dependencies**: 4.9
  **Size**: XS

- [x] 7.4 Run lifecycle documentation scan tests
  **Dependencies**: 5.6
  **Size**: XS

- [x] 7.5 Run smoke harness tests
  **Dependencies**: 6.7
  **Size**: XS

- [x] 7.6 Checkpoint: run `openspec validate vendor-neutral-autopilot --strict`, work-package validation, plus full relevant pytest subset
  **Dependencies**: 7.1, 7.2, 7.3, 7.4, 7.5
