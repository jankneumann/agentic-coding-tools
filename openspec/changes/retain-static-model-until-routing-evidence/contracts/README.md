# Contracts: retain-static-model-until-routing-evidence

| Sub-type | File | Status |
|---|---|---|
| OpenAPI | `openapi/v1.2.yaml` | Self-contained overlay of v1.1 (`implement-the-task-router-vendor-x-location-x-model`). Adds optional request `incumbent`, optional response `retention`, and a nullable `selected` (only with a retained, catalog-less incumbent). |
| Events / persistence | `events/routing-decision-record.schema.json` | v1.1 decision record plus `retention`, nullable `selected`, and `incumbent` in the persisted request. |
| Generated types | `generated/models.py` | `Incumbent`, `Retention`, `RetentionReason` only (additive). |
| Database | none | `routing_decisions` stores the record as JSON; no column or migration change. |

Tests locate these files with `change_dir()` (design D7). The archived `add-adaptive-model-router`
contract is not edited.
