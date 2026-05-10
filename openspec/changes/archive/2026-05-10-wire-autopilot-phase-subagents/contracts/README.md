# Contracts — wire-autopilot-phase-subagents

Three contract sub-types apply to this change. Each is the coordination
boundary between parallel work-package agents.

| Sub-type | File | Owner package | Consumed by |
|---|---|---|---|
| Database | `db/0NN_add_phase_archetype.sql` | `wp-contracts` | `wp-coordinator-status-discovery` |
| Event | `events/status-report.schema.json` | `wp-contracts` | `wp-skills-autopilot`, `wp-coordinator-status-discovery` |
| OpenAPI | `openapi/discovery-agents.yaml` | `wp-contracts` | `wp-coordinator-status-discovery`, `wp-integration` (round-trip test) |

## Sub-types evaluated

- **OpenAPI** — applies (`GET /discovery/agents` response field added).
- **Database** — applies (one new TEXT column).
- **Event** — applies (`POST /status/report` payload schema extended).
- **Type generation stubs** — not applicable: there are no Python or
  TypeScript clients in this repo that consume the discovery API via
  generated types. Contracts are validated by hand-written tests in
  `wp-integration` instead.

The migration filename uses `0NN` as a placeholder; the implementer in
`wp-coordinator-status-discovery` SHALL replace `0NN` with the next
unused sequence number under `agent-coordinator/database/migrations/`.
