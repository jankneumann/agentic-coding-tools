# Design: Deterministic context producer checks

## Context

The repository already has useful generators, but their interfaces and ownership
are inconsistent. `make decisions` is close to the desired model,
`workflow-contracts-check` validates a narrower surface, and `update-specs` is a
main-touching workflow rather than a pure projection.

ri-06 supplies strict `project-context-runtime` models and JSON Schemas for
producer results, operation records, and deterministic manifests. This change is
an adapter/registry layer over those models, not a competing persistence or
result-model owner.

## Decisions

### D1 — Stable registry with domain-owned implementations

The shared layer defines registration, invocation, validation, and result
ordering. Domain owners retain parsing and rendering. Adapters call Python entry
points directly where available and subprocess commands only for stable existing
command boundaries.

Stable v1 producer IDs are:

- `documentation.inventory`
- `api.contracts`
- `decisions.timeline`
- `openspec.projection`

Registry metadata includes canonical owner, declared inputs, managed outputs,
optional/configured policy, and producer version. It does not duplicate result
classes from `project-context-runtime`.

### D2 — ri-06 owns ProducerResult

Every adapter returns the strict model corresponding to:

`context-refresh-types.schema.json#/$defs/ProducerResult`.

Mappings are:

| Producer observation | Canonical ri-06 representation |
|---|---|
| generated path | `artifacts[]` with change kind and resulting digest |
| path that would change in check mode | `artifacts[]` with expected change/digest |
| clean check | `status=fresh` plus passed validation |
| drift found without writing | `status=degraded`, failed validation, remediation, `fallback.kind=custom` |
| render/parse exception | `status=failed`, failed validation, safe error, remediation |
| optional producer unavailable | `status=not-configured`, skipped validation, remediation, fallback |

The invocation request retains repository, exact source revision, and mode. ri-06
operation records retain that request identity, so those fields are not added to
`ProducerResult`.

### D3 — Generate and check are separate modes

`generate` may update only a producer's declared managed outputs. `check` renders
to memory or a temporary directory and compares bytes. It leaves tracked and
untracked checkout state unchanged.

No producer uses mtimes. Inputs are Git paths plus explicit generator
configuration. ri-06 owns aggregate operation identity; each producer still uses
the exact request revision when rendering and writes source-bound metadata inside
managed output regions.

### D4 — Stable repository metadata

Managed artifacts expose `source_revision`, `producer_id`, and
`producer_version`. Metadata derives from invocation inputs and code version,
never wall-clock time. Human-authored files keep metadata and generated content
inside declared marker regions.

Artifact and validation ordering follows the ri-06 model/manifest contract.

### D5 — Documentation proposal is absorbed, not composed

This change adopts the generated-marker engine, filesystem inventory, cross-link
checks, and prose-preservation behavior from
`add-update-documentation-skill`.

It rejects the old proposal's pre-commit, post-merge, cleanup-feature,
validate-feature, and auto-commit wiring. ri-10 owns deterministic gates and
ri-11 owns merge convergence. The old change is neutralized across its proposal,
design, tasks, work packages, and spec delta so no workflow can dispatch it
independently.

### D6 — OpenSpec check is a projection

The OpenSpec adapter reuses `update-specs` delta parsing and merge rules against
a temporary copy. It reports expected canonical capability artifacts through
ri-06 repository-artifact records. It does not archive a change, mutate canonical
specs, bypass active-agent checks, or replace cleanup-feature ownership.

## Failure Behavior

- Unknown producer IDs, invalid revisions, paths outside the repository,
  duplicate managed outputs, and schema-invalid results fail before publication.
- Adapter exceptions become bounded `SafeError` values; raw subprocess output,
  environment values, tracebacks, and absolute machine paths are not persisted.
- Unbalanced documentation markers fail closed and preserve the original file.
- A configured required producer cannot return `not-configured`; registry policy
  validation turns that into `failed`.
- One producer failure does not invoke other producers in this change; ri-07 owns
  orchestration and degradation across producers.

## Test Strategy

- Contract tests validate every adapter result against the installed ri-06
  Draft 2020-12 schema and strict Python model.
- Each adapter uses a fixture repository and asserts checkout state before and
  after check mode.
- Golden tests prove byte stability and prose preservation.
- Integration tests run all four producers without network services.
- Supersession tests prove the old proposal has no unchecked tasks, executable
  package, or normative lifecycle delta.
