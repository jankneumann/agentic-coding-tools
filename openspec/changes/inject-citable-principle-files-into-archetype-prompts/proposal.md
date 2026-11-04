# Inject citable principle files into archetype prompts

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `inject-citable-principle-files-into-archetype-prompts`
> Effort: M
> Priority: 3

## Summary

Add docs/principles/<id>.md files, each with a when-it-applies trigger, a checkable bar and an optional registry rule link, seeded with test-behaviour-not-wiring, build-the-lever, attack-the-premise, fix-root-causes and subtract-before-you-add. Add a per-archetype principles list to archetypes.yaml that the resolver appends as compact pointer + bar at the same composition point as PROCEDURE_MODE_SENTENCES, and validate session-log principle citations.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- A test enforces that each principle file has its trigger, checkable bar and well-formed optional rule link, rejects one with no checkable bar, and rejects a rule link to an id not in docs/enforcement/rules.yaml.
- Resolving an archetype with a principles list yields a system prompt containing each principle's id and bar, and a size-budget test bounds the added text.
- A session-log decision citing a non-existent principle id fails validation.
- AGENTS.md indexes the principle files.

## Rationale

Gives agents a small, citable, checkable set of principles linked to registry rules from ri-05, without moving AGENTS.md's linked guides into principle files.
