# Land verified stack prefixes via Gate.MERGE

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `land-verified-stack-prefixes-via-gate-merge`
> Effort: M
> Priority: 2

## Summary

For stacked PRs, merge only the contiguous prefix of nodes that carry a valid SHA-bound verdict, and pass the bound verdict into autopilot's Gate.MERGE evidence so /cleanup-feature can confirm it merges the head that was verified.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- Given a stack whose third node lacks a valid verdict, the merge plan lands only the first two nodes and reports the third as blocked with its reason.
- Autopilot's Gate.MERGE evidence records the verified head SHA and patch-id, and /cleanup-feature refuses to merge when the live head's patch-id differs.
- Autopilot never merges on its own; the human merge gate is unchanged, and autopilot and cleanup SKILL.md edits are line-neutral or go into references/.

## Rationale

Completes the merge-verdict capability on top of ri-01's bound verdicts: without prefix landing a stack can merge past an unverified node, and without Gate.MERGE evidence the cleanup step cannot prove it merged the verified head.
