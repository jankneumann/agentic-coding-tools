# Judge implementation strategy selection in autopilot

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-implementation-strategy-selection-in-autopilot`
> Effort: S
> Priority: 3

## Summary

Replace the four-criterion weighted sum in implementation_strategy_selector with Choice(strategy, {alternatives, lead_review}) over the package YAML and the matching design.md section, using the reserved design_path parameter, while keeping the vendor-count availability gate deterministic and falling back to lead_review when confidence is low.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- design_path is read and its matching design.md section forms part of the state, covered by a test using a package fixture.
- Confidence below the config-held floor yields lead_review, asserted by a stubbed-decision test.
- The vendor-count gate still forces lead_review when fewer than three vendors are available, regardless of the judged label.
- The existing weighted-sum selector remains reachable as the fallback and its current tests pass unchanged.

## Rationale

Pilot step 4. The selector's loc/alternatives/kind/vendors sum is a proxy for "are there two plausible designs worth comparing", and design_path is already documented as reserved for exactly this inference. Choosing alternatives costs three implementations, so a low-confidence answer must bias toward the cheap branch.
