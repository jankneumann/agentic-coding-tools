# Schedule the learning flywheel pipeline

> Parent roadmap: `closed-loop-learning`
> Change ID: `schedule-the-learning-flywheel-pipeline`
> Effort: M
> Priority: 1

## Summary

Turn the existing collect-transcripts -> episodic memory -> improve-harness -> proposal-stub pipeline into a recurring scheduled job (coordinator cron or harness scheduled task behind the adapter seam) that runs transcript collection and gap analysis weekly, files coordinator issues for capability gaps above a frequency x severity threshold, and feeds candidate proposals into /prioritize-proposals.

## Dependencies

- None

## Acceptance Outcomes

- A scheduled job runs the transcript-collection and gap-analysis pipeline at least weekly with zero human invocation, and each run appears in the audit log.
- Capability gaps above the configured frequency x severity threshold automatically produce a coordinator issue carrying the memory-conventions tag set.
- Improve-harness-generated candidates appear in the /prioritize-proposals queue alongside feature work.
- The repo-improvement roadmap marks ri-12 as delivered by this item, with no duplicate implementation.

## Rationale

The learning pipeline is built but hand-cranked; nothing schedules it, so capability-gap signal accumulates unread. This delivers repo-improvement ri-12, unblocks its ri-13 consumers, and is sequenced first because every other capability in this epic consumes the signal it produces.
