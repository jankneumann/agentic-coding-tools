# Deliver memory-file proposals as one commit per edit with proposal.json

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `deliver-memory-edits-as-commits-with-proposal-json`
> Effort: L
> Priority: 4

## Summary

Build the proposal writer: edits are made on a staging copy, the diff is measured from the file and never taken from a model reply, each edit becomes one commit on a proposal branch with the action kind, instruction ids, and verbatim quotes in the commit body, and a proposal.json records edit keys for the rejection ledger. Enforce in code the per-action evidence floors, the max-edits-per-run cap, and the post-edit budget check, failing loudly after two re-prompts.

## Dependencies

- `ri-01`
- `ri-03`
- `ri-09`
- `ri-13`

## Acceptance Outcomes

- A run producing three edits yields a branch with exactly three commits, each body containing action kind, instruction ids, and quotes from at least two distinct qualifying sessions, plus a proposal.json listing three edit keys.
- An add edit that pushes the always-loaded surface over budget is rejected in code and the run fails after at most two re-prompts with the rejected proposal preserved on disk.
- A remove edit backed only by non-compliance evidence is rejected; an extract edit whose removed lines do not all reappear in the target SKILL.md is rejected (asserted by tests).
- Reverting one commit and rerunning records that edit key in the rejection ledger and does not re-propose it.

## Rationale

Sections 3.4 and 4 (adopt items 4, 8, 9; adapt item 4). PR review is the human gate this repo already uses; one commit per edit gives it backpass's per-edit accept/reject without a new UI, and reverting a commit is the rejection the ledger records. Rules enforced in code, briefed in prose.
