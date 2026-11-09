# Contracts: generate-coordinator-clients-from-contracts

Sub-types evaluated for this change:

| Sub-type | Applies | Artifact |
|---|---|---|
| OpenAPI | yes: typed revision of the promoted feature-registry contract (5 operations, no new endpoints) | `contracts/openapi/v1.yaml` → promoted to `openspec/contracts/agent-coordinator/openapi/features.yaml` |
| Database | no: no schema or migration changes | none |
| Event | no: no events added or changed | none |
| Generated types | yes: real `datamodel-codegen` 0.83.0 output from `v1.yaml` (stdlib `TypedDict`) | `contracts/generated/models.py` |
| Breaking-change acknowledgement | yes: acknowledges the typing edit to `features.yaml` | `contracts/accepted-breaking-changes.yaml` (task 2.2) |

## Deviations from the plan template

- **Error responses are not RFC 7807.** The app raises `HTTPException`, which FastAPI renders as
  `{"detail": ...}`. The contract describes that shape so the conformance test (design D5) checks
  reality. Moving to `application/problem+json` would be a runtime change across all routes and
  is out of scope.
- **No `types.ts`.** There is no TypeScript consumer of this domain.

## Regenerate the stub

```bash
uvx --from datamodel-code-generator==0.83.0 datamodel-codegen \
  --input openspec/changes/generate-coordinator-clients-from-contracts/contracts/openapi/v1.yaml \
  --input-file-type openapi --output-model-type typing.TypedDict \
  --target-python-version 3.11 --disable-timestamp --formatters black isort \
  --use-schema-description \
  --output openspec/changes/generate-coordinator-clients-from-contracts/contracts/generated/models.py
```

## Validate

```bash
uvx --from openapi-spec-validator openapi-spec-validator \
  openspec/changes/generate-coordinator-clients-from-contracts/contracts/openapi/v1.yaml
python3 -I openspec/changes/generate-coordinator-clients-from-contracts/contracts/generated/models.py
```

Both pass as of plan time (2026-10-08). `openapi-spec-validator` is not a dependency of either
venv, so it runs through `uvx`.
