# Stamp and check team toolkit consistency

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `toolkit-consistency`
> Effort: M
> Priority: 5

## Summary

Have install.sh stamp the installed toolkit version and payload hash into a tracked file in the consumer repository, add install.sh --check to report drift between the pinned version and local runtime copies, and support opt-in repository-scoped shared learnings.

## Dependencies

- None

## Acceptance Outcomes

- A consumer repository records the installed toolkit version and payload hash in a tracked file registered in docs/guides/state-artifacts.md.
- install.sh --check reports drift between the pinned version and the local runtime copy.
- Repository-scoped learnings are opt-in and never include private transcript content.
- Installed payloads contain no references to private coordinator source.

## Rationale

Installed skill versions drifting between developers makes team behavior inconsistent and keeps learning personal (P9); a pinned, checkable install lets improvements reach every teammate's agents.
