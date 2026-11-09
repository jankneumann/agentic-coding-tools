# Architecture impact

## Scope

DG-05 adds one standard-library-only isolation contract and threads it through the
existing configuration, registry, adaptive-router, outage-fallback, and review
dispatcher boundaries. It does not add a deployment surface, database migration,
or frontend component.

## Validation evidence

- Validated branch: `openspec/pin-isolation-contract`
- Validated implementation/review commit: `741f9ff2`
- Comparison base: `09cc9216`
- The architecture refresh pipeline completed with the repository's Python source,
  application, and migration directories supplied explicitly. The optional
  TypeScript analyzer was unavailable; DG-05 changes no TypeScript source.
- Scoped flow validation over the changed-file set reported 0 findings.
- The baseline architecture diff reported 285 added and 52 removed nodes, 123 added
  and 3 removed edges, one newly reported dependency cycle, four high-impact nodes,
  eight untested routes, and six database tables. Those repository-wide deltas
  include the adaptive-router base branch and stale generated architecture state;
  they are not a DG-05-only change count.
- The reported cycle (`agents_config -> agents_config -> model_routing.api ->
  vendor_registry`) follows imports already present in the adaptive-router surface.
  DG-05 adds the leaf `isolation_contract` dependency and does not introduce that
  mutual topology.
- The shared `isolation_contract` module appearing as a high-impact node is expected:
  it is intentionally the single vocabulary/validation seam used by live routing and
  outage fallback.
- Structural linters reported ten advisory file-size findings in existing routing,
  fallback, dispatcher, and test modules. They reported no blocking dependency or
  scoped-flow violation.

## Disposition

Architecture mode for this change is advisory. No blocking DG-05 architecture
finding was identified. The generated repository-wide architecture refresh was used
as validation evidence only and was not committed, avoiding unrelated documentation
churn in this work package.
