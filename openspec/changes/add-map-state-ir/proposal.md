# Agent-activity map-state IR (schema + coordinator projection)

> Parent roadmap: `codeviz`
> Change ID: `add-map-state-ir`
> Effort: M
> Priority: 3

## Summary

Operationalize the draft contract at openspec/schemas/map-state.schema.json: a typed IR describing live agent activity across the work hierarchy (roadmap items, changes, work packages, agents, worktrees, paths) with mandatory provenance on every node and edge. Ship a coordinator projection endpoint (GET /map/state) that materializes the currently-missing agent-to-file join from work_queue, agent_sessions, file_locks, the worktree registry, scope globs in work-packages.yaml, and scope_checker output; reconcile the three agent-identity forms (registry agent_id, agent_sessions.id, the <package>--<vendor> suffix convention) into one agent node; derive the five-state agent activity (working/waiting/idle/stale/disconnected) the raw active/idle/disconnected enum cannot express; and ship a snapshot writer that persists frozen map-state documents as event artifacts for delta review at sync points.

## Dependencies

- `artifact-header-schema`

## Acceptance Outcomes

- GET /map/state on the coordinator MUST return a document that validates against openspec/schemas/map-state.schema.json, covering all active changes.
- Every emitted node and edge MUST carry at least one provenance entry naming its source store and a human-followable evidence pointer; the endpoint MUST NOT emit edges lacking provenance.
- Agent nodes MUST reconcile registry agent_id, agent_sessions.id, and the <package>--<vendor> naming convention into a single node with an identities block; a fixture test MUST cover an agent visible under all three forms.
- Derived agent activity MUST be one of working/waiting/idle/stale/disconnected, computed from heartbeat freshness, active claims, and needs_human status reports; the derivation rule MUST be documented in docs/codeviz/map-state.md and recorded as a derived provenance entry.
- Intent-versus-reality MUST be expressible; scoped_to edges from work-packages.yaml scope globs and touched edges from scope_checker output, with out_of_scope flagged on touches outside the owning package's write_allow.
- A snapshot writer MUST persist frozen map-state documents as event artifacts under docs/codeviz/map-state/<YYYY-MM-DD>/<run-id>.json carrying the mandatory artifact header.
- A validation helper under skills/shared MUST validate documents against the schema and MUST be covered by fixture tests for both valid and invalid (provenance-less) documents.

## Rationale

Every observability surface (kanban board, CLI, future map lens) currently reimplements ad-hoc joins over coordinator endpoints, and no store correlates agents with the files they touch. A schema-validated, server-owned projection gives all consumers one contract, makes agent-identity reconciliation testable, and is the prerequisite for the agent-activity map lens.
