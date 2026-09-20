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
- Confidence below the config-held floor yields lead_review (via the existing weighted-sum fallback), asserted by a stubbed-decision test.
- Vendor availability is included in the judged call's state as context rather than a new hard pre-judgment gate; the existing weighted-sum fallback's own treatment of vendor count (one additive term among four, no hard floor) is left completely unmodified, since two existing tests (test_fewer_than_3_vendors_reduces_score, test_boundary_score_2_selects_alternatives) deliberately assert "alternatives" is reachable with only 2 vendors when the sum still clears the threshold.
- The existing weighted-sum selector remains reachable as the fallback and its current tests -- including both vendor-count boundary tests above -- pass unchanged.

## Rationale

Pilot step 4. The selector's loc/alternatives/kind/vendors sum is a proxy for "are there two plausible designs worth comparing", and design_path is already documented as reserved for exactly this inference. Choosing alternatives costs three implementations, so a low-confidence answer must bias toward the cheap branch.

**Grounding correction (2026-09-18):** the scaffolded text above claimed "the vendor-count gate still forces lead_review when fewer than three vendors are available" as existing behavior being preserved. It is not -- `_compute_score` treats vendor count as one additive term among four, with no hard floor anywhere, and two existing tests deliberately assert "alternatives" is selected with only 2 vendors when the sum still clears the threshold. A new hard pre-judgment gate would have broken both tests, directly contradicting the very next acceptance outcome's "pass unchanged" requirement. Resolved by making vendor availability part of the judged call's context instead of a gate, leaving the deterministic fallback (and its current tests) completely untouched.
