## ADDED Requirements

### Requirement: Executed Routing Decisions

`autopilot-roadmap` SHALL obtain a routing decision before each dispatch and verify the dispatch honored it.

#### Scenario: Ledger-verified vendor switch

WHEN the policy engine selects switch for a limited vendor
THEN the next dispatch SHALL be issued to the alternate vendor
AND the dispatch ledger SHALL confirm the alternate vendor executed the work
AND expected and observed cost and latency deltas SHALL be persisted in checkpoint.json.

### Requirement: Roadmap Loop Safety Caps

The roadmap execution loop SHALL enforce a global iteration cap and a no-progress detector.

#### Scenario: Stuck dispatch trips the cap

WHEN consecutive iterations produce no item state transition
THEN the loop SHALL checkpoint and escalate rather than continue spinning.

### Requirement: Loud Outcome-State Failures

Applying a phase outcome against a missing loop-state file SHALL be an error, not a silent no-op.

#### Scenario: Missing state file

WHEN apply-outcome runs and the loop state file is absent
THEN the command SHALL exit non-zero with a structured error.
