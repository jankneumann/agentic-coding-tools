# Contracts: Speculative Merge Trains

## Contract Types

| Type | Path | Purpose |
|------|------|---------|
| Internal API | `internal/merge-train-api.yaml` | Python service-layer API for train composition, ejection, status |
| Internal API | `internal/git-adapter-api.yaml` | Git adapter protocol for speculative branch operations |
| Internal API | `internal/test-linker-output.yaml` | Test linker module output schema and affected_tests query interface |
| Database | `db/schema.sql` | JSONB indexes for train state queries |

## Notes

- **No OpenAPI contracts**: This feature extends internal coordinator services, not external HTTP APIs. HTTP/MCP exposure is an integration-phase task that uses the internal API contracts as the specification.
- **No generated types**: Internal API contracts define Python method signatures, not wire protocols. Pydantic models will be defined inline in the implementation modules.
- **Feature flag schema**: `flags.yaml` is a simple YAML file with a JSON Schema validator (task 1.5), not a contract in the OpenAPI sense.
