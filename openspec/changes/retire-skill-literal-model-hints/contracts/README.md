# Contracts: retire-skill-literal-model-hints

## Evaluation

| Sub-type | Applicable? | Rationale |
|----------|-------------|-----------|
| OpenAPI | No | No new or modified HTTP endpoints |
| Database | No | No schema or migration changes |
| Event | No | No new event payloads |
| Type generation | No | No OpenAPI/DB sources to generate from |

This change updates skill markdown vocabulary, a pytest CI guard, and OpenSpec
requirement deltas only. Consuming skills treat a `contracts/` directory that
contains only this README as **no contracts applicable**.
