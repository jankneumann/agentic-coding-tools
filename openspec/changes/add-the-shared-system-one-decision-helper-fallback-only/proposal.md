# Add the shared system_one decision helper, fallback-only

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `add-the-shared-system-one-decision-helper-fallback-only`
> Effort: M
> Priority: 1

## Summary

Create skills/shared/system_one.py with the frozen Decision dataclass and both entry points, decide(state, questions, *, site) and decide_intent(state, intents, *, fallback, human_intent, act_floor, irreversible, approve_floor, site), implemented with no network call at all: every decision comes from the caller's existing rule via fallback and is recorded to the caller's event log with degraded=True and evidence_class "judgment".

## Dependencies

- None

## Acceptance Outcomes

- skills/shared/system_one.py exports Decision(intent, p, distribution, degraded, evidence_class="judgment"), decide and decide_intent, and imports no vendor SDK.
- With no TYPESAFE_API_KEY set, decide_intent returns fallback(state) with degraded=True and never raises, proven by a unit test for each of the four documented checks (unavailable, act_floor, irreversible/approve_floor, normal return).
- A decide_intent call appends one event carrying intent, distribution and degraded to the caller's event log, asserted against a loop-state.json phase_history fixture.
- Unit tests in skills/shared/tests cover act_floor routing to human_intent and needs_approval flagging for intents in the irreversible set.

## Rationale

Pilot step 0 of the proposal. Landing the helper fallback-only turns every existing rule decision in Group C into a recorded, replayable event before any model is consulted, and gives every later item a single seam to switch on. It is the shared infrastructure all other items depend on, and it mirrors skills/shared/github_classifier.py as the portable home for cross-skill logic.
