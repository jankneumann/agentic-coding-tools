# Contracts: consolidate-model-tier-sources

No new API contracts (no OpenAPI, DB, or event schemas).

The behavioral contract is the existing shape of:

| Artifact | Role |
|---|---|
| `agent-coordinator/archetypes.yaml` (`model_aliases`, `archetypes`, `phase_mapping`) | Sole authored tier→model and task→tier sources |
| `openspec/schemas/provider-model-map.schema.json` | Normalized provider map shape (schema_version 2); YAML `model_aliases` is normalized into this shape at load time |
| `DEFAULT_PROVIDER_MODEL_MAP` | Emergency fallback only when YAML cannot be loaded — not an authored twin |

Contract tests MUST resolve the stable schema path under `openspec/schemas/`,
never a schema inside this change directory.
