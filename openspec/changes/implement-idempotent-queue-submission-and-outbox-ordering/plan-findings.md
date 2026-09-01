# Plan Findings — Iteration 1

| # | Type | Criticality | Finding | Resolution |
|---|---|---|---|---|
| 1 | correctness | high | Integer casts in the partial expression index could fail on fractional or huge legacy values, and the conflict arbiter was implicit. | Replaced the cast with text expressions; published the exact predicate, `ON CONFLICT` target, canonical lookup, bounds, and malformed/concurrency tests. |
| 2 | correctness | high | Reconcile could race a different keyed submit and leave two active tuples. | Keyed submit and reconcile now share a transaction advisory lock derived from `change_id`; real PostgreSQL different-tuple races are required. |
| 3 | contract_mismatch | high | Identity could arrive from both top-level fields and arbitrary `input_data`. | One explicit `projection_key` is authoritative; all reserved identity keys in `input_data` are rejected. |
| 4 | correctness | high | The plan mixed phase-local `iteration` and monotonic `total_iterations`. | Renamed identity to `transition_sequence` and defined it exclusively as bounded `LoopState.total_iterations`, including revisit tests. |
| 5 | spec_gap | high | Reconciliation did not define a terminal row at the current key. | Completed, failed, and cancelled current rows are already-satisfied canonical generations and are never replaced. |
| 6 | contract_mismatch | high | OpenAPI required UUID/booleans even for denied failures with null task IDs. | HTTP uses success-only `ProjectionMutationSuccess` and 4xx RFC 7807 Problems; MCP/CLI failures use discriminated failure envelopes. |
| 7 | spec_gap | high | Direct MCP and CLI mappings/tests were omitted and the base submit scenario implied every call inserts. | Added direct/proxy MCP and CLI tasks, scopes, tests, transport-parity scenarios, and modified ordinary-submit semantics. |
| 8 | resilience | medium | Migration preflight, remediation, rollback/retry, and lock strategy were incomplete. | Added short table-lock preflight, deterministic SQLSTATE/evidence, atomic rollback, remediation, unchanged retry, and seeded tests. |
| 9 | security | medium | Boundary validation did not cover bounds, enum, bool-as-int, partial keys, or reserved embedded fields. | Contract and scenarios now define strict change/phase/sequence validation and 422 rules for submit and reconcile. |
| 10 | testability | medium | Contract gate only parsed YAML and package gates omitted API and real PostgreSQL concurrency suites. | Gates now run semantic OpenAPI validation plus coordinator HTTP/MCP/CLI and real PostgreSQL migration/concurrency suites. |

All seven high and three medium findings are resolved in plan revision 2. No threshold-level findings remain.
