# Round 4 implementation-review dispositions

Quorum was met with valid structured findings from Claude Code, Codex, and Grok
(3/3 requested). Antigravity failed before review because its configured
`--json-schema` argument lacked JSON output mode. Pi completed analysis but its
adapter emitted protocol NDJSON and wrote a findings file instead of returning
the required JSON document; that output is preserved as out-of-band evidence and
does not count toward quorum.

## Fixed

- Consensus 1, 5, 7, and 10: every ESCALATE transition now uses the canonical
  writer, records resume metadata, advances the generation once, persists and
  projects goal-gate/apply-outcome failures, and treats a structured degraded
  projection as non-authoritative success (`e7558c4e`).
- Consensus 3 and 4: migration 038 moves exact projection-label repair into the
  per-change database transaction; implicit issue reads exclude cancelled rows,
  and concurrent-generation/live migration regressions guard the board contract
  (`83a2dad8`).
- Consensus 8: the OpenAPI request schemas now match runtime extra-field,
  non-empty string, priority, UUID, label, and typed-problem constraints
  (`e7558c4e`, `83a2dad8`).
- Consensus 2, 6, and 9: the recovery validation adds the missing live
  PostgreSQL/host evidence and successive-generation coverage; results are
  recorded in change-context and the validation handoff.
- Harness finding: Antigravity now pairs `--json-schema` with
  `--output-format json`; vendor health tolerates `sdk: null` (`e7558c4e`).

## Accepted advisory observations

- Consensus 11 is a bounded redundant snapshot query under backpressure, not a
  correctness failure. The fresh second snapshot is intentional and no latency
  budget was violated in validation.
- Consensus 12 correctly notes that the isolation contract is jointly guarded
  by the AST import test and transport spies; the test names are retained because
  the combined suite, rather than either test alone, proves D10.
- Consensus 13 records reviewer-environment limitations and positive static
  checks; local recovery validation executes the affected suites.
- Consensus 14–20 are positive verification observations and require no change.

The post-fix implementation is reviewed again in round 5 at an exact commit.
