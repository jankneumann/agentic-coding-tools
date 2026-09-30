Review the OpenSpec plan artifacts in openspec/changes/standardize-port-leases/.

Read proposal.md, design.md, tasks.md, work-packages.yaml, all specs/*/spec.md, and everything
under contracts/ (openapi/v1.yaml, db/schema.sql, schemas/port-lease-env.schema.json).

This plan allocates blocks of 5 host ports to concurrent agent sessions, via a coordinator
backend (Postgres-backed ledger) or a file-registry fallback, so that parallel validate-feature
runs on one host never collide.

A prior iteration already fixed these — do NOT re-report them, but DO report anything they miss
or any contradiction they introduced:
- lease ownership check on release/conflict (not_lease_owner)
- reconcile scoped by host_id
- backends allocate from disjoint slot ranges (PORT_ALLOC_FILE_SLOT_BASE)
- release keyed on session_id not agent_id
- port pattern bounded to 1024-65535
- kanban e2e uses the compose-published REST port; validate-feature deploy uses API_PORT
- blocked-slot cooling period expiry and startup prune
- allocation atomicity across worker processes
- reconcile requires slot or db_port

Focus on: specification completeness, contract consistency across the three contract files and
the four spec deltas, architecture alignment, security, and work-package validity.

Output ONLY valid JSON conforming to review-findings.schema.json.
