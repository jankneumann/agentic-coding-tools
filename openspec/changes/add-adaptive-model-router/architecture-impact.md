# Architecture Impact: add-adaptive-model-router (dg-00)

**Runtime checkpoint analyzed**: `67ff34d831b788abf8ec31db8405c77c8919cb37`
**Base**: `c523ad8c3197986a1689326841b0976ecc9f426a`

## Status

**PASS WITH QUALIFICATIONS** — A staged refresh using the repository's Makefile-defined
source roots completed successfully, the refreshed graph is current, the changed-file flow
validator returned zero findings, and the baseline diff contains no new dependency cycle.

## Changed Surface

The runtime change adds a coordinator-owned model-routing service, five HTTP routes, one MCP
selection tool, four additive PostgreSQL tables, three independent watchdog jobs, bounded
adaptive-to-static delegation, and OpenAI-compatible dispatcher discovery. It reuses the
resolver, exploration, feedback, pricing, and adapter core already on `main` from PR #237.

## Structural Diff

- Nodes added/removed: 156 / 52
- Edges added/removed: 49 / 3
- New cycles: 0
- New high-impact modules: 2
- New database tables: 4
- Changed-file scoped flow validation: 43 files, 0 errors, 0 warnings, 0 informational findings

## Qualification

The generic architecture refresh must be invoked with this repository's actual roots
(`agent-coordinator/src`, `agent-coordinator/database/migrations`, and `apps`); its bare defaults
target nonexistent generic paths and fail closed before promotion. With the configured roots,
all Python, PostgreSQL, SQL tree-sitter, compiler, enrichment, validation, parallel-zone, view,
and report stages passed. TypeScript analysis was skipped and the last known TypeScript artifact
was carried forward.

The baseline diff labels all five new HTTP routes as untested because this source-root refresh
does not ingest `agent-coordinator/tests` (`test_linker` discovered zero tests). That is a tool
coverage limitation, not accepted evidence of missing route tests: the affected coordinator
suite passed 2,562 tests with 11 skipped and 132 deselected, including direct auth and behavior
coverage for every routing path plus MCP parity.

## Structural Advisories

The structural linter reported eight medium file-size advisories. Seven files already exceeded
500 lines at the base revision. `watchdog.py` grew from 402 to 511 lines while adding the three
independently scheduled routing jobs; extracting those jobs is modularity follow-up, not a
correctness or dependency-direction blocker for dg-00.

## Recommendation

The architecture is safe for dg-00: no new cycle or broken scoped flow was found, the four-table
schema is visible in the graph, and the fallback boundary remains coordinator-to-static rather
than introducing a second routing core. Retain the test-linker and file-size limitations as
explicit advisories rather than interpreting the generated counts as behavioral failures.
