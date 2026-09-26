# Change Context: retain-static-model-until-routing-evidence

> Authored after implementation rather than before it (implement-feature step 3a was
> missed at the start and caught before the PR). The tests below were still written first,
> task by task. Req IDs number the scenarios in order so they match the references in
> `tasks.md`: `model-routing.N` is the Nth scenario of "Incumbent Retention Until Routing
> Evidence", and `agent-archetypes.N` is the Nth scenario of "Archetype Resolution Delegates
> to Adaptive Router". Each capability has exactly one requirement, so the requirement-ordinal
> join used by `generate_contract_refs.py` lands on the `.1` rows. It wrote `---` there, because
> no contract document here declares `x-traceability` citations.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| model-routing.1 | specs/model-routing/spec.md | Empty evidence keeps the incumbent (`no-evidence`) | --- | D1, D3 | src/model_routing/resolver.py, src/model_routing/api.py | test_incumbent_retention.py::test_empty_catalog_evidence_keeps_incumbent_despite_alphabetical_order; test_service_incumbent.py::test_empty_evidence_keeps_incumbent_and_persists_reason | deferred: isolated stack has no feasible lanes (all `lane:unavailable`), so `no-evidence` is unreachable there; unit-tested; confirm with the post-deploy coord.rotkohl.ai probe |
| model-routing.2 | specs/model-routing/spec.md | Evidenced challenger below the margin keeps the incumbent (`below-margin`) | --- | D3 | src/model_routing/resolver.py | test_incumbent_retention.py::test_evidenced_challenger_below_margin_keeps_incumbent; test_service_incumbent.py::test_margin_knob_is_read_server_side | deferred: needs an evidenced catalog (none exists until #609/#612); unit-tested |
| model-routing.3 | specs/model-routing/spec.md | Evidenced challenger above the margin displaces the incumbent | --- | D3 | src/model_routing/resolver.py | test_incumbent_retention.py::test_evidenced_challenger_above_margin_displaces_incumbent | deferred: needs an evidenced catalog; unit-tested |
| model-routing.4 | specs/model-routing/spec.md | Ties go to the incumbent at margin 0 | --- | D3 | src/model_routing/resolver.py | test_incumbent_retention.py::test_exact_tie_at_zero_margin_goes_to_incumbent | deferred: needs an evidenced catalog; unit-tested |
| model-routing.5 | specs/model-routing/spec.md | An unresolvable incumbent keeps static with a null selection, still persisted | --- | D2, D5, D8 | src/model_routing/resolver.py, src/model_routing/api.py, src/model_routing/catalog.py, database/migrations/044_routing_decision_retention.sql | test_incumbent_retention.py::test_unresolvable_incumbent_keeps_static_with_null_selection; test_service_incumbent.py::test_unresolved_incumbent_persists_null_selection; test_service_incumbent.py::test_assignment_path_persists_catalogless_retention_against_v12_schema; test_fresh_database_migration.py::test_044_persists_a_catalogless_retention | pass dae6bacc (live: 14/14 vendorless incumbents -> `incumbent-unresolved`, persisted with SQL-null `selected`) |
| model-routing.6 | specs/model-routing/spec.md | An infeasible incumbent gives way to an evidenced alternative | --- | D3 | src/model_routing/resolver.py | test_incumbent_retention.py::test_infeasible_incumbent_with_evidenced_alternative_switches | deferred: needs an evidenced alternative; unit-tested |
| model-routing.7 | specs/model-routing/spec.md | An infeasible incumbent with no evidenced alternative keeps static (null selection) | --- | D3, D5, D8 | src/model_routing/resolver.py, src/model_routing/api.py | test_incumbent_retention.py::test_infeasible_incumbent_without_evidenced_alternative_keeps_static; test_service_incumbent.py::test_all_infeasible_with_incumbent_does_not_raise; test_fresh_database_migration.py::test_044_rejects_a_null_selection_without_retention | pass dae6bacc (live: 70/70 -> `incumbent-infeasible-no-evidenced-alternative`, persisted; CHECK `routing_decisions_selected_or_retention` rejects null selection without retention) |
| model-routing.8 | specs/model-routing/spec.md | Exploration only among evidenced challengers | --- | D4 | src/model_routing/exploration.py, src/model_routing/api.py | test_incumbent_retention.py::test_exploration_never_fires_with_fewer_than_two_evidenced; test_incumbent_retention.py::test_exploration_picks_only_evidenced_non_base_candidates; test_service_incumbent.py::test_exploration_is_inert_on_an_empty_catalog_with_an_incumbent; test_service_incumbent.py::test_evidenced_exploration_records_its_reason | deferred: needs >=2 evidenced candidates; live exploration was inert (0 differences) |
| model-routing.9 | specs/model-routing/spec.md | No incumbent preserves the prior selection and omits `retention` | --- | D4, D5 | src/model_routing/api.py, src/coordination_mcp.py, src/http_proxy.py | test_service_incumbent.py::test_no_incumbent_keeps_prior_behavior_and_omits_retention; test_service_incumbent.py::test_proxy_sends_incumbent_only_when_supplied; test_incumbent_retention.py::test_choose_is_unchanged_without_an_incumbent | pass dae6bacc (live: no-incumbent request keeps prior behavior, 503 on an all-infeasible catalog with no `retention` key) |
| agent-archetypes.1 | specs/agent-archetypes/spec.md | Flag off preserves static behavior | --- | --- | --- (unchanged path) | test_delegation.py::test_adaptive_flag_off_preserves_exact_static_result | pass dae6bacc (live: flag off made 0 router calls, 0 rows) |
| agent-archetypes.2 | specs/agent-archetypes/spec.md | Resolver unavailable preserves static behavior | --- | --- | --- (unchanged path) | test_delegation.py::test_adaptive_error_returns_static_result; test_delegation.py::test_adaptive_timeout_is_bounded_and_returns_static_result | pass dae6bacc (live: unreachable resolver returned the static model/provider in 0.16s) |
| agent-archetypes.3 | specs/agent-archetypes/spec.md | Escalation signals become task signals | --- | --- | --- (unchanged path) | test_delegation.py::test_adaptive_flag_forwards_phase_archetype_and_escalation_signals | deferred: unit-tested; not observable from the persisted request alone |
| agent-archetypes.4 | specs/agent-archetypes/spec.md | Static resolution is forwarded as the incumbent | --- | D2 | src/agents_config.py, src/model_routing/api.py | test_delegation.py::test_static_resolution_is_forwarded_as_the_incumbent; test_delegation.py::test_unknown_provider_forwards_a_vendorless_incumbent; test_delegation.py::test_seam_sends_the_incumbent_and_accepts_a_retained_null_selection | pass dae6bacc (live: 170/170 persisted requests carry the incumbent, e.g. codex/gpt-5.6-terra) |
| agent-archetypes.5 | specs/agent-archetypes/spec.md | A retained incumbent returns the exact static object | --- | D6 | src/agents_config.py | test_delegation.py::test_retention_returns_the_identical_static_object | pass dae6bacc (live: 84/84 retained results equal static; identity is in-process, unit-tested) |
| agent-archetypes.6 | specs/agent-archetypes/spec.md | An evidence-free catalog changes no phase | --- | D1–D6 | src/agents_config.py, src/model_routing/api.py | test_empty_evidence_end_to_end.py::test_every_phase_equals_static_with_the_router_on; test_empty_evidence_end_to_end.py::test_control_the_same_catalog_without_an_incumbent_ignores_the_task | pass dae6bacc (live: 14 phases x 6 providers, 0 differences from static, 0 router errors) |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | A score with no prior and no samples says nothing about the model | `resolver.has_evidence`, `ScoredCandidate.evidenced` | Reads the same two inputs `blend_quality` uses; not serialized |
| D2 | Identity must match catalog rows | `IncumbentIdentity`, `agents_config._catalog_vendor_for_provider` | Exact `(catalog_vendor, model)` match; a wrong guess can only mean "unresolved", which keeps static |
| D3 | Only evidence plus a margin may displace static | `resolver.apply_incumbent_retention` | Pure function, so every retention case is unit-tested |
| D4 | An empty catalog must not produce random picks | `exploration.choose_evidenced` | `choose()` stays untouched, so no-incumbent behavior is identical by construction |
| D5 | Kept-static outcomes must be auditable | `SelectModelResponse.retention`, nullable `selected` | Pre-change clients treat null as an error and fall back to static |
| D6 | Retention is not a fallback | `resolve_archetype_for_phase` returns `static` | The identity (`is`) of the static object is preserved |
| D7 | The archived contract stays untouched | `contracts/openapi/v1.2.yaml` overlay | Follows the v1.1 overlay pattern and is located with `change_dir()` |
| D8 | `routing_decisions` has fixed columns | Migration 044 plus `catalog.record_decision_and_audit` | Added during implementation, with the user's approval; additive and safe in either deploy order |

## Coverage Summary

- **Requirements traced**: 15/15 scenarios
- **Tests mapped**: 15 scenarios have at least one test
- **Evidence collected**: 8/15 live-verified against an isolated stack (`/validate-feature`, 2026-09-25)
- **Gaps identified**: none in unit/integration coverage. The live-catalog smoke check ran on an isolated stack; every catalog lane was `lane:unavailable` there, so the live reasons were `incumbent-unresolved` / `incumbent-infeasible-no-evidenced-alternative` rather than `no-evidence`.
- **Deferred items**: 7. Six need an evidenced catalog (model-routing.1–4, .6, .8 — no evidence source exists until #609/#612); agent-archetypes.3 is unit-only. model-routing.1 (`no-evidence`) is confirmed by the post-deploy coord.rotkohl.ai probe.
