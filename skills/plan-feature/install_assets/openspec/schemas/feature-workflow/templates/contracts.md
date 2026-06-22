# Contracts: <change-id>

## OpenAPI

<!-- Primary API contract. Validate with: openapi-generator validate -i contracts/openapi/v1.yaml -->

contracts/openapi/v1.yaml

## Generated Types

<!-- Language-specific types generated from the OpenAPI spec -->

- Python (Pydantic): contracts/generated/python/
- TypeScript: contracts/generated/typescript/

## SQL Schema

<!-- Database table definitions for new tables -->

contracts/sql/

## Event Schemas

<!-- JSON Schema files for async event payloads -->

contracts/events/

## Mocks

<!-- Prism mock server configuration -->

contracts/mocks/prism-config.yaml
