# Contracts: add-model-usage-ledger

Coordination boundary between the eight work packages. Sub-types evaluated:

| Sub-type | Applies | Artifact |
|---|---|---|
| OpenAPI | Yes | `openapi/v1.yaml` — `/usage/ingest`, `/usage/dispatch`, `/usage/summary`, `/usage/by-phase`, `/usage/by-model`, `/usage/mismatches`, `/usage/events` |
| Database | Yes | `db/schema.sql` — `usage_records`, `dispatch_records`, `transcript_events`, `usage_ingest_state`, widened `agent_sessions.phase_archetype` CHECK |
| Events | Yes | `events/usage-record.schema.json`, `events/dispatch-record.schema.json` — payloads the collector and orchestrator emit |
| Generated types | Yes | `generated/models.py` (Pydantic, from OpenAPI schemas), `generated/types.ts` (for `apps/usage-viz`) — produced by task 1.4 |

Config contract referenced but not duplicated here: `agent-coordinator/pricing.yaml` follows the
shape in `cross-vendor-arbitrage-instrument/contracts/config/vendor-pricing-eligibility.schema.json`
(`schema_version`, monotonic `version`, per-vendor per-model USD per Mtok), extended with
`cache_read`, `cache_write`, and optional `thinking` rates. The loader's JSON schema in
`agent-coordinator/src/pricing.py` is the authoritative copy (task 3.4).

Validation (task 1.1–1.3):

```bash
skills/.venv/bin/python -c 'import json, yaml, jsonschema
for p in ("contracts/events/usage-record.schema.json", "contracts/events/dispatch-record.schema.json"):
    jsonschema.Draft202012Validator.check_schema(json.load(open(p)))
yaml.safe_load(open("contracts/openapi/v1.yaml"))'
```
