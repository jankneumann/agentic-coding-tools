# Architectural Decisions Index

This directory is **generated** by `make decisions` from `architectural:` tagged Decision bullets in session-log Phase Entries. Do not edit these files by hand.

## What belongs in this index

A Decision is *architectural* when it shapes how a capability behaves across multiple changes — patterns, constraints, or interfaces that later work either builds on or reverses. Tag such decisions with `` `architectural: <capability>` `` in the Decision bullet of the session-log Phase Entry where the call was made.

Routine engineering choices that do not outlive the change that introduced them SHOULD remain untagged — they clutter the index without adding archaeological value.

## How to read a capability timeline

Each `<capability>.md` file is reverse-chronological (newest first). Every entry carries a status (`active` or `superseded`), a back-reference to the originating session-log phase entry, and — when a later decision explicitly reverses an earlier one via `` `supersedes:` `` — bidirectional `Supersedes` / `Superseded by` links.

## Generation

```
make decisions
```

CI verifies the index is fresh by re-running `make decisions` and failing on any `git diff docs/decisions/`.

## Active capabilities in this index

- [agent-coordinator](./agent-coordinator.md)
- [configuration](./configuration.md)
- [merge-pull-requests](./merge-pull-requests.md)
- [observability](./observability.md)
- [skill-workflow](./skill-workflow.md)
- [software-factory-tooling](./software-factory-tooling.md)
