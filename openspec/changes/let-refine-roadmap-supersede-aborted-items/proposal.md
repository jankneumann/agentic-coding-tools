# Let refine-roadmap supersede aborted items

> Parent roadmap: `durable-execution`
> Change ID: `let-refine-roadmap-supersede-aborted-items`
> Effort: S
> Priority: 3

## Summary

Teach /refine-roadmap to recognize aborted items and changes from the canonical checkpoint and loop-state so it can supersede them without a manual checkpoint edit, while still refusing in-progress items that have not been aborted.

## Dependencies

- `ri-06`

## Acceptance Outcomes

- After an abort, /refine-roadmap supersedes the aborted item with no manual edit to checkpoint.json.
- /refine-roadmap still refuses to supersede an in-progress or parked (non-terminal) item and names the abort command in its refusal.

## Rationale

Closes the proposal's stated gap where /refine-roadmap correctly refuses to supersede in-progress items but nothing lets the operator stop and replace them.
