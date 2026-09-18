# Narrow deployable-surface fallout with a high-floor judgment

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `narrow-deployable-surface-fallout-with-a-high-floor-judgment`
> Effort: M
> Priority: 6

## Summary

For the unknown bucket only in gate_logic.classify_deployable_surface, ask Noul("This change alters the behaviour of a running service") and accept non-deployable only above a high config-held floor (about 0.9), otherwise keep failing closed to deployable. Declared frontmatter and the proven-non-deployable prefix set stay authoritative.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- Changes with declared frontmatter or a prefix in the proven-non-deployable set never reach a decision call, asserted by a call-count test.
- A probability below the configured floor still yields deployable (fail closed), covered by a parametrised test around the floor.
- Every judged classification writes DEGRADED-style provenance ("derived by system_one, p=0.93") into the validation report via record_degraded-equivalent plumbing, asserted on a report fixture.
- A replay over recorded unknown-bucket changes shows no change previously classified deployable being downgraded without the floor being met.

## Rationale

Pilot step 7. This is a gate input, so it goes last and asymmetrically: the judgment may only skip container phases for changes it is very confident about, never add risk. The cost being removed is Docker-dependent smoke, security and E2E phases on changes that do not need them.
