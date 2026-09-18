# Judge multi-vendor review eligibility for pull requests

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-multi-vendor-review-eligibility-for-pull-requests`
> Effort: M
> Priority: 3

## Summary

Replace the under-50-lines / under-3-files skip in vendor_review.check_review_eligibility with Noul("This PR warrants independent multi-vendor review") and Score(risk, ["docs/config only", "internal refactor", "behaviour change", "security or data path"]) over the PR title, body, file list and diff stat, keeping the size rule as the degraded path.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- A fixture PR of under 50 changed lines touching guardrails.py or a policy file is routed to multi-vendor review; a docs-only PR of over 300 lines is not.
- The dependabot/renovate/Jules-subtype origin skip list still short-circuits before any decision call, asserted by a call-count test.
- SMALL_PR_MAX_CHANGED_LINES and SMALL_PR_MAX_FILES move to config and remain the fallback when the helper returns None.
- The eligibility record in the merge report carries evidence_class "judgment", the risk score and its probability.

## Rationale

Pilot step 4. A 40-line change to guardrails.py or a Cedar policy is "small" under the current rule while a 300-line docs move is "large", so the size threshold routes review effort by the wrong variable. Provenance-based skips are facts and stay deterministic.
