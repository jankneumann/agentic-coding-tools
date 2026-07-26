# Design: Revision-Aware Architecture Refresh

## Context

Architecture refresh has producer-specific state (input fingerprint, optional analyzer
identity, owned artifacts) and shared workflow state (repository/revision operation,
locking, retries, producer results). ri-06 deliberately centralizes the latter in
`project-context-runtime`. This design keeps the boundary one-way:

```text
refresh-architecture -> project-context-runtime
project-context-runtime -X-> refresh-architecture
```

## Goals

- Prove which inputs and producer generated the architecture artifacts.
- Detect drift without writes or mtimes.
- Produce byte-identical outputs for identical identities.
- Publish one canonical architecture `ProducerResult` through ri-06.
- Preserve the subprocess RPC as an architecture-specific compatibility facade.

## Non-Goals

- Another operation store, lock, atomic record writer, or generic status type.
- Finalizing a multi-producer context refresh.
- Cross-clone durability, analyzer replacement, or main integration.

## Decisions

### D1 — Architecture-Specific Provenance Evidence

`docs/architecture-analysis/architecture.provenance.json` is owned by the architecture
producer. It records schema version, exact analyzed SHA, dirty state, producer version,
mode, input roots/fingerprint, deterministic timestamp, optional tool identity,
validation summary, and sorted owned-artifact digests.

The later project-context manifest remains owned by ri-06/ri-07. Its canonical
architecture `ProducerResult.artifacts` points at changed architecture files,
including the provenance document; it does not duplicate the architecture-specific
fingerprint fields.

### D2 — Content Identity, Not Git SHA Alone

The fingerprint hashes a canonical stream of relevant relative paths, modes, bytes,
missing-root markers, architecture configuration, and output-affecting optional-tool
identity. It excludes `.git`, architecture outputs, caches, dependency trees, and
transient state.

The analyzed SHA is immutable provenance, not a requirement that current `HEAD`
always equal it. An artifact-only convergence commit remains fresh when relevant input
and producer fingerprints agree. Relevant source/config changes alter the fingerprint.

### D3 — Deterministic Clock and Serialization

Committed architecture metadata uses `SOURCE_DATE_EPOCH`, otherwise the analyzed
commit timestamp, otherwise a fixed fixture epoch. Architecture JSON uses canonical
serialization and stable collection ordering. Wall-clock operation metadata belongs
only to `project-context-runtime`.

### D4 — Stage, Validate, Compare, Promote

Generation writes to a temporary sibling tree, validates required outputs/contracts,
constructs provenance from staged bytes, then promotes the owned set. The shared
runtime's atomic primitive is reused where applicable; architecture retains only
set-level staging/promotion logic.

`--check` recomputes identity and verifies the committed provenance/artifact digests
without invoking analyzers or writing repository/runtime state. It reports
`fresh|stale|invalid`, reason codes, and exact artifact paths.

### D5 — Reuse the Canonical Shared Operation

The adapter calls ri-06's supported facade with canonical `repository_id` and full
`source_revision`:

1. `create_or_load`;
2. `begin_attempt` only when the shared operation is pending or retryable;
3. run/check architecture;
4. `record_producer_result` with `producer_id=architecture`.

It reuses ri-06's per-operation lock, atomic persistence, schema validation,
`record_revision`, safe error shape, remediation, and retry transitions. No
architecture operation files, schemas, IDs, locks, PID records, or cleanup policy are
introduced.

Architecture does **not** call shared `finalize`. A standalone producer may leave the
overall operation running; ri-07 decides when all configured producers support a
terminal project-context outcome.

### D6 — Adapter-Specific Status Projection

The RPC facade derives architecture status from the canonical operation's
`producer_id=architecture` result:

| Shared evidence | Architecture RPC status |
|---|---|
| operation absent/corrupt | `UNKNOWN` or client unavailable |
| operation pending/running, architecture result absent | `RUNNING` |
| architecture result `fresh` | `COMPLETED` |
| architecture result `degraded` or `not-configured` | `FAILED` with remediation |
| architecture result `failed` | `FAILED` with safe error/remediation |

The facade returns the shared operation ID as `refresh_id`. Duplicate triggers reuse
the canonical revision operation; if a valid fresh architecture result and matching
provenance already exist, no pipeline process starts.

### D7 — Additive RPC Compatibility

`is_graph_stale(max_age_hours=...)` remains callable and returns legacy fields, but
freshness comes from architecture provenance. Responses add source SHA, producer
version, input fingerprint, provenance path, shared operation ID, and a reason.

`trigger_refresh(reason, caller)` keeps required inputs and may add repository/revision
arguments. `get_refresh_status` keeps legacy statuses while exposing canonical
producer remediation. `RefreshRpcClient` continues returning
`RefreshClientUnavailable` for transport/payload failures.

## Data Flow

```text
inputs + producer code
        |
 architecture identity/check
        |
 staged generation -> architecture.provenance.json
        |
 canonical ProducerResult(architecture)
        |
 project-context-runtime operation store
        |
 RPC architecture status projection
```

## Failure Handling

- Missing/malformed provenance: stale/invalid and full-suite fallback.
- Pipeline failure: preserve previous committed set; record canonical failed producer
  result with safe error and remediation.
- Shared runtime unavailable/corrupt: RPC fails safely; coordinator sentinel fallback.
- Duplicate producer trigger: reuse shared operation and valid producer evidence.
- Global operation outcome: never decided by the architecture adapter.

## Test Strategy

- Unit tests for architecture fingerprints, deterministic metadata, stable output, and
  mtime independence.
- Runner tests for check reasons and staged failure recovery.
- Adapter contract tests against ri-06 installed schemas/models.
- Separate-process RPC tests that observe the canonical architecture producer result.
- Coordinator regressions proving legacy response/sentinel behavior.

## Risks and Mitigations

- **Producer result replacement semantics:** adapter tests pin ri-06's supported
  `record_producer_result` retry behavior; no direct record edits.
- **Standalone run leaves global operation nonterminal:** intentional; the
  architecture-specific facade is terminal independently, and ri-07 owns finalization.
- **Cross-change contract drift:** ri-04 tests import installed ri-06 schemas/facade
  rather than copying them.
- **Input hashing cost:** stream only declared relevant roots and benchmark the largest
  supported fixture during implementation.
