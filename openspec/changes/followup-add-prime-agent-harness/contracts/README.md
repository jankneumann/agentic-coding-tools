# Contracts — followup-add-prime-agent-harness

Contract sub-types evaluated for this change:

| Sub-type | Applicable | Reason |
|---|---|---|
| **Roster** | **yes** | `roster.md` freezes the canonical provider, binary, agent, profile, coordinator-identity, provider-credential, and conditional dispatch-mode names shared by every package. |
| **Provider map** | **yes** | `provider-model-map.schema.json` is the planned schema-v3 six-provider contract. |
| **CLI dispatch config** | **yes** | `cli-dispatch-config.schema.json` pins the optional cleanup object consumed across the coordinator/dispatcher boundary. |
| **OpenAPI** | **yes** | `openapi/v1.yaml` describes the existing `GET /agents/dispatch-configs` response after it gains the optional cleanup object. |
| Database | no | Generic registry profile and assignment sync already materializes `prime_local`; no migration or new table is required. |
| Events | no | No event type or payload changes. |
| Type generation | no | The config shapes are represented by existing Python dataclasses; tests pin producer/consumer parity directly. |

The load-bearing boundary is that coordinator authentication and model-provider
authentication are different credentials:

- `prime_local_key` / `--prime-local-key` authenticates the `prime-local`
  coordinator identity and is injected as `COORDINATION_API_KEY`.
- `PRIME_API_KEY` is supplied by the operator, declared by
  `prime-local.cli.api_key_env`, and authenticates only to Prime Inference.

No producer, serializer, template, or alias may substitute one for the other.

