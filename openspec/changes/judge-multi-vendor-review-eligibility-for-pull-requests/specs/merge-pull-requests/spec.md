## MODIFIED Requirements

### Requirement: Vendor Review Artifact Resilience

`vendor_review.check_review_eligibility` SHALL determine review eligibility for
a non-skip-origin, non-draft PR by asking a calibrated judgment — a
`Noul("This PR warrants independent multi-vendor review")` plus a
`Score(risk, [...])` characterizing risk level — over the PR's title, body,
file list and diff stat (never the diff itself). The deterministic draft-PR
and origin-provenance skips (`SKIP_ORIGINS`) SHALL run first and SHALL NOT
invoke the judgment. When the judgment is unavailable, it SHALL fall back to
the existing size-threshold rule (`SMALL_PR_MAX_CHANGED_LINES` /
`SMALL_PR_MAX_FILES`, config-overridable), unchanged. An existing-review
check (fresh approval or unresolved change request) SHALL still short-circuit
eligibility independently of the judgment's answer. When the judgment drove
the decision, the returned eligibility record's `details` SHALL carry
`evidence_class: "judgment"`, the risk score, and its probability.

The vendor review dispatch (Step 9) SHALL handle PRs regardless of whether
OpenSpec planning artifacts (contracts, work-packages) exist.

<!-- Scenario ID: merge-pull-requests.judged-eligibility-overrides-size -->
#### Scenario: A small but risky PR is routed to review by the judgment

- **GIVEN** a PR of 40 changed lines touching `guardrails.py` or a policy file
- **WHEN** eligibility is checked and the judgment is available and confident it warrants review
- **THEN** the PR SHALL be eligible for vendor review
- **AND** the eligibility record SHALL carry `evidence_class: "judgment"`, the risk score, and its probability

<!-- Scenario ID: merge-pull-requests.judged-eligibility-skips-large-low-risk -->
#### Scenario: A large but low-risk PR is skipped by the judgment

- **GIVEN** a docs-only PR of 320 changed lines
- **WHEN** eligibility is checked and the judgment is available and confident it does not warrant review
- **THEN** the PR SHALL NOT be eligible for vendor review

<!-- Scenario ID: merge-pull-requests.origin-skip-precedes-judgment -->
#### Scenario: Origin and draft skips never invoke the judgment

- **GIVEN** a PR whose origin is in `SKIP_ORIGINS`, or a draft PR
- **WHEN** eligibility is checked
- **THEN** the PR SHALL be ineligible
- **AND** the judgment SHALL NOT be invoked

<!-- Scenario ID: merge-pull-requests.judgment-unavailable-falls-back -->
#### Scenario: Unavailable judgment falls back to the size rule unchanged

- **GIVEN** the judgment is unavailable (module missing, no usable answer)
- **WHEN** eligibility is checked
- **THEN** eligibility SHALL be determined by `SMALL_PR_MAX_CHANGED_LINES` / `SMALL_PR_MAX_FILES`, exactly as before this change

<!-- Scenario ID: merge-pull-requests.existing-approval-overrides-judgment -->
#### Scenario: An existing approval still skips review regardless of the judgment

- **GIVEN** a PR the judgment marked eligible for review
- **WHEN** the PR already has an `APPROVED` review
- **THEN** the PR SHALL be ineligible with reason `has_approval`

#### Scenario: Vendor review with planning artifacts
- **WHEN** a PR has an associated OpenSpec change directory containing contracts and work-packages
- **THEN** the vendor review prompt SHALL include contract and scope information for richer review context
- **AND** the review dispatch SHALL proceed normally

#### Scenario: Vendor review without planning artifacts
- **WHEN** a PR lacks contracts or work-packages (legacy PR, external contribution, non-OpenSpec PR)
- **THEN** the vendor review SHALL proceed using only the PR diff and metadata as context
- **AND** the review SHALL NOT fail, skip, or produce an error due to missing artifacts
- **AND** the review output SHALL note that artifact-based scoping was unavailable
