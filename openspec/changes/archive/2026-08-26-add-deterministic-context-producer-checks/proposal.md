# Change: Add deterministic context producer checks

> Parent roadmap: `project-context-refresh-lifecycle`
> Roadmap item: `ri-05`
> Change ID: `add-deterministic-context-producer-checks`
> Approval: inherited from `$autopilot-roadmap project-context-refresh-lifecycle`

## Why

Project context is currently refreshed through unrelated commands with different
freshness rules. Decision indexes already have a deterministic regeneration gate,
workflow contracts have a check target, and OpenSpec/documentation have domain
owners, but there is no common producer registry that a later project-context
orchestrator can call.

The active `add-update-documentation-skill` proposal contains useful
marker-preserving inventory behavior, but it also proposes independent hook,
cleanup, and post-merge writers that conflict with the roadmap's shared
convergence lifecycle.

ri-06 establishes the machine-readable `ProducerResult` and durable refresh
record boundary. This change must consume that boundary rather than introduce a
second producer-result model.

## What Changes

- Add a deterministic-producer registry under `skills/project-context-refresh/`
  whose adapters return ri-06 `project-context-runtime` `ProducerResult` models.
- Implement documentation inventory generation/check mode using generated
  markers while preserving hand-authored prose.
- Adapt workflow contract/binding validation, decision-index regeneration, and
  OpenSpec projections without transferring canonical ownership.
- Represent generated or stale paths as canonical repository-artifact records,
  check outcomes as validation results, and failures/fallbacks through ri-06
  remediation/error/fallback types.
- Add precise drift reporting, source-bound invocation, stable producer
  identity/versioning, and byte-identical repeat-run tests.
- Fully supersede `add-update-documentation-skill`: retain its useful historical
  design, move producer behavior here, and neutralize its tasks, work packages,
  and hook/cleanup/post-merge spec delta.

## Scope

### In scope

- Stable producer registration and invocation for:
  `documentation.inventory`, `api.contracts`, `decisions.timeline`, and
  `openspec.projection`.
- Independent `generate` and side-effect-free `check` modes.
- Adapters that produce the ri-06 `ProducerResult` contract.
- Absorption and supersession of `add-update-documentation-skill`.

### Out of scope

- Architecture generation, owned by `refresh-architecture` and ri-04.
- Semantic indexing, owned by ri-01 through ri-03.
- Durable operation storage or aggregate manifest writing, owned by ri-06.
- CI and merge gates, owned by ri-10 and ri-11.
- Rewriting hand-authored documentation or OpenSpec requirements.

## Dependencies

- **ri-06 — `add-durable-context-refresh-records`**: required. This change
  imports its strict models and validates results against
  `context-refresh-types.schema.json#/$defs/ProducerResult`.
- ri-07 consumes the independently runnable producer registry.

The parent roadmap owns the corresponding `ri-05 -> ri-06` DAG edge.

## Approaches Considered

### Approach A — Shared adapter registry over ri-06 contracts (Recommended)

Keep producer invocation and ownership adapters in
`project-context-refresh`, but import ri-06 runtime models and emit its canonical
`ProducerResult` shape.

**Pros**

- One machine-readable producer-result contract across producer, operation, and
  manifest layers.
- Domain owners remain independently runnable.
- ri-07 can record results without translation or lossy field mapping.
- Durable storage stays out of producer adapters.

**Cons**

- Adds a roadmap dependency on ri-06.
- Check-mode drift must be expressed through canonical artifact, validation,
  remediation, and fallback fields rather than a bespoke `stale_artifacts` key.

**Effort:** M

### Approach B — Standalone producer protocol with a later translation layer

Define a smaller ri-05 result containing changed/stale lists and diagnostics,
then translate it into ri-06 records in the orchestrator.

**Pros**

- ri-05 could remain a dependency root.
- Producer adapters would initially have fewer fields.

**Cons**

- Creates two v1 result contracts with incompatible status and diagnostic
  semantics.
- Pushes mandatory validation and fallback logic into ri-07.
- Allows drift between direct and orchestrated producer execution.

**Effort:** M

### Approach C — Shell commands with unstructured exit codes

Register producer commands and let ri-07 parse stdout and exit status.

**Pros**

- Small implementation surface.
- Reuses existing commands directly.

**Cons**

- Cannot reliably report exact artifacts, validations, remediation, or safe
  errors.
- Makes deterministic ordering and cross-platform testing brittle.
- Violates the durable manifest contract.

**Effort:** S

## Selected Approach

Approach A is selected under the approved roadmap direction. ri-06 owns the
machine contract; ri-05 owns deterministic invocation and domain adapters.

## Result Semantics

The invocation boundary is:

```text
run_producer(
  producer_id,
  mode,
  repository,
  source_revision,
) -> project_context_runtime.ProducerResult
```

- The caller retains `mode`, repository, and exact revision in the operation
  request; the canonical result is the ri-06 `ProducerResult`.
- `artifacts` lists files written by `generate` or files that would change under
  `check`, with the expected digest.
- `validations` contains stable pass/fail/skipped checks. Drift is a failed
  validation, never a fresh claim.
- A check that detects repairable drift returns `degraded` with explicit
  remediation and a `custom` fallback explaining that no checkout write was
  performed.
- Rendering/parsing failures return `failed` with a bounded safe error and
  remediation.
- Optional unavailable producers return `not-configured` with remediation and a
  declared fallback.

## Acceptance Outcomes

- Every configured producer supports deterministic generation and a
  side-effect-free check that identifies exact affected paths without mtimes.
- Every adapter result validates directly against the installed ri-06
  `ProducerResult` contract without translation.
- Managed artifacts carry source revision, producer ID, and producer version;
  content outside managed documentation regions remains byte-identical.
- Documentation, API/bindings, decisions, and OpenSpec producers are
  independently runnable and identify their canonical owner.
- `add-update-documentation-skill` contains no executable tasks, packages, or
  lifecycle spec directing hooks, cleanup, post-merge commits, or independent
  implementation; its only remaining normative delta is a supersession guard.
- Two runs at the same revision and inputs produce byte-identical managed output.

## Risks

- Existing generators may embed wall-clock timestamps. Adapters must remove them
  or derive stable metadata from the source revision.
- OpenSpec canonical updates are sync-point mutations; this producer may only
  project and compare.
- Marker corruption could overwrite prose. Unbalanced or duplicate marker pairs
  fail closed without writing.
- ri-06 contract changes after dispatch require a contract revision and ri-05
  plan review before implementation continues.
