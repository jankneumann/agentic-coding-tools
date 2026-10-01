# Contracts: split-no-evidence-retention-reason

| Sub-type | File | Status |
|---|---|---|
| OpenAPI | `openapi/v1.3.yaml` | Self-contained overlay of v1.2 (`retain-static-model-until-routing-evidence`). Adds `no-evidenced-challenger` to the `Retention.reason` enum and to the "kept reasons ⇒ `retained: true`" conditional. The set allowed to have `selected: null` is unchanged (design D3). |
| Events / persistence | `events/routing-decision-record.schema.json` | v1.2 decision record with the same two additions. |
| Generated types | `generated/models.py` | v1.2 models; `RetentionReason` adds the new value. |
| Database | none | Migration 044 has no CHECK on `retention->>'reason'`, so a new value needs no schema change (design D5). |

Each file differs from its v1.2 counterpart only by the lines listed above, plus the
version and description header. Tests locate these files with `change_dir()`. The archived
v1.2 contract is not edited (D7 of `retain-static-model-until-routing-evidence`).
