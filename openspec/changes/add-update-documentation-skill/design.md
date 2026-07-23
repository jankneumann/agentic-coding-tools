# Historical design: documentation inventory synchronization

> **Status: SUPERSEDED — HISTORICAL RATIONALE ONLY**
> Replacement: `add-deterministic-context-producer-checks`

This document preserves the useful design reasoning from the original proposal.
It is not an implementation plan. ri-05 incorporates the retained decisions into
the registered `documentation.inventory` producer and rejects the original
independent lifecycle wiring.

## Retained Decisions

### Generated marker regions preserve authored prose

Mechanical inventories belong between explicit
`<!-- GENERATED: begin docs:<block-id> -->` and matching end markers. Renderers
own only those bytes. Missing, duplicate, or unbalanced markers fail closed;
content outside marker regions remains byte-identical.

### Filesystem state is the inventory source

Skill entries derive from `skills/*/SKILL.md`, capability inventory derives from
canonical OpenSpec specs, and documentation inventory derives from tracked
documentation paths. A second hand-maintained manifest would introduce another
drift source.

### Generate and check share one renderer

Generate mode may update declared marker regions. Check mode renders through the
same functions into memory or a temporary tree and compares bytes without
changing tracked or untracked checkout state.

### Target-specific renderers remain separate

README summaries, agent guidance indexes, and detailed skill catalogues have
different presentation needs. They share scanner records and marker mechanics
but retain target-specific rendering functions and golden tests.

### Stable diagnostics distinguish drift from failure

Clean output, repairable drift, malformed markers, parsing failure, and broken
links require distinct machine-readable validation/remediation results. ri-05
maps these outcomes to the canonical ri-06 `ProducerResult` contract.

## Rejected Historical Decisions

The original design proposed direct pre-commit, post-merge, cleanup-feature, and
validate-feature integration, including a post-merge auto-commit. Those decisions
are superseded:

- ri-05 supplies only the independently runnable producer;
- ri-10 decides deterministic drift-gate policy;
- ri-11 runs exactly one main convergence operation.

No code should be implemented from this historical design document.
