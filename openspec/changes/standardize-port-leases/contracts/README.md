# Contracts: standardize-port-leases

Sub-types evaluated for this change:

| Sub-type | Applies | Artifact |
|---|---|---|
| OpenAPI | yes: five `/ports/*` endpoints, two new | `contracts/openapi/v1.yaml` |
| Database | yes: `port_leases` table, `agent_sessions.isolation_provided`, one function | `contracts/db/schema.sql`, `contracts/db/seed.sql` |
| Event | no: no new events; `coordinator_agent` events are unchanged | none |
| Env contract | yes: the lease env every backend emits | `contracts/schemas/port-lease-env.schema.json` |
| Generated types | deferred to wp-contracts task 1.4 | `contracts/generated/` |

Validate with:

```bash
skills/.venv/bin/python -c 'import json, yaml, jsonschema; \
  s = json.load(open("openspec/changes/standardize-port-leases/contracts/schemas/port-lease-env.schema.json")); \
  jsonschema.Draft202012Validator.check_schema(s); \
  jsonschema.Draft202012Validator(s).validate(s["examples"][0]); \
  yaml.safe_load(open("openspec/changes/standardize-port-leases/contracts/openapi/v1.yaml"))'
psql "$POSTGRES_DSN" -v ON_ERROR_STOP=1 -f openspec/changes/standardize-port-leases/contracts/db/schema.sql
```

The env schema is also the source of truth for the dispatch env allowlist (design D10). Promote
to `openspec/contracts/port-lease-client/` before archiving.
