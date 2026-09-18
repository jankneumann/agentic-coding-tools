# Route recoverable escalation actions on confidence

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `route-recoverable-escalation-actions-on-confidence`
> Effort: M
> Priority: 4

## Summary

In EscalationHandler.handle, ask Choice(action, the EscalationAction values) over the escalation summary, impact set and attempt history, restricted to the recoverable actions for escalation types the existing table already treats as recoverable, with the prescribed mapping as the fallback.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- Escalation types whose table entry is REQUIRE_HUMAN always return REQUIRE_HUMAN regardless of the distribution, asserted per type by a parametrised test.
- The candidate action set passed for each type is a subset of that type's table-permitted recoverable actions, asserted by a test over every escalation type.
- Below act_floor the handler routes to the human intent rather than the fallback action, covered by a test.
- Every handled escalation records the chosen action, its distribution and degraded flag in the escalation record.

## Rationale

Pilot step 6 and companion section 3. The table's "no conversational decision-making" rule was correct against a chat model improvising; a calibrated choice constrained to the actions the table already permits keeps that guarantee while letting the recoverable cases pick the cheapest working recovery.
