# Tasks: Make the orchestrator obey the router

> Change ID: `make-the-orchestrator-obey-the-router`

## Ordered work packages

- [x] 1. Define the versioned routing-dispatch context contract and checkpoint safety state.
  - Add `contracts/routing-dispatch-context.schema.json`, `design.md`, and package metadata.
  - Bind immutable `decision_id`, selected lane, canonical isolation, dispatch/ledger work ID, and observed lane; define fail-closed validation and resume idempotency.
  - Depends on: dg-02, dg-04, dg-05.

- [x] 2. Inject validated route decisions before every host dispatch.
  - Add a bridge-backed resolver protocol; preserve host-assisted execution and never make model SDK calls from the state machine.
  - Persist the prepared attempt before dispatch and carry the opaque context unchanged to the host seam.
  - Depends on: 1.

- [x] 3. Execute ledger-verified alternate-lane retries.
  - On capacity failure, exclude the observed lane, resolve a fresh decision, and redispatch the same item phase only through a new durable attempt.
  - Require terminal ledger completion to echo the active decision/attempt/lane; reject mismatches and unavailable ledger states.
  - Depends on: 1, 2.

- [x] 4. Add resumable loop-safety guards.
  - Persist global iteration count, durable-progress fingerprint, consecutive no-progress count, and escalation record; checkpoint before parking/escalating.
  - Reset only on a durable item/phase/ledger transition; cover restart behavior and bounded switch retries.
  - Depends on: 1, 3.

- [ ] 5. Validate the contract end to end and update evidence.
  - Add focused unit and integration coverage for decision injection, isolation preservation, alternate completion, mismatch/ledger failure, cap/no-progress, and restart idempotency.
  - Run strict OpenSpec, package/context validation, focused and full relevant suites, then independent implementation review.
  - Depends on: 2, 3, 4.
