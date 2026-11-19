# Architecture Impact: add-project-keyed-gate-projection

Commit: 80e92b1
Branch: claude/eloquent-edison-tn8alg
Base: f8a7da6 (merge-base against main)

## Changed Files

- `agent-coordinator/database/migrations/047_gate_projection.sql` (new): one table, one row per project
- `agent-coordinator/src/gate_projection.py` (new): the service
- `agent-coordinator/src/gate_projection_routes.py` (new): four `/gates/*` routes
- `agent-coordinator/src/approval.py`: `get_requests`, a lookup by id list
- `agent-coordinator/src/config.py`: `GateProjectionConfig`
- `agent-coordinator/src/coordination_api.py`: installs the routes
- `agent-coordinator/tests/`: three new test files, one extended
- `openspec/contracts/agent-coordinator/openapi/gates.yaml` (new)
- `skills/supervise/scripts/gate_projection.py` (new) and `skills/supervise/SKILL.md`
- `skills/tests/supervise/test_gate_projection.py` (new)
- `agent-coordinator/CLAUDE.md`: routes and environment variables

## Structural Diff

`make architecture-diff BASE_SHA=f8a7da6`: +195/-40 nodes, +85/-9 edges, 2 new
high-impact modules, 7 routes without tests, 3 database tables. The previous
roadmap item measured +150/-40 nodes, +43/-3 edges, 3 routes and 2 tables
against the same base, so this change accounts for about 45 nodes, 42 edges,
4 routes and 1 table.

### New Cross-Layer Flows

- `skills/supervise/scripts/gate_projection.py push` → `POST /gates/projection` → `gate_projection` table
- `GET /gates/pending` → `gate_projection` table and the approval service
- `POST /gates/decide` → the approval service

### Broken Cross-Layer Flows

None.

### New High-Impact Nodes

None from this change. `gate_projection.py` is imported by its routes module only.

## Validation Findings

`validate_flows.py` on the changed files: 93 entrypoints, 0 errors, 612
findings, 70 of them naming the new code.

| Severity | Category | Count | Note |
|---|---|---|---|
| warning | disconnected_flow | 4 | The routes have no frontend caller. Expected: the caller is a later roadmap item |
| warning | test_coverage | 33 | The analyzer finds coverage for 0 of 264 flows in scope, tested or not |
| warning | orphan | 29 | Service and collector helpers reached through the installer function or the command line |
| info | reachability | 4 | The analyzer does not follow the service's database calls |

`run_architecture_linters.py` on the changed files:

| Severity | Category | Description | File |
|---|---|---|---|
| nit | architecture | 860 lines, over the 500-line limit; this change added 30 | `agent-coordinator/src/config.py` |
| nit | architecture | 4072 lines, over the 500-line limit; this change added 4 | `agent-coordinator/src/coordination_api.py` |

## Parallel Zone Impact

The routes are installed by a function in their own module, so later changes to
them do not contend for `coordination_api.py`.

## Recommendations

- A review surface should read `GET /gates/pending` and treat a project marked
  degraded as unknown, not as empty.
- Before any gate is made decidable through `POST /gates/decide`, run
  `get_requests` against PostgreSQL.
