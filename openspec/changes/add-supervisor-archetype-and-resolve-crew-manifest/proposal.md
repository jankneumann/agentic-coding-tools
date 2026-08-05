# Add supervisor archetype and resolve crew manifest

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `add-supervisor-archetype-and-resolve-crew-manifest`
> Effort: M
> Priority: 1

## Summary

Add a read-only, frontier-tier `supervisor` archetype to `agent-coordinator/archetypes.yaml` with a system prompt centered on decomposition, delegation, and gate adjudication, and either repurpose `agent-coordinator/teams.yaml` as a documented crew manifest (supervisor plus archetype roster and eligible vendors per role) or delete it.

## Dependencies

- None

## Acceptance Outcomes

- POST /archetypes/resolve_for_phase resolves the supervisor archetype with model tier frontier and write_capable false.
- The resolver rejects any configuration or request that marks the supervisor archetype write-capable.
- teams.yaml is either consumed by a documented reader or removed from the repository; no unwired team model remains.

## Rationale

The supervisor is a promoted role, not a new runtime; the archetype is the routing anchor every later supervise capability resolves against, and the vestigial teams.yaml must stop looking load-bearing.
