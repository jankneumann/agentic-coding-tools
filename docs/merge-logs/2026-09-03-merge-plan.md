# Merge Plan

- Schema: `1.0`
- Generated: `2026-09-04T02:09:05.859667+00:00`
- Authoritative storage: `file`
- Base branch: `main`

## Nodes

| PR | Title | Origin | Outcome | Strategy | Auto | Gates | CI | Staleness | Comments | Revalidate | Blocking reason |
|----|-------|--------|---------|----------|------|-------|----|-----------|----------|------------|-----------------|
| #468 | plan: add-model-usage-ledger — end-to-end model usage observability | openspec | pending | rebase | no | proposal_acceptance | clean | fresh | 6 | no | refined and reviewed; held at the proposal_acceptance gate. Unlike the Tier A claude/fix-* branches, this carries a real openspec/changes/<id>/proposal.md, so the gate is live rather than vacuous. Operator approval required before merge. |
| #467 | plan(standardize-port-leases): proposal, design, specs, tasks, contracts, work-packages | openspec | pending | rebase | no | proposal_acceptance | clean | fresh | 5 | no | refined and reviewed; held at the proposal_acceptance gate. Unlike the Tier A claude/fix-* branches, this carries a real openspec/changes/<id>/proposal.md, so the gate is live rather than vacuous. Operator approval required before merge. |
| #465 | fix(coordinator): close two fail-open paths in trust resolution (#408 defects 2 and 3) | openspec | merged | rebase | no | proposal_acceptance | clean | fresh | 1 | no | — |
| #464 | fix(coordinator): stop recording failed migrations as applied, default to postgres (#456) | openspec | merged | rebase | no | proposal_acceptance | clean | fresh | 2 | no | — |
| #463 | fix(coordinator): restore the audit trail on the postgres backend (#455) | openspec | merged | rebase | no | proposal_acceptance | clean | fresh | 0 | no | — |
| #422 | feat(configuration): point pi standard tier at stealth/ox-alpha | openspec | pending | rebase | no | proposal_acceptance | clean | stale | 1 | no | — |
| #417 | feat(plan): centralize model policy ownership | openspec | pending | rebase | no | proposal_acceptance | clean | unknown | 0 | no | — |
| #411 | chore(architecture): refresh architecture analysis artifacts | openspec | pending | rebase | no | proposal_acceptance | blocked | stale | 3 | no | — |
| #408 | fix(coordinator): main cannot boot on PostgreSQL — restore boot, audit trail, and two trust escalations | openspec | closed | rebase | no | proposal_acceptance | unknown | stale | 2 | no | closed as superseded by #463/#464/#465 (all merged). 033_audit_log_delegated_from.sql is byte-identical to the 035 #463 landed. P2 thread genuinely dead (_release_claimed_task no longer exists); P1 thread NOT superseded, preserved as issue #474; comment-only trust_resolution invariant preserved as PR #483. |
| #363 | feat(review): harden consensus and recovery | openspec | pending | rebase | no | proposal_acceptance | blocked | unknown | 0 | no | — |
| #353 | feat(openspec): propose behavior handbook layer for architecture pipeline | openspec | pending | rebase | no | proposal_acceptance | unknown | stale | 2 | no | — |
| #472 | fix(ci): skip the Playwright e2e test when the npx probe times out | other | merged | squash | no | required_review | clean | fresh | 0 | no | — |

## Dependency Edges

- #468 → #472
- #467 → #468
- #467 → #472
- #465 → #472
- #464 → #463
- #464 → #472
- #463 → #472
- #411 → #422
- #408 → #411
- #408 → #422
- #408 → #463
- #408 → #464
- #408 → #465
- #353 → #408
- #353 → #411
- #353 → #422
