# Change Context: restructure-openbao-per-agent-secrets

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| agent-coordinator.1 | `specs/agent-coordinator/spec.md` | Atomic API-Key Identity Reload | `contracts/openapi/v1.yaml`, `contracts/openbao-event.schema.json` | D4 | --- | tasks.md §§3.1–3.6, 5.4 | --- |
| agent-coordinator.2 | `specs/agent-coordinator/spec.md` | Bounded Identity Reload Degradation | `contracts/openapi/v1.yaml`, `contracts/openbao-event.schema.json` | D4 | --- | tasks.md §§3.1–3.6, 5.4 | --- |
| agent-coordinator.3 | `specs/agent-coordinator/spec.md` | Credential Failure Audit and Readiness Contract | `contracts/openapi/v1.yaml`, `contracts/openbao-event.schema.json` | D4 | --- | tasks.md §§3.1–3.6, 5.4 | --- |
| agent-identity.1 | `specs/agent-identity/spec.md` | OpenBao Service Principals | `contracts/principal-topology.schema.json`, `contracts/openapi/v1.yaml` | D1, D3 | --- | tasks.md §§1.1–1.2, 2.1–2.4, 5.2 | --- |
| agent-identity.2 | `specs/agent-identity/spec.md` | Dispatch Principal Wire Contract | `contracts/principal-topology.schema.json`, `contracts/openapi/v1.yaml` | D1, D2 | --- | tasks.md §§1.1–1.2, 2.1–2.4, 5.2 | --- |
| agent-identity.3 | `specs/agent-identity/spec.md` | Declarative Agent Configuration | `contracts/principal-topology.schema.json`, `contracts/openapi/v1.yaml` | D1 | --- | tasks.md §§1.1–1.2, 2.1–2.4, 5.2 | --- |
| agent-identity.4 | `specs/agent-identity/spec.md` | API Key Identity Generation | `contracts/principal-topology.schema.json`, `contracts/openapi/v1.yaml` | D4 | --- | tasks.md §§1.1–1.2, 2.1–2.4, 5.2 | --- |
| agent-identity.5 | `specs/agent-identity/spec.md` | OpenBao AppRole per Agent | `contracts/principal-topology.schema.json`, `contracts/openapi/v1.yaml` | D1, D3 | --- | tasks.md §§1.1–1.2, 2.1–2.4, 5.2 | --- |
| agent-identity.6 | `specs/agent-identity/spec.md` | Registry Projection Invariant | `contracts/principal-topology.schema.json`, `contracts/openapi/v1.yaml` | D1 | --- | tasks.md §§1.1–1.2, 2.1–2.4, 5.2 | --- |
| agent-identity.7 | `specs/agent-identity/spec.md` | Harness Key Coverage | `contracts/principal-topology.schema.json`, `contracts/openapi/v1.yaml` | D1 | --- | tasks.md §§1.1–1.2, 2.1–2.4, 5.2 | --- |
| configuration.1 | `specs/configuration/spec.md` | OpenBao Migration and Rollback | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D3 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.2 | `specs/configuration/spec.md` | Coordinator-Internal Bao Compatibility | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D5 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.3 | `specs/configuration/spec.md` | Internal and Bootstrap Compatibility Scenarios | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D5 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.4 | `specs/configuration/spec.md` | Principal OpenBao Configuration | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D1 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.5 | `specs/configuration/spec.md` | Live OpenBao Conformance Matrix | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D1 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.6 | `specs/configuration/spec.md` | Dispatch Tier Credential Boundary | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D2 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.7 | `specs/configuration/spec.md` | Secret Interpolation | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D5 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.8 | `specs/configuration/spec.md` | OpenBao Secret Backend | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D2 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.9 | `specs/configuration/spec.md` | OpenBao Configuration Dataclass | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D5 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |
| configuration.10 | `specs/configuration/spec.md` | Bootstrap Seeding Script | `contracts/bootstrap-bundle.schema.json`, `contracts/session-cache.schema.json`, `contracts/migration-map.schema.json` | D3 | --- | tasks.md §§1.3–1.4, 2.1–2.4, 3.7–3.8, 4.1–4.2, 5.3 | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | One deterministic topology projection | --- | See `design.md` |
| D2 | Typed adapter boundary | --- | See `design.md` |
| D3 | Provisioning, wrapping, and reconciliation | --- | See `design.md` |
| D4 | Atomic identity snapshot and bounded degradation | --- | See `design.md` |
| D5 | Keep coordinator-internal secrets separate | --- | See `design.md` |
| D6 | Verification and migration order | --- | See `design.md` |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 0/20
- **Tests mapped**: 20 requirements have planned tests
- **Evidence collected**: 0/20 requirements have pass/fail evidence
- **Gaps identified**: pending implementation
- **Deferred items**: ---
