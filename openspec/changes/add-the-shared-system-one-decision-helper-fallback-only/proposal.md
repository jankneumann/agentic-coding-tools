# Add the shared system_one decision helper, fallback-only

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `add-the-shared-system-one-decision-helper-fallback-only`
> Effort: M
> Priority: 1

## Summary

Create the installable package packages/system-one-decisions (importable as system_one_decisions) with the frozen Decision dataclass and both entry points, decide(state, questions, *, site) and decide_intent(state, intents, *, fallback, human_intent, act_floor, irreversible, approve_floor, site), implemented with no network call at all: every decision comes from the caller's existing rule via fallback and is recorded to the caller's event log with degraded=True and evidence_class "judgment". Declare it from every consuming runtime: a path dependency in skills/pyproject.toml, an optional "decisions" extra in packages/gen-eval/pyproject.toml, and a path dependency in agent-coordinator/pyproject.toml plus a COPY line in the coordinator Dockerfile beside the existing gen-eval and code-search copies.

## Dependencies

- None

## Acceptance Outcomes

- packages/system-one-decisions exports Decision(intent, p, distribution, degraded, evidence_class="judgment"), decide and decide_intent, has no required dependencies, and imports no vendor SDK.
- The package is importable from the skills venv, from a standalone `uv pip install packages/gen-eval[decisions]`, and inside the coordinator Docker image (docker-smoke-import covers `import system_one_decisions`).
- With no TYPESAFE_API_KEY set, decide_intent returns fallback(state) with degraded=True and never raises, proven by a unit test for each of the four documented checks (unavailable, act_floor, irreversible/approve_floor, normal return).
- A decide_intent call appends one event carrying intent, distribution and degraded to the caller's event log, asserted against a loop-state.json phase_history fixture.
- Unit tests in packages/system-one-decisions/tests cover act_floor routing to human_intent and needs_approval flagging for intents in the irreversible set.

## Rationale

Pilot step 0 of the proposal. Landing the helper fallback-only turns every existing rule decision in Group C into a recorded, replayable event before any model is consulted, and gives every later item a single seam to switch on. A package boundary rather than a skills/shared module is required because the three consumers (skills venv, gen-eval, coordinator image) do not share a dependency set: gen-eval is independently installable and the coordinator Dockerfile copies only skills/shared/github_classifier.py.
