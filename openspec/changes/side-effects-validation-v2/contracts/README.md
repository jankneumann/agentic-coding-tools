# Contracts: side-effects-validation-v2

## Evaluated Contract Sub-Types

| Sub-Type | Applicable? | Reason |
|----------|-------------|--------|
| OpenAPI | No | No new HTTP API endpoints introduced; changes are to internal evaluation models |
| Database | No | No database schema changes; side-effect verification queries existing tables |
| Events | No | No new events introduced |
| Type generation | No | No cross-language type sharing needed |

## Notes

This change extends the gen-eval framework's internal Pydantic models and evaluator logic. All changes are within the `agent-coordinator/evaluation/gen_eval/` module. No external interfaces are added or modified -- the framework continues to consume the same scenario YAML format (with optional new fields) and produce the same verdict/report types (with optional new sub-fields).

The only "contract" is the Pydantic model schema itself, which is self-documenting and validated at parse time.
