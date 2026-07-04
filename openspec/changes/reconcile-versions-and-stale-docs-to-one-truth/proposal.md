# Reconcile versions and stale docs to one truth

> Parent roadmap: `repo-improvement`
> Change ID: `reconcile-versions-and-stale-docs-to-one-truth`
> Effort: S
> Priority: 3

## Summary

Single-source the root VERSION into agent-coordinator, packages/gen-eval, skills, and apps/kanban-viz, tag v0.2.0 with a minimal tag-triggered release workflow, fix documented drift (coordinator CLAUDE.md checklist, README counts, verification_gateway, formal/ duplication), and make one canonical file the sole statement of the D4 memory tag schema.

## Dependencies

- None

## Acceptance Outcomes

- git tag is non-empty and a tag-triggered release workflow exists.
- One grep finds exactly one authoritative statement of the D4 memory tag schema.
- Component manifests and the /health report agree with the root VERSION file.

## Rationale

Version drift and docs-vs-reality drift undermine trust in automation (weakness W5); a single authoritative version and tag schema removes contradictory statements that mislead both humans and agents.
