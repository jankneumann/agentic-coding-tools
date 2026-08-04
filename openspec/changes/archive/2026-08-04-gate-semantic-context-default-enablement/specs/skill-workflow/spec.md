# skill-workflow Specification Delta

**Change ID**: `gate-semantic-context-default-enablement`

## ADDED Requirements

### Requirement: Evidence-Gated Injection Default

Semantic context injection SHALL remain disabled by default unless a valid, current, passing evaluation report authorizes it, and that report SHALL demonstrate both a retrieval-quality result and a coding-context utility result for every named consumer. The effective default SHALL be expressed as a single machine-readable declaration in the retrieval helper, so that changing it is one reviewable line.

#### Scenario: Enablement without evidence is rejected

- **WHEN** the declared default is enabled and no valid passing evaluation
  report exists
- **THEN** the enablement check SHALL fail
- **AND** it SHALL name which condition was unmet

#### Scenario: One gate passing is not enough

- **WHEN** the retrieval-quality result passes and the coding-context utility
  result does not, or the reverse
- **THEN** enablement SHALL NOT be authorized

#### Scenario: The default is one declaration

- **WHEN** the effective default is read
- **THEN** it SHALL come from a single named declaration rather than being
  inferred from the absence of an environment variable
- **AND** while that declaration is disabled, assembled context SHALL be
  identical to its behavior before this capability existed

#### Scenario: A consumer regression blocks enablement

- **WHEN** any named consumer's measured coding-context utility is below its own
  exact-search baseline
- **THEN** enablement SHALL NOT be authorized
- **AND** improvements measured for other consumers SHALL NOT offset it

### Requirement: Evidence Expiry Withdraws Injection Authorization

When the evidence authorizing injection ceases to describe the current system, the enablement check SHALL fail until the default is disabled or the evaluation is retaken. This check SHALL NOT duplicate the per-request fail-closed fallback the retrieval helper already performs.

#### Scenario: Stale evidence withdraws authorization

- **WHEN** the evaluation corpus, its thresholds, the harness version, the
  embedding fingerprint, or the reachability of the report's index revision
  changes such that the report no longer describes the tree under test
- **THEN** the enablement check SHALL fail
- **AND** disabling the default SHALL restore it to passing

#### Scenario: Runtime fallback remains the retrieval helper's responsibility

- **WHEN** an index for the exact requested revision is unavailable at request
  time
- **THEN** the retrieval helper SHALL continue to return an explicit
  exact-search fallback carrying zero hits without blocking the coding job
- **AND** the enablement check SHALL NOT introduce a second runtime path for
  that decision
