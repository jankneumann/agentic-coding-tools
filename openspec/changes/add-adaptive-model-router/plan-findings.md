# Plan Findings

## Iteration 1

<!-- Date: 2026-08-24 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | consistency | high | Concrete primary and fallback models are duplicated across `agents.yaml`, `archetypes.yaml`, and Python defaults, so harness configuration can drift from task/archetype policy. | Added D14 and requirements making `agents.yaml` mechanics-only and `archetypes.yaml` the sole curated static model-policy authority. |
| 2 | completeness | high | Removing model keys from YAML alone would break SDK validation plus synchronous CLI, asynchronous CLI, SDK, discovery, and health consumers that read those fields today. | Added decomposed tasks 4.7–4.9 covering characterization, versioned route resolution, consumer migration, and removal of legacy fields/defaults. |
| 3 | consistency | high | Canonical `agent-archetypes` and `skill-workflow` requirements explicitly place fallback models in `agents.yaml`, contradicting the requested ownership boundary. | Added MODIFIED spec deltas for fallback integration, CLI/SDK schemas, retry behavior, and configurable fallback chains. |
| 4 | testability | high | The plan had no invariant proving every configured harness/task combination resolves a concrete model or that missing mappings fail before dispatch. | Added cross-file coverage, orphan-route rejection, ambient-default prohibition, sync/async/SDK parity, and sole-source structural acceptance scenarios. |
| 5 | parallelizability | medium | The migration touches files locked by both `wp-resolver` and `wp-dispatch`; assigning it to either package would create write-scope overlap. | Added `wp-model-config-ownership` depending on both packages, with its own locks, scope, verification, and integration dependency. |
| 6 | consistency | medium | Task-sizing notes still described only one large package after adding the second cross-layer migration package. | Updated the sizing rationale to identify and decompose both large packages consistently with `work-packages.yaml`. |
| 7 | parallelizability | high | The new package used a non-canonical `config:` lock namespace, so the package validator rejected an otherwise non-overlapping DAG. | Replaced it with the canonical `feature:add-adaptive-model-router:models` lock and revalidated all package and parallel-zone checks. |
| 8 | contract mismatch | high | The current v2 provider model-map schema cannot express exact agent-harness, dispatch-kind, tier, and ordered `ModelSpec` chains. | D14 and task 4.8 now require a v3 `routes[agent_id][dispatch_kind][tier]: ModelSpec[]` contract, migration-only v2 reading, and mixed-version rejection. |
| 9 | compatibility | high | Existing `agents.yaml` primary and fallback values could be removed before being seeded into the new authority. | Tasks 4.7–4.9 and the migration scenario now characterize every chain, seed v3 routes, prove selection/retry parity, then switch consumers and remove legacy fields atomically. |
| 10 | architecture | high | Adaptive selection did not define how its single candidate composes with static capacity fallbacks. | Defined adaptive primary-only replacement, selected thinking propagation, ordered static `capacity_fallbacks`, selected-model deduplication, and separate decisions for ranked alternatives. |
| 11 | correctness | high | Task 3.10 appeared to depend on the new D14 route data before the migration package created it. | Kept 3.10 behind the default-off flag on the characterized legacy static path until task 4.9 performs the parity-gated atomic cutover. |
| 12 | contract mismatch | medium | The HTTP/MCP request lacked `agent_id` and `dispatch_kind`, while the candidate omitted thinking and the response omitted its capacity chain. | Updated the OpenAPI and coordinator/model-routing requirements with route scope, thinking, and ordered `capacity_fallbacks`. |
| 13 | completeness | medium | Discovery, bridge, and health migrations were tasks only, without normative projection behavior. | Added `skill-workflow.5` requiring transport parity and forbidding health/discovery from inventing ambient model IDs. |
| 14 | testability | medium | `wp-probes` omitted tasks 6.7–6.8 from its description and its test filter did not match quota tests. | Expanded the package to tasks 6.1–6.8 and changed verification to `-k 'probes or tripwires or quota'`. |

### Quality Checks

- Baseline: `openspec validate add-adaptive-model-router --strict` passed before refinement.
- Post-refinement: strict OpenSpec validation, YAML integrity, and diff hygiene checks passed.
- Review: the schema-valid primary review plus successful Antigravity and Grok reviews met 3/3
  synthesis quorum. Claude Code timed out and Pi was unavailable for billing/credits; all seven
  external medium/high findings were remediated once without re-dispatch.
- Requirements use SHALL/SHALL NOT and include success plus failure/edge scenarios.
- New tasks trace to D14, agent-archetypes, and skill-workflow scenarios.

### Parallelizability Assessment

- Independent tasks/packages: 4 unaffected package lanes remain available alongside the resolver/dispatch chain.
- Sequential chains: 1 added chain (`4.7 -> 4.8 -> 4.9`).
- Max parallel width: 5 packages in the existing DAG.
- File overlap conflicts: none after sequencing `wp-model-config-ownership` behind both `wp-resolver` and `wp-dispatch`.

---

## Summary

- Total iterations: 1
- Total findings addressed: 14
- Remaining findings below threshold: none
- Termination reason: threshold met
