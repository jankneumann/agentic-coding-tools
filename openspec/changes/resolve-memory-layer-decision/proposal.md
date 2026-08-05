# Resolve memory-layer decision

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `resolve-memory-layer-decision`
> Effort: M
> Priority: 4

## Summary

Either wire procedural memory as the home for roadmap `learnings/<item>.md` content, queryable by the replanner and the supervisor's digest, or descope the empty `memory_working` and `memory_procedural` layers from schema, bridge surface, and docs — with no third state.

## Dependencies

- None

## Acceptance Outcomes

- Procedural memory has both a writer and a reader in the roadmap loop, or the unused layers are removed from schema, bridge surface, and docs.
- No documentation or schema references remain to a memory layer with neither writer nor reader, verified by grep.
- If wired, a roadmap run persists learnings content into procedural memory and the replanner query returns it in a test.

## Rationale

A three-layer cognitive architecture with two empty layers is documentation debt that misleads contributors and agents; the proposal requires an explicit decision either way.
