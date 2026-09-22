## ADDED Requirements

### Requirement: Executed Routing Decisions

`autopilot-roadmap` SHALL obtain and durably persist a validated routing decision before each host dispatch. The immutable dispatch context SHALL include a decision identifier, selected agent/vendor/model/location, canonical dg-05 isolation, dispatch mode, and ledger work/attempt correlation. The host seam SHALL preserve this context unchanged; the state machine SHALL not call a model SDK or select a vendor locally.

#### Scenario: Ledger-verified vendor switch

WHEN a submitted attempt reports a vendor-limit result
THEN the orchestrator SHALL resolve a fresh alternate assignment excluding the observed limited lane
AND persist a new attempt before redispatching the same item and phase
AND accept success only when the terminal VendorResultEnvelope/ledger completion matches that attempt's decision identifier and observed lane
AND reject a stale, mismatched, or unavailable completion without treating the phase as complete.

#### Scenario: Router unavailable

WHEN no validated routing decision can be obtained from the configured resolver
THEN the orchestrator SHALL use only a declared static fallback assignment with canonical isolation
OR SHALL checkpoint a fail-closed escalation
AND SHALL NOT dispatch with an un-routed context.

### Requirement: Roadmap Loop Safety Caps

The roadmap execution loop SHALL enforce durable global iteration and no-progress safeguards. Their counters and last durable-progress fingerprint SHALL be checkpointed before each dispatch and survive a resumed process.

#### Scenario: Stuck dispatch trips the cap

WHEN the configured iteration cap is reached or consecutive iterations produce no durable item, phase, or correlated-ledger transition
THEN the loop SHALL checkpoint an explicit parked/escalated outcome and return it without continuing to dispatch.

#### Scenario: Resume does not duplicate a submitted attempt

WHEN a process stops after persisting a prepared attempt and before terminal completion
THEN a resumed process SHALL reconcile the correlated ledger state before any new submission
AND SHALL NOT issue a duplicate dispatch for that attempt.
