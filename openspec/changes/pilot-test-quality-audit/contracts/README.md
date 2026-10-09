# Contracts: pilot-test-quality-audit

These contracts form the boundary between the stage work packages, and between this package and its
two future consumers: ri-07 `add-mutation-score-guardrail` and ri-08
`calibrate-llm-judge-against-human-labels`.

| File | Contract | Producers | Consumers |
|---|---|---|---|
| `schemas/stage-record.schema.json` | One JSONL line per test per stage, joined on `test_id` (D1) | every stage module | `analysis.py`, `explain.py`, `labels.py` |
| `schemas/label-ledger.schema.json` | Human oracle-source labels, a sidecar keyed by node id + content hash (D2, D9) | `labels.py` | `analysis.py`, ri-08 |
| `schemas/mutation-result.schema.json` | Per-mutant results with per-test attribution (D4) | `mutation.py` | `analysis.py`, ri-07 |
| `schemas/analysis-report.schema.json` | Metrics, candidates, disagreements, open decisions (D10, D11, D13) | `analysis.py` | `report.py` |
| `schemas/skill-audit-kinds.delta.json` | Append-only `kind` enum extension for skill-audit findings (D12) | `wp-skill-audit-lens` | skill-audit ledger validation |

## Sub-types evaluated

- **OpenAPI: not applicable.** No HTTP endpoint is added or changed.
- **Database: not applicable.** No coordinator schema change. All output is files.
- **Events: JSON Schemas above.** The "events" are JSONL records on disk, not bus messages.
- **Generated types: not generated.** The package defines frozen dataclasses in `records.py` that
  mirror these schemas. Contract tests (task 1.1) validate the dataclasses' `to_json()` output
  against the schemas, so the schemas, not the code, are the source of truth.

## Stability

Every schema carries `schema_version: 1`. Adding optional fields is non-breaking. Removing or
renaming a field, or narrowing an enum, needs `schema_version: 2` and a note to ri-07 and ri-08.
