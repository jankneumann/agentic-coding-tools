# Change Context: add-local-model-provider-tier

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-archetypes.1 | specs/agent-archetypes/spec.md (MODIFIED: Archetype Definition Schema) | Roster covers exactly claude_code, codex, antigravity, grok, pi, local; local defines standard+economy minimum | contracts/local-roster-entry.schema.json | D1, D7 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py | test_agents_config.py::test_local_provider_defines_its_required_tiers, test_real_archetypes_yaml_local_roster_is_valid, test_default_map_local_tiers_match_the_yaml_roster | pass 06a8951 |
| agent-archetypes.2 | specs/agent-archetypes/spec.md (MODIFIED: Archetype Definition Schema) | Tiers omitted by the local roster resolve via graceful degradation with recorded reasons | contracts/local-roster-entry.schema.json | D7 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py | test_agents_config.py::test_frontier_request_degrades_with_recorded_reason, test_premium_request_degrades_with_recorded_reason, test_best_defined_tier_degradation_is_local_only | pass 06a8951 |
| agent-archetypes.3 | specs/agent-archetypes/spec.md (MODIFIED: Archetype Definition Schema) | Resolution output byte-identical for providers other than local | --- | D6 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py | test_agents_config.py::test_resolution_identical_with_and_without_local_roster | pass 06a8951 |
| agent-archetypes.4 | specs/agent-archetypes/spec.md (ADDED: Local Roster Hardware Matching) | Local roster entries declare total/active params + review date; MoE within host-class active ceiling accepted | contracts/local-roster-entry.schema.json#/$defs/LocalRosterEntry | D4 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py | test_agents_config.py::test_real_archetypes_yaml_local_roster_is_valid, test_active_params_over_host_ceiling_rejected | pass 06a8951 |
| agent-archetypes.5 | specs/agent-archetypes/spec.md (ADDED: Local Roster Hardware Matching) | Dense >=30B entries rejected at startup with structured error on bandwidth-bound host classes | contracts/local-roster-entry.schema.json#/$defs/LocalHostClass | D4 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py | test_agents_config.py::test_dense_large_model_rejected, test_missing_review_date_rejected | pass 06a8951 |
| agent-archetypes.6 | specs/agent-archetypes/spec.md (ADDED: Local Provider Archetype Trust Boundary) | local permitted only for runner/analyst/documenter/validator; permitted resolution notes boundary check | --- | D3 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py, agent-coordinator/src/coordination_api.py | test_agents_config.py::test_permitted_archetype_resolves_locally; test_phase_archetype_resolution.py::test_endpoint_local_permitted_archetype_200 | pass 06a8951 |
| agent-archetypes.7 | specs/agent-archetypes/spec.md (ADDED: Local Provider Archetype Trust Boundary) | architect/reviewer/gatekeeper + local fails with structured, audit-logged error before dispatch | --- | D3 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py, agent-coordinator/src/coordination_api.py | test_agents_config.py::test_boundary_archetype_refused, test_real_config_boundary_phases_refuse_local; test_phase_archetype_resolution.py::test_endpoint_local_boundary_archetype_refused_and_audited; test_coordination_api.py::test_local_trust_boundary_returns_403_and_failed_audit | pass 06a8951 |
| skill-workflow.1 | specs/skill-workflow/spec.md (ADDED: Local Provider Dispatch Adapter) | Configured endpoint dispatches through tool-capable Pi; only explicit final (outcome, handoff_id) succeeds; model_used from roster | contracts/README.md (env contract) | D2 | skills/autopilot/scripts/provider_dispatch.py, skills/autopilot/scripts/pi_local_provider.ts | test_provider_dispatch.py::test_reachable_endpoint_dispatches_through_pi_and_normalizes, test_local_dispatch_uses_tool_capable_agent_harness, test_harness_cannot_complete_without_a_real_handoff, test_local_is_a_supported_provider | pass review-remediation gates |
| skill-workflow.2 | specs/skill-workflow/spec.md (ADDED: Local Provider Dispatch Adapter) | Unset/unreachable endpoint degrades to structured fallback naming local; never hangs; policy engine excluded while probe fails | contracts/README.md (env contract) | D5 | skills/autopilot/scripts/provider_dispatch.py, skills/autopilot-roadmap/scripts/policy.py | test_provider_dispatch.py::test_unset_base_url_degrades_to_fallback_naming_local, test_failing_health_probe_degrades_to_fallback, test_probe_failure_does_not_hang; test_policy.py::test_local_excluded_when_probe_fails | pass 06a8951 |
| skill-workflow.3 | specs/skill-workflow/spec.md (ADDED: Local Provider Dispatch Adapter) | Concurrency cap queues excess dispatches; none dropped or failed solely due to cap | contracts/README.md (env contract) | D5 | skills/autopilot/scripts/provider_dispatch.py | test_provider_dispatch.py::test_concurrency_cap_queues_excess_dispatches, test_default_concurrency_cap_is_four | pass 06a8951 |
| skill-workflow.4 | specs/skill-workflow/spec.md (MODIFIED: Manual Provider Smoke Path) | Smoke selector accepts local (dry-run and real mode); unreachable real-mode reports fallback as outcome; gemini still rejected | --- | D2, D5 | skills/autopilot/scripts/provider_dispatch.py, skills/autopilot/scripts/smoke_provider_dispatch.py | test_autopilot.py::test_smoke_accepts_local_selector_in_dry_run, test_smoke_local_real_mode_unreachable_endpoint_degrades, test_smoke_rejects_gemini_naming_the_supported_roster | pass 06a8951 |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 first-class local provider | Distinct vendor for trust/routing/audit/rate-limit policy | _SUPPORTED_PROVIDERS + model_aliases.local (cc9aa70, 06a8951) | pi precedent; smallest delta reusing tested machinery |
| D2 Pi-backed OpenAI-compatible adapter | Preserve a real agent tool and handoff loop; serving stack remains out of scope | provider_dispatch.py launches Pi; pi_local_provider.ts registers the endpoint for one run | Existing Pi harness is the stable execution boundary; endpoint protocol remains deployment-neutral |
| D3 resolver-enforced trust boundary | Prose gates invisible to unattended loops | LocalProviderTrustBoundaryError in resolve_archetype_for_phase; API 403 + success=False audit (06a8951) | Coordinator is the single decision point |
| D4 machine-checked roster metadata | Rule must be enforceable, not advisory | _validate_local_roster() at load; LocalRosterConfigError (06a8951) | Same fail-fast mechanism as undefined-archetype errors |
| D5 probe + concurrency cap in adapter | Never hang a phase; no switching to dead endpoints | 3s GET {base}/models probe cached; threading.Semaphore cap default 4; policy.py _selectable_alternates gate (cc9aa70) | Structured fallback path already exists |
| D6 byte-identical regression guard | "No behavior change" must be executable | before/after snapshot test over all archetype x provider and phase x provider pairs (06a8951) | Snapshot test over all (archetype x provider) pairs |
| D7 two-model resident MoE roster | Bandwidth-bound GB10; avoid swap scheduling in v1 | standard=gpt-oss-120b 117/5.1, economy=qwen3-coder-30b-a3b 30.5/3.3, reviewed 2026-08-16 (06a8951) | economy small-MoE + standard large-MoE co-resident in 128 GB |

## Review Findings Summary

Independent same-vendor review (C3 fallback: no non-claude vendor CLIs in this
container; vendor-diversity waived with the degradation reported). Verdict
request-changes -> all critical/major fixed -> re-verified green.

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|
| F-01 | wp-dispatch | spec-violation | critical | fixed | Smoke uses INIT/runner inside the boundary; resolver refusal is a hard exit-2 failure, no fallback dispatch |
| F-02 | wp-dispatch | defense-in-depth | major | fixed | Adapter allowlist check before any request; absent/refused archetype degrades to structured fallback (dry-run mirrors) |
| F-03 | wp-dispatch | liveness | major | fixed | Probe cache TTL 30s (monotonic) + invalidation on connection-error dispatch failures |
| F-04 | wp-dispatch | robustness | major | fixed | Wall-clock deadlines via bounded worker (probe 3s, dispatch 300s); semaphore acquire timeout with fallback; slot freed in finally |
| F-05 | wp-coordinator | contract | major | fixed | Served map strips local entries to canonical tierEntry form; schema-validation tests over default and loaded maps |
| F-06 | wp-coordinator | contract | major | fixed | OpenAPI 403 delta added to contracts/openapi/v1.yaml; README no-HTTP-change claim corrected |
| F-07 | wp-dispatch | security | minor | fixed | Base URL scheme restricted to http/https |
| F-08 | wp-dispatch | security | minor | fixed | 10 MB response byte budget, fails closed |
| F-09 | wp-dispatch | concurrency | minor | fixed | Cap read once per process; no semaphore swap |
| F-10 | wp-dispatch | concurrency | minor | fixed | Cold probe single-flight behind lock |
| F-11 | wp-dispatch | documentation | minor | fixed | Docstring + docs state cap is per-process, not host-level |
| F-12 | wp-dispatch | security | minor | fixed | Warnings carry exception class name only; full text at debug |
| F-13 | wp-coordinator | spec-gap | minor | fixed | Local frontier->premium degradation records a reason (falls through to best-defined-tier branch) |
| F-14 | wp-dispatch | spec-violation | minor | fixed | Unresolved model degrades to fallback; no 'default' substitution |
| F-15 | wp-dispatch | operator-ux | minor | deferred | Follow-up filed: bridge should surface 403 trust-boundary distinctly from transport failure (cross-cutting shared resolution path) |
| F-16 | wp-coordinator | validation | minor | fixed | Review dates parsed with date.fromisoformat (regex AND parse); impossible dates rejected |
| F-17 | wp-coordinator | code-clarity | info | fixed | Comment documents jsonschema-first ordering; check guards direct callers |
| F-18 | wp-coordinator | churn | info | fixed | Schema description em-dash restored; diff scoped to enum addition |
| F-19 | wp-coordinator | test-coverage | info | fixed | Contract tests cover local tier rules, strict cloud shapes, unknown providers, and runtime map validation |
| F-20 | wp-dispatch | validation | info | fixed | Concurrency cap clamped to 64 with warning |

## GitHub Review Remediation (2026-08-19)

| Thread | Criticality | Disposition | Resolution |
|--------|-------------|-------------|------------|
| Tool-capable local dispatch | P1 | fixed | Replaced raw `/chat/completions` dispatch with headless Pi plus a one-shot custom-provider extension; final plain text or missing/empty handoff ids fail closed. |
| Stable provider-map schema | P1 | fixed | Canonical schema includes `local`; runtime strips roster metadata and contract tests pin the shape. |
| Missing local premium/frontier tiers | P2 | fixed | Resolver degrades to the best defined local tier with an explicit reason; focused tests cover premium/frontier. |
| HTTP trust-boundary verification | P2 | fixed | Added API-level 403 and failed-audit assertion; coordinator work package now locks the route and API test and verifies both suites. |


## Coverage Summary

- **Requirements traced**: 11/11
- **Tests mapped**: 11 requirements have at least one test
- **Evidence collected**: 11/11 requirements have pass/fail evidence (gates at 06a8951: coordinator 2202 passed + mypy --strict + ruff; skills 2368 passed + ruff; openspec --strict valid)
- **Review findings**: initial 20 (19 fixed, 1 deferred F-15) plus 4 GitHub threads fixed
- **Review-remediation gates**: 197 skills tests + 119 coordinator/API tests; Ruff and strict mypy clean; work-packages valid; OpenSpec strict valid; Pi extension syntax valid under Node 22
- **Gaps identified**: live-service smoke skipped (no Docker daemon in cloud container; soft gate); 7 pre-existing e2e failures in skills/tests/autopilot/test_phase_{dispatch,archetype}_e2e.py confirmed on baseline before this change
- **Deferred items**: ---
