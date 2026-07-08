# Amend skill-workflow spec for policy-authorized sync windows

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `amend-skill-workflow-spec-for-policy-authorized-sync-windows`
> Effort: S
> Priority: 2

## Summary

Amend the "Main Receives Work Through PR Sync Points" requirement so sync-point skills MAY also run under a scheduled sync window declared in the trust posture (cadence, allowed sources, auto-merge ceiling), with the active-agent guard and validation gates unchanged.

## Dependencies

- `ri-04`

## Acceptance Outcomes

- openspec validate passes with the amended requirement.
- The user-invoked path remains the documented default; scheduled windows require an explicit posture declaration.

## Rationale

Sync points are user-invoked by spec today; this deliberate, reviewed relaxation is scoped to the posture file so interactive repos are unaffected.
