# Define the decision-card schema and markdown renderer

> Parent roadmap: `operator-front-door`
> Change ID: `define-the-decision-card-schema-and-markdown-renderer`
> Effort: M
> Priority: 1

## Summary

A versioned JSON schema for decision cards (breadcrumb project > roadmap > item, since-last-seen summary, decision and evidence, 2-4 numbered options with a recommendation, default action, deadline) plus a deterministic markdown renderer and an option-token parser for answers such as 2 or 1a.

## Dependencies

- None

## Acceptance Outcomes

- The decision-card JSON schema carries a schema version and validates every card emitted in tests; a card missing a breadcrumb, since-last-seen summary, numbered options, recommendation, default, or deadline is rejected.
- Rendering the same card twice yields byte-identical markdown, and the rendered canonical merge and escalate-resume cards each fit within 1,200 characters.
- The token parser maps option tokens (2, 1a) to the matching option and returns an explicit no-match for tokens that name no option, covered by unit tests.
- A rendered card contains no repository-relative paths that require opening the repo to understand the decision (self-contained constraint), checked by a fixture test.

## Rationale

Cards are the unit the inbox stores, delivery pushes, the governor and ladder raise, and promotion learns from, so the schema must exist before any of them. Kept separate from gate tiering because it is independently shippable data plus a pure renderer, consumable by any surface (thread, PR comment, digest).
