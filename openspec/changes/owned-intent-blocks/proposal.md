# Add owned intent blocks with single-writer change control

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `owned-intent-blocks`
> Effort: M
> Priority: 3

## Summary

Give each proposal a structured intent block (goals, non-goals, constraints, done-means) with a declared owner, add a CI check that rejects non-owner edits lacking an accepted amendment, and have agents raise a principal-conflict escalation when they detect conflicting intents.

## Dependencies

- `ri-02`
- `ri-09`

## Acceptance Outcomes

- openspec validate accepts a proposal intent block whose owner resolves in the ownership map and rejects one whose owner does not.
- A PR that edits another owner's intent block without an accepted amendment fails the intent-ownership check.
- An agent encountering two principals' conflicting intents emits a conflict escalation naming both owners and makes no choice between them.
- Proposals without an intent block, and repositories without owners.yaml, validate and merge exactly as before.

## Rationale

Intent is a single-writer artifact (P3) and agents must never arbitrate between principals' intents; this turns the 'whose spec wins' argument into an owner decision.
