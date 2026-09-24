# Narrow deployable-surface fallout with a high-floor judgment

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `narrow-deployable-surface-fallout-with-a-high-floor-judgment`
> Effort: M
> Priority: 6

## Summary

For the unknown bucket only in gate_logic.classify_deployable_surface, ask Noul("This change alters the behaviour of a running service") and accept non-deployable only when that probability is at or below a low config-held ceiling (about 0.1); any higher probability keeps failing closed to deployable. Declared frontmatter and the proven-non-deployable prefix set stay authoritative.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- Changes with declared frontmatter or a prefix in the proven-non-deployable set never reach a decision call, asserted by a call-count test.
- A probability of altering a running service above the configured ceiling still yields deployable (fail closed), covered by a parametrised test around the ceiling including a high-probability case that must remain deployable.
- Every judged classification writes DEGRADED-style provenance ("derived by system_one, p(alters service)=0.04") into the validation report via record_degraded-equivalent plumbing, asserted on a report fixture.
- A replay over recorded unknown-bucket changes shows no change previously classified deployable being downgraded unless its probability of altering a service is at or below the ceiling.

## Rationale

Pilot step 7. This is a gate input, so it goes last and asymmetrically: the judgment may only skip container phases for changes it is very confident do not touch a running service, never add risk. The cost being removed is Docker-dependent smoke, security and E2E phases on changes that do not need them.
