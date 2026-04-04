# Contracts: add-langfuse-observability

## Contract Sub-Types Evaluated

| Sub-Type | Applicable? | Rationale |
|----------|-------------|-----------|
| OpenAPI | No | No new public API endpoints. The Langfuse middleware traces existing endpoints but does not add or modify any. |
| Database | No | Langfuse uses its own database (`langfuse` on the shared Postgres). No coordinator schema changes. |
| Events | No | No new event types. Langfuse traces are sent to the Langfuse API, not the coordinator event bus. |
| Type Generation | No | No new shared types. `LangfuseConfig` is internal to the coordinator config module. |

## Notes

- The `LangfuseConfig` dataclass follows the established pattern of other config dataclasses in `config.py` and is consumed only within the coordinator process.
- The Langfuse hook (`langfuse_hook.py`) is a standalone script with no shared interface beyond environment variables.
- The Langfuse middleware is internal middleware — it wraps existing endpoints without changing their request/response contracts.
