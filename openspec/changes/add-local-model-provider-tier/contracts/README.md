# Contracts: add-local-model-provider-tier

Contract sub-type evaluation (per plan-feature Step 7):

- **OpenAPI**: `openapi/v1.yaml` (delta). No endpoint is added and no request
  shape changes; `POST /archetypes/resolve_for_phase` gains one **403** refusal
  response for the `local` provider archetype trust boundary (design D3), with
  detail fields `error`, `phase`, `provider`, `archetype`,
  `permitted_archetypes`. The delta declares only that response — the endpoint's
  baseline (request body, 200/400/401/404/500) is unchanged and lives in the
  archived `add-per-phase-archetype-resolution` contract. The primary contract
  slot in `work-packages.yaml` carries the canonical schema below, which remains
  the coordination boundary for this change.
- **Database**: Not applicable. No schema or data changes; configuration is YAML-only.
- **Events**: Not applicable. No new event payloads; trust-boundary refusals use the
  existing audit-log operation record.
- **Type generation**: Not applicable (single schema consumed by Python validation
  code in `agents_config.py`; tests assert against the schema directly).

## Canonical contract

- `local-roster-entry.schema.json` — the extended roster entry form
  (`model`, `total_params_b`, `active_params_b`, `reviewed`) and host-class
  configuration (`active_params_ceiling_b`, `dense_params_limit_b`) that make the
  MoE-first hardware-matching rule machine-checkable at coordinator startup
  (design D4). This is the coordination boundary between the coordinator package
  (validation implementation) and the dispatch package (roster consumption).

## Adapter environment contract (informational)

The dispatch adapter's configuration surface (design D2/D5), enforced by tests in
`skills/autopilot/scripts/tests/`:

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `LOCAL_INFERENCE_BASE_URL` | yes (to enable) | unset → provider inert | OpenAI-compatible endpoint base URL |
| `LOCAL_INFERENCE_API_KEY` | no | unset | Bearer token if the endpoint requires one |
| `LOCAL_INFERENCE_MAX_CONCURRENCY` | no | 4 | Simultaneous local dispatches; excess queues |
