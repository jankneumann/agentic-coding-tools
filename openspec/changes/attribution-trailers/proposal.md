# Stamp attribution trailers on skill-authored commits and PRs

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `attribution-trailers`
> Effort: S
> Priority: 3

## Summary

Emit On-Behalf-Of and Correlation-Id commit trailers and PR-body metadata from skill-authored commits and PRs, as the git-native fallback carrier of the coordinator's causal IDs.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- Skill-authored commits carry On-Behalf-Of and Correlation-Id trailers, verified by a test over a generated commit.
- Skill-created PR bodies include a metadata block with the principal chain and correlation ID readable as plain markdown.
- With the coordinator unavailable, trailers are still written using locally generated IDs.

## Rationale

Git is the source of truth and teammates without coordinator access must still see who acted on whose behalf (P1, P9); trailers make attribution and later correction-linking work from the git remote alone.
