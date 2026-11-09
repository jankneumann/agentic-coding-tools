# Merge Plan

- Schema: `1.1`
- Generated: `2026-09-04T02:09:05.859667+00:00`
- Authoritative storage: `file`
- Base branch: `main`

## Nodes

| PR | Title | Origin | Kind | Skill | Outcome | Strategy | Auto | Gates | CI | Failure class | Staleness | Comments | Revalidate | Blocking reason |
|----|-------|--------|------|-------|---------|----------|------|-------|----|---------------|-----------|----------|------------|-----------------|
| #468 | plan: add-model-usage-ledger — end-to-end model usage observability | openspec | plan | iterate-on-plan | merged | rebase | no | proposal_acceptance | clean | — | fresh | 6 | no | — |
| #467 | plan(standardize-port-leases): proposal, design, specs, tasks, contracts, work-packages | openspec | plan | iterate-on-plan | merged | rebase | no | proposal_acceptance | clean | — | fresh | 5 | no | — |
| #465 | fix(coordinator): close two fail-open paths in trust resolution (#408 defects 2 and 3) | openspec | implementation | iterate-on-implementation | merged | rebase | no | proposal_acceptance | clean | — | fresh | 1 | no | — |
| #464 | fix(coordinator): stop recording failed migrations as applied, default to postgres (#456) | openspec | implementation | iterate-on-implementation | merged | rebase | no | proposal_acceptance | clean | — | fresh | 2 | no | — |
| #463 | fix(coordinator): restore the audit trail on the postgres backend (#455) | openspec | implementation | iterate-on-implementation | merged | rebase | no | proposal_acceptance | clean | — | fresh | 0 | no | — |
| #422 | feat(configuration): point pi standard tier at stealth/ox-alpha | openspec | implementation | iterate-on-implementation | pending | rebase | no | proposal_acceptance | clean | — | stale | 1 | no | — |
| #417 | feat(plan): centralize model policy ownership | openspec | plan | iterate-on-plan | pending | rebase | no | proposal_acceptance | clean | — | unknown | 0 | no | — |
| #411 | chore(architecture): refresh architecture analysis artifacts | openspec | implementation | iterate-on-implementation | pending | rebase | no | proposal_acceptance | blocked | — | stale | 3 | no | — |
| #408 | fix(coordinator): main cannot boot on PostgreSQL — restore boot, audit trail, and two trust escalations | openspec | implementation | iterate-on-implementation | closed | rebase | no | proposal_acceptance | unknown | — | stale | 2 | no | closed as superseded by #463/#464/#465 (all merged). 033_audit_log_delegated_from.sql is byte-identical to the 035 #463 landed. P2 thread genuinely dead (_release_claimed_task no longer exists); P1 thread NOT superseded, preserved as issue #474; comment-only trust_resolution invariant preserved as PR #483. |
| #363 | feat(review): harden consensus and recovery | openspec | plan | iterate-on-plan | pending | rebase | no | proposal_acceptance | blocked | — | unknown | 0 | no | — |
| #353 | feat(openspec): propose behavior handbook layer for architecture pipeline | openspec | plan | iterate-on-plan | pending | rebase | no | proposal_acceptance | unknown | — | stale | 2 | no | — |
| #472 | fix(ci): skip the Playwright e2e test when the npx probe times out | other | automation | quick-task | merged | squash | no | required_review | clean | — | fresh | 0 | no | — |

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
