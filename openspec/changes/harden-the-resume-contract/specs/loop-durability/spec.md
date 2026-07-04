## ADDED Requirements

### Requirement: Context-Free Resume

Autopilot and roadmap loops SHALL be resumable from persisted state by a fresh session with no conversational context.

#### Scenario: Kill-resume matrix

WHEN a loop is terminated at any phase boundary and resumed in a clean process
THEN the final state SHALL be identical to an uninterrupted run.

#### Scenario: Resume freshness check

WHEN persisted checkpoint state disagrees with the current branch state (for example an intervening human merge)
THEN resume SHALL reconcile or escalate instead of blindly continuing.
