# RI03 integration validation

Date: 2026-07-23

Package: `wp-integration`

Branch tip validated: `aa6b92c0`

## Mandatory deterministic evidence

| Gate | Command | Result |
|---|---|---|
| Shared code-search package | `packages/code-search/.venv/bin/pytest packages/code-search/tests -q -rs` | PASS: 277 passed; 7 live-resource cases explicitly skipped |
| Coordinator query/runtime/surfaces | `agent-coordinator/.venv/bin/pytest agent-coordinator/tests/test_code_search.py agent-coordinator/tests/test_code_search_authorization.py agent-coordinator/tests/test_code_search_imports.py agent-coordinator/tests/test_code_search_runtime.py agent-coordinator/tests/test_code_search_surfaces.py -q` | PASS: 75 passed; one upstream Starlette deprecation warning |
| Capability discovery | `/Users/jankneumann/Coding/agentic-coding-tools/skills/.venv/bin/pytest skills/coordination-bridge/scripts/tests -q` | PASS: 71 passed |
| OpenAPI v2 contract | `agent-coordinator/.venv/bin/pytest openspec/changes/expose-fail-closed-semantic-code-search/tests/test_openapi_contract.py -q` | PASS: 30 passed |
| Strict typing | `agent-coordinator/.venv/bin/mypy src/code_search.py src/code_search_authorization.py src/code_search_runtime.py tests/integration/postgres/test_code_search_v2.py` from `agent-coordinator/` | PASS: no issues in 4 source files |
| Ruff lint | `ruff check` over every RI03-modified Python file, grouped under the coordinator, code-search, and skills configurations | PASS |
| Strict OpenSpec | `openspec validate expose-fail-closed-semantic-code-search --strict` | PASS; non-fatal PostHog telemetry DNS warning followed validation |
| Work-package schema | `skills/.venv/bin/python skills/validate-packages/scripts/validate_work_packages.py openspec/changes/expose-fail-closed-semantic-code-search/work-packages.yaml` | PASS: schema, dependency references, cycles, and lock keys |
| DAG and contracts | `skills/.venv/bin/python skills/parallel-infrastructure/scripts/dag_scheduler.py .../work-packages.yaml --base-dir . --json` | PASS: valid contracts and topological order |
| Parallel zones | `skills/.venv/bin/python skills/refresh-architecture/scripts/parallel_zones.py --validate-packages .../work-packages.yaml --json` | PASS: no parallel scope or lock overlap |
| Integration-package scope | `scope_checker.check_scope_compliance(...)` over the four integration-owned files | PASS: 4 files within `wp-integration.write_allow` |
| Architecture flows | `skills/.venv/bin/python skills/validate-flows/scripts/validate_flows.py --diff cfb74b67...HEAD --output /tmp/ri03-architecture-diagnostics.json` | PASS: 0 findings; graph matched 0 changed entrypoints, so behavioral surface tests remain the substantive flow evidence |
| Review schema | Validate `review-findings-implementation.json` against `openspec/schemas/review-findings.schema.json` with `jsonschema` | PASS |
| Diff hygiene | `git diff --check` | PASS |

Deterministic test total: **453 passed**.

## Resource-deferred evidence

Live evidence was collected as skips, not counted as passes:

- `packages/code-search/tests/test_cocoindex_revision_compat.py`: one case
  deferred because no `POSTGRES_DSN`/live ParadeDB was configured.
- `packages/code-search/tests/test_indexer_e2e.py`: six cases deferred because
  live indexing was not explicitly enabled with its scratch database and
  embedding-provider configuration.
- `agent-coordinator/tests/integration/postgres/test_code_search_v2.py`: six
  RI03 cases deferred because no acknowledged
  `CODE_SEARCH_V2_POSTGRES_DSN` was configured.

The RI03 suite collected all six intended cases: exact canonical success plus
ready status, revision mismatch before embedding, legacy-only exclusion,
provider mismatch before embedding/storage, canonical pointer change without
stale hits, and vanished final storage returning sanitized `unavailable`.

Run the live RI03 suite only against an acknowledged scratch database:

```bash
CODE_SEARCH_V2_POSTGRES_DSN=postgresql://... \
CODE_SEARCH_V2_ALLOW_SCRATCH_MUTATIONS=1 \
agent-coordinator/.venv/bin/pytest \
  agent-coordinator/tests/integration/postgres/test_code_search_v2.py -q
```

## Review disposition

The implementation review is schema-valid and contains no blocking finding.
Production enablement remains contingent on the documented live Postgres,
provider, and retrieval-quality evidence.

NOTICED BUT NOT TOUCHING:
- `agent-coordinator/src/coordination_api.py`,
  `agent-coordinator/src/coordination_mcp.py`,
  `agent-coordinator/src/http_proxy.py`, the OpenAPI contract test, and two
  coordination-bridge files are not whole-file Ruff-format clean — they are
  outside `wp-integration` write scope, Ruff lint is clean, and formatting them
  would widen this package; file a follow-up if whole-repository format
  conformance is required.
