# Define memory actions and placement policy in the documentation guide

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `define-memory-actions-and-placement-policy`
> Effort: M
> Priority: 2

## Summary

Add a section to docs/guides/documentation.md defining the five memory actions (add, rewrite, remove, extract, move) with their evidence floors and mechanical checks, and a single what-goes-where placement policy that merges the keep/cut test, the broad/narrow/trigger table, and the progressive-disclosure tiers with measured relevance as the criterion. Reference the section from the skill-workflow spec.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- docs/guides/documentation.md contains a table with exactly five actions, each row naming its evidence floor (2 distinct sessions with quotes; 2 sessions with harm for remove; exempt for extract and move) and its mechanical check.
- The same guide contains a placement section mapping broad (20 percent of sessions or safety) to AGENTS.md, narrow-with-trigger to a skill, and narrow-without-trigger to deletion, and states the corroboration unit chosen for this corpus (distinct changes or distinct interactive sessions).
- openspec/specs/skill-workflow/spec.md references the memory-actions section by path and no longer carries its own contradictory keep/cut wording.
- The extract action text states that every removed line must reappear in the created or extended SKILL.md and that the description delta is charged to the always-loaded budget.

## Rationale

Sections 3.4 and 4 (adapt item 3). No action vocabulary exists in the repo today; the keep/cut/relocate heuristic lives only in prose. The definitions are the contract that the Phase 4 proposal-commit format and the skill-rightsizing ri-14 (cut-competence-rules-relocate-policy) and ri-15 extract work will be judged against: relevance prioritizes a cut, the replay benchmark accepts it.
