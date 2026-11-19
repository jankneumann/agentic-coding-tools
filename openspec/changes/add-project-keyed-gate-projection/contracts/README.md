# Contracts: add-project-keyed-gate-projection

The HTTP contract for this change is authored directly in the promoted
contract tree, because the coordinator's OpenAPI contract test reads only that
tree:

- `openspec/contracts/agent-coordinator/openapi/gates.yaml`: `POST /gates/projection`,
  `DELETE /gates/projection`, `GET /gates/pending`, `POST /gates/decide`.

No database contract file is added: the one table is defined by migration
`047_gate_projection.sql`. No event contract: the change emits no events.

The snapshot the collector sends is the request body of `POST /gates/projection`
in that file (`SnapshotGate`).
