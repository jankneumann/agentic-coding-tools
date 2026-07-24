# Implementation Findings: add-revision-aware-semantic-index-registry

## Independent Review

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | contract mismatch | high | A promoted canonical index could be mutated away from the required ready/main/same-repository shape through direct SQL. | Fixed with an index-side deferrable constraint trigger and structural/live regressions. |
| 2 | resilience | high | A crashed collector left an expired `deleting` lease that no later collector could reclaim. | Fixed with expired deleting-lease takeover and an idempotent deletion contract. |
| 3 | contract mismatch | high | Missing repositories raised a raw foreign-key error instead of `IndexNotFoundError`. | Fixed by ensuring through `INSERT ... SELECT` from the repository row. |
| 4 | contract mismatch | medium | The JSON Schema accepted a deleted record without `deleted_at`. | Fixed with a deleted-state conditional and executable lifecycle schema tests. |

## Validation Review

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 5 | architecture | medium | `registry.py` exceeded the 500-line structural limit. | Fixed by extracting pure identity and record contracts to `registry_models.py`; final structural linter has no findings. |
| 6 | environment evidence | low | Live PostgreSQL tests could not run because `POSTGRES_DSN` is unset and Docker is unavailable. | Accepted as deferred supplemental evidence; structural, repository, and schema regressions pass. |
| 7 | tooling gap | medium | Default architecture analysis excludes `packages/code-search`, and `make architecture-validate` points to a removed validator path. | Recorded for follow-up; direct graph-schema, changed-file flow, and structural validators pass. |
