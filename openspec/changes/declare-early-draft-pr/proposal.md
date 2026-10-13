# Open a declare-early draft PR at plan completion

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `declare-early-draft-pr`
> Effort: M
> Priority: 3

## Summary

Have /plan-feature (and /autopilot at plan completion) open a draft PR containing only the proposal, spec deltas, and contracts before implementation begins, listing contracts introduced or changed and the owners whose review is requested.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- A planned change has a draft PR with proposal, spec deltas, and contracts/ before the first implementation commit.
- The draft PR body lists contracts introduced or changed and the owners whose review is requested, as plain markdown.
- The behavior is opt-out per repository and is skipped in solo mode unless explicitly enabled.

## Rationale

The draft PR is the claim, contract announcement, and review invitation that teammates who do not use the skills can see (P4, P7, P8); it is also the git-native surface later used to mirror queue claims.
