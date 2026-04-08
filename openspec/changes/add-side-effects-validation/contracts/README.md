# Contracts: add-side-effects-validation

## Contract Sub-Types Evaluated

| Sub-Type | Applicable? | Rationale |
|----------|-------------|-----------|
| OpenAPI | No | This change modifies internal evaluation logic (models, evaluator, reports). No API endpoints are added or modified. |
| Database | No | No database schema changes. The DB client remains read-only. Side-effect verification uses existing SELECT queries. |
| Event | No | No event payloads are added or modified. |
| Type generation | No | No cross-language type boundaries are affected. |

## Summary

This change is purely internal to the gen-eval framework — it extends Pydantic models, evaluator logic, report generation, and scenario YAML formats. The contract boundary is the `Scenario` Pydantic model and `ExpectBlock` model defined in `models.py`, which serve as the schema contract between scenario YAML files, generators, and the evaluator. These are validated by Pydantic at load time rather than by separate contract artifacts.
