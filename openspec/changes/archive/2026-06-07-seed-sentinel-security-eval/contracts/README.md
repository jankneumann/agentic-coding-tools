# Contracts — Seed Sentinel Security-Evaluation Capability

This is a **seed-only spec change**: it authors governance + specification artifacts and
introduces no runnable interfaces. The contract sub-types were evaluated as follows.

| Sub-type | Applicable? | Why |
|---|---|---|
| OpenAPI | No | The seed adds no API endpoints. Sentinel reuses `agent-coordinator`'s existing MCP/HTTP surfaces; concrete eval endpoints are authored in roadmap implementation changes. |
| Database | No | No schema in the seed. The finding store / coverage checklist schemas are authored when their roles are implemented (roadmap). |
| Events | No | No new events in the seed. |
| Type stubs | No | Nothing to generate without OpenAPI/DB contracts. |

**No contracts applicable for this change.** When `/plan-roadmap` decomposes the seed,
each role-implementation change introduces its own contracts (e.g., a finding-store DB
contract for the Detector/Triager, OpenAPI for the Reporter's publish surface).
