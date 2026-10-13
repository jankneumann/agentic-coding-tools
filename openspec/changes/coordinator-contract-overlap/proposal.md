# Extend coordinator overlap analysis to requirements and contracts

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `coordinator-contract-overlap`
> Effort: M
> Priority: 3

## Summary

Extend feature_registry.py overlap analysis from lock keys and files to OpenSpec requirements and contract files, and merge its live claims into the git-native collision report when the coordinator is reachable.

## Dependencies

- `ri-06`

## Acceptance Outcomes

- feature_registry overlap analysis reports two registered features touching the same requirement or contract file as a collision at the matching level.
- With the coordinator reachable, /plan-feature's collision report includes live claims not yet visible on the git remote, labeled as such.
- With the coordinator unreachable, the collision report is identical to the git-native report and planning is not blocked.

## Rationale

The coordinator half of P7: live claims catch in-flight work that has not yet been pushed, enriching but never replacing the git-native scan.
