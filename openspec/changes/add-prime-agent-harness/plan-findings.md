# Plan Findings — add-prime-agent-harness

Findings recorded while addressing PR #360 review threads through
`/iterate-on-plan`. Threshold: medium. Findings at or above the threshold were
fixed in this iteration.

## Iteration 1 (2026-08-29, coordinated parallel review)

### Baseline

- `openspec validate add-prime-agent-harness --strict` passed, but
  `openspec status --change add-prime-agent-harness` reported the contracts and
  work-package artifacts as incomplete.
- Five parallel reviewers assessed completeness, consistency, feasibility and
  parallelizability, testability, and security.
- The PR had three unresolved review threads: missing execution contracts, a
  coordinator/provider credential conflation, and an incomplete cleanup contract.

### Findings

| # | Type | Criticality | Description | Proposed Fix | Disposition |
|---|------|-------------|-------------|--------------|-------------|
| F1 | completeness | **high** | The plan lacked the required `contracts/` boundary artifacts and `work-packages.yaml`, so cross-package vocabulary, ownership, and sequencing were implicit. | Add roster, CLI cleanup, provider-map, and OpenAPI contracts plus a validated package DAG with isolated scopes, locks, verification, and context-impact declarations. | **Fixed** |
| F2 | consistency/security | **high** | Task 2.7 treated `PRIME_API_KEY` as a setup-cloud coordinator key even though setup-cloud generically derives `prime_local_key` and exposes it as `COORDINATION_API_KEY`. This would conflate coordinator identity with the Prime Inference provider credential. | Make `PRIME_API_KEY` operator-supplied through `cli.api_key_env`; constrain setup-cloud work to regression tests for the generic `prime_local_key` / `--prime-local-key` / `cprime-agent` projection. Pin the separation in design, specs, roster, and tests. | **Fixed** |
| F3 | completeness/testability/security | **high** | The cleanup plan covered only part of the producer round trip and did not define the consumer lifecycle, failure semantics, secret environment, timeout, shell behavior, or concurrent-session safety. | Define an unconditional typed cleanup capability, lossless canonical parser plus HTTP/MCP projection, argv-only `shell=False` execution, bounded timeout, minimal environment, exactly-once terminal cleanup, fail-closed quorum behavior, and per-session/concurrency safeguards with explicit tests. | **Fixed** |
| F4 | parallelizability | **medium** | The proposal had more than five implementation tasks across several trees but no executable package DAG, leaving file ownership and convergence points ambiguous. | Decompose the implementation into ten dependency-ordered packages and validate parallel scopes and locks. | **Fixed** |

### Triage decisions

- Fixed all high- and medium-criticality findings in iteration 1.
- Kept P1-P9 as the empirical human checkpoint; P7 decides whether
  `prime-local` populates cleanup, not whether the generic capability exists.
- Kept the existing dispatch-config endpoint instead of adding a new API surface.
- No unresolved assumption requires a user decision before implementation.

### Parallelizability assessment

- Independent implementation packages: **5**
- Sequential dependency chains: **4**
- Maximum parallel width: **4**
- File or lock overlap conflicts between parallel packages: **none**
- Convergence: documentation/templates → integration → authorized live smoke

### Termination

All findings at or above the medium threshold are addressed. Strict OpenSpec,
work-package schema/DAG, scope/lock overlap, context-impact, JSON schema, and
OpenAPI YAML checks pass.
