# Shape skill-authored PRs for reviewers

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `reviewer-shaped-prs`
> Effort: M
> Priority: 4

## Summary

Lead PRs created by /autopilot and /cleanup-feature with a ledger (decisions where the spec was silent, contracts changed, concerns-as-tests added, evidence) generated from choices.json and contract diffs, and add a configurable size budget that splits work or pauses at a contract checkpoint for review by a non-running owner.

## Dependencies

- `ri-02`
- `ri-09`

## Acceptance Outcomes

- PRs created by /autopilot and /cleanup-feature render a ledger section generated from choices.json and contract diffs.
- A change exceeding the size budget pauses at a contract checkpoint requesting review from a non-running owner when one exists.
- In solo mode the checkpoint is skipped and only the ledger section is added.

## Rationale

Reviewer throughput is the team bottleneck and rationale artifacts go unread (P6, P8); placing the ledger before the diff and bounding PR size keeps review proportional to agent output.
