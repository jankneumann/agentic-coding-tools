# Publish the multiplayer collaboration principles guide

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `multiplayer-principles-guide`
> Effort: S
> Priority: 1

## Summary

Add docs/guides/multiplayer-collaboration.md stating principles P1-P10, the single-principal assumption table, and how each skill behaves in solo versus team mode, linked from AGENTS.md and docs/guides/documentation.md.

## Dependencies

- None

## Acceptance Outcomes

- docs/guides/multiplayer-collaboration.md exists and is linked from both AGENTS.md and docs/guides/documentation.md.
- Each of the ten principles names at least one capability or existing mechanism that implements it.
- The guide contains the single-principal assumption table and a per-skill solo-mode versus team-mode behavior section stating that solo mode adds no new prompts, gates, or PR checkpoints.

## Rationale

Every later capability cites a principle; the guide is the shared reference that makes the epic's intent legible to teammates and to agents, and it fixes the solo-versus-team vocabulary before code depends on it.
