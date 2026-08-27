# Contracts: introduce-fitness-function-gates

Contract sub-types evaluated for this change:

- **OpenAPI**: not applicable — no API endpoints are introduced or modified.
- **Database**: not applicable — no schema or migration changes.
- **Events**: not applicable — no event payloads introduced or modified.
- **Type generation**: not applicable — no generated model surface changes.

The coordination boundaries between work packages are configuration/schema shapes,
documented here as the canonical contract set:

| Contract | File | Producing package | Consuming packages |
|---|---|---|---|
| 8-value axis enum + copy-identity rule | `review-findings-axis.md` | wp-schema | wp-gates (linters emit axes), wp-integration |
| `gates.architecture` config shape | `architecture-gates-config.md` | wp-gates | wp-integration |
| Coverage baseline file shape | `coverage-baseline.schema.json` | wp-coverage | wp-integration |
| `DEGRADED` status vocabulary | `architecture-gates-config.md` (§ Statuses) | wp-gates | wp-coverage (job summary), wp-integration |

`work-packages.yaml` points `contracts.openapi.primary` at this README per house
convention for changes with no OpenAPI surface.
