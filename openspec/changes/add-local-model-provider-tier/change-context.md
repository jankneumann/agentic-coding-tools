# Change Context: add-local-model-provider-tier

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-archetypes.1 | specs/agent-archetypes/spec.md (MODIFIED: Archetype Definition Schema) | Roster covers exactly claude_code, codex, antigravity, grok, pi, local; local defines standard+economy minimum | contracts/local-roster-entry.schema.json | D1, D7 | --- | test_agents_config.py::test_local_provider_resolution | --- |
| agent-archetypes.2 | specs/agent-archetypes/spec.md (MODIFIED: Archetype Definition Schema) | Tiers omitted by the local roster resolve via graceful degradation with recorded reasons | contracts/local-roster-entry.schema.json | D7 | --- | test_agents_config.py::test_local_tier_degradation | --- |
| agent-archetypes.3 | specs/agent-archetypes/spec.md (MODIFIED: Archetype Definition Schema) | Resolution output byte-identical for providers other than local | --- | D6 | --- | test_agents_config.py::test_existing_provider_resolution_unchanged | --- |
| agent-archetypes.4 | specs/agent-archetypes/spec.md (ADDED: Local Roster Hardware Matching) | Local roster entries declare total/active params + review date; MoE within host-class active ceiling accepted | contracts/local-roster-entry.schema.json#/$defs/LocalRosterEntry | D4 | --- | test_agents_config.py::test_local_roster_moe_entry_accepted | --- |
| agent-archetypes.5 | specs/agent-archetypes/spec.md (ADDED: Local Roster Hardware Matching) | Dense >=30B entries rejected at startup with structured error on bandwidth-bound host classes | contracts/local-roster-entry.schema.json#/$defs/LocalHostClass | D4 | --- | test_agents_config.py::test_local_roster_dense_rejected | --- |
| agent-archetypes.6 | specs/agent-archetypes/spec.md (ADDED: Local Provider Archetype Trust Boundary) | local permitted only for runner/analyst/documenter/validator; permitted resolution notes boundary check | --- | D3 | --- | test_agents_config.py::test_local_trust_boundary_permitted | --- |
| agent-archetypes.7 | specs/agent-archetypes/spec.md (ADDED: Local Provider Archetype Trust Boundary) | architect/reviewer/gatekeeper + local fails with structured, audit-logged error before dispatch | --- | D3 | --- | test_agents_config.py::test_local_trust_boundary_refused | --- |
| skill-workflow.1 | specs/skill-workflow/spec.md (ADDED: Local Provider Dispatch Adapter) | Configured endpoint dispatches via OpenAI protocol; normalizes to (outcome, handoff_id); model_used from roster | contracts/README.md (env contract) | D2 | --- | test_provider_dispatch.py::test_local_dispatch_success | --- |
| skill-workflow.2 | specs/skill-workflow/spec.md (ADDED: Local Provider Dispatch Adapter) | Unset/unreachable endpoint degrades to structured fallback naming local; never hangs; policy engine excluded while probe fails | contracts/README.md (env contract) | D5 | --- | test_provider_dispatch.py::test_local_fallback_degradation, test_policy_local_probe_gate | --- |
| skill-workflow.3 | specs/skill-workflow/spec.md (ADDED: Local Provider Dispatch Adapter) | Concurrency cap queues excess dispatches; none dropped or failed solely due to cap | contracts/README.md (env contract) | D5 | --- | test_provider_dispatch.py::test_local_concurrency_cap | --- |
| skill-workflow.4 | specs/skill-workflow/spec.md (MODIFIED: Manual Provider Smoke Path) | Smoke selector accepts local (dry-run and real mode); unreachable real-mode reports fallback as outcome; gemini still rejected | --- | D2, D5 | --- | test_autopilot.py::test_smoke_local_selector | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 first-class local provider | Distinct vendor for trust/routing/audit/rate-limit policy | --- | pi precedent; smallest delta reusing tested machinery |
| D2 OpenAI-compatible adapter | No SDK dependency; serving stack out of scope | --- | Endpoint protocol is the stable boundary |
| D3 resolver-enforced trust boundary | Prose gates invisible to unattended loops | --- | Coordinator is the single decision point |
| D4 machine-checked roster metadata | Rule must be enforceable, not advisory | --- | Same fail-fast mechanism as undefined-archetype errors |
| D5 probe + concurrency cap in adapter | Never hang a phase; no switching to dead endpoints | --- | Structured fallback path already exists |
| D6 byte-identical regression guard | "No behavior change" must be executable | --- | Snapshot test over all (archetype x provider) pairs |
| D7 two-model resident MoE roster | Bandwidth-bound GB10; avoid swap scheduling in v1 | --- | economy small-MoE + standard large-MoE co-resident in 128 GB |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 11/11
- **Tests mapped**: 11 requirements have at least one test
- **Evidence collected**: 0/11 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
