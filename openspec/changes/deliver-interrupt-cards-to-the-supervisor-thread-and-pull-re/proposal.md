# Deliver interrupt cards to the Supervisor thread and pull requests

> Parent roadmap: `operator-front-door`
> Change ID: `deliver-interrupt-cards-to-the-supervisor-thread-and-pull-re`
> Effort: M
> Priority: 1

## Summary

Continuous, unbatched delivery of interrupt cards from the inbox to the long-lived Supervisor thread in the Claude app and, for PR-scoped cards, as one PR comment; answers given by option token or free text are written back to the inbox and resume the raising worker, while batched cards appear on thread open or in the digest.

## Dependencies

- `ri-07`

## Acceptance Outcomes

- An interrupt card is visible in the Supervisor thread within one coordinator poll interval of being opened.
- An answer given as an option token (2, 1a) or as free text in the Supervisor thread is recorded against the right card, and the worker that raised it resumes using that answer.
- A PR-scoped card appears as exactly one PR comment ending with the attribution footer and is not re-posted on retry.
- Opening the Supervisor thread lists every open card across all projects, oldest deadline first, without the operator naming a project.
- The Supervisor session's configuration grants no write access to implementation source, and a delivery-channel fallback is named in the digest.

## Rationale

Realises the single conversational front door: the operator answers any decision from any device without reloading context. Follows the operator decisions for continuous interrupt delivery and Claude-app-plus-PR-only notifications; phone push stays deferred per Out of Scope, and the Supervisor stays read-and-adjudicate only.
