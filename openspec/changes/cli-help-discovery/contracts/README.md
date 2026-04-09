# Contracts: cli-help-discovery

## Applicable Sub-Types

| Sub-Type | Applicable | Reason |
|----------|-----------|--------|
| OpenAPI | Yes | Adds GET /help and GET /help/{topic} HTTP endpoints |
| Database | No | No schema changes — help content is in-memory |
| Events | No | No new events emitted |
| Type Generation | No | No new shared types — uses plain dicts |

## OpenAPI Contract

See `openapi/v1.yaml` for the help endpoint definitions.
