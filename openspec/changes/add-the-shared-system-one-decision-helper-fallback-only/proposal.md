# Add the shared system_one decision helper, fallback-only

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `add-the-shared-system-one-decision-helper-fallback-only`
> Effort: M
> Priority: 1

## Summary

Create the installable package packages/system-one-decisions (importable as system_one_decisions) with the frozen Decision dataclass and both entry points, decide(state, questions, *, site) and decide_intent(state, intents, *, fallback, human_intent, act_floor, irreversible, approve_floor, site), implemented with no network call at all: every decision comes from the caller's existing rule via fallback and is recorded to the caller's event log with degraded=True and evidence_class "judgment". Declare it from every consuming runtime: a path dependency in skills/pyproject.toml, an optional "decisions" extra in packages/gen-eval/pyproject.toml, and a path dependency in agent-coordinator/pyproject.toml plus a COPY line in the coordinator Dockerfile beside the existing gen-eval and code-search copies.

## Dependencies

- None

## Impact

- **New capability**: `system-one-decisions` (spec delta at
  `specs/system-one-decisions/spec.md`).
- **New package**: `packages/system-one-decisions/`.
- **Touched, not migrated**: `skills/pyproject.toml`, `packages/gen-eval/pyproject.toml`,
  `agent-coordinator/pyproject.toml`, `agent-coordinator/Dockerfile` — each gains a
  dependency declaration only. No existing call site is migrated to use the helper
  in this item; that is each later Group A/B/C roadmap item's own job.

## Approaches Considered

### Approach A — `skills/shared/` module (rejected; superseded assessment text)

**Description**: Add `skills/shared/system_one.py`, mirroring
`skills/shared/github_classifier.py`.
**Pros**: Simplest possible location; no new package to publish.
**Cons**: Unreachable from two of the three consumers — the coordinator
Dockerfile copies exactly one file out of `skills/shared/`
(`github_classifier.py`), and `packages/gen-eval` is independently installable
with its own dependency set. A reviewer on the parent proposal (PR #565) flagged
this and the assessment document was corrected to Approach B before this item was
scaffolded.
**Effort**: XS.

### Approach B — Installable package under `packages/` (Recommended)

**Description**: `packages/system-one-decisions/`, declared as a path dependency
from each of the three consuming runtimes (skills venv, gen-eval's optional
extra, coordinator path dependency + Dockerfile `COPY`), mirroring how
`packages/gen-eval` and `packages/code-search` are already wired into the
coordinator image.
**Pros**: Reachable from every consumer by construction; matches an existing,
proven pattern in this repo; keeps the SDK import (added in ri-02) confined to
one module regardless of which runtime loads it.
**Cons**: One more `pyproject.toml` to maintain; requires touching four files
outside the new package to wire it in.
**Effort**: M.

### Approach C — Vendor `system_one_decisions` logic into each consumer separately

**Description**: Duplicate the `Decision` dataclass and routing logic into
`skills/shared/`, `packages/gen-eval/src/gen_eval/`, and
`agent-coordinator/src/`, each independently.
**Pros**: No new package boundary to design.
**Cons**: Three copies of confidence-routing logic that must be kept in sync by
hand — exactly the kind of drift this repo's own conventions (e.g.
`finding-coercion.json` being a single shared file rather than three copies)
exist to avoid. Rejected outright.
**Effort**: L (three implementations, plus the ongoing cost of keeping them
identical).

### Selected Approach

**Approach B**, for the reason given in its Cons/Pros: it is the only approach
reachable from all three consumers without duplicating logic, and it follows an
existing, working pattern in this repository rather than inventing a new one.

## Acceptance Outcomes

- packages/system-one-decisions exports Decision(intent, p, distribution, degraded, evidence_class="judgment"), decide and decide_intent, has no required dependencies, and imports no vendor SDK.
- The package is importable from the skills venv, from a standalone `uv pip install packages/gen-eval[decisions]`, and inside the coordinator Docker image (docker-smoke-import covers `import system_one_decisions`).
- With no TYPESAFE_API_KEY set, decide_intent returns fallback(state) with degraded=True and never raises, proven by a unit test for each of the four documented checks (unavailable, act_floor, irreversible/approve_floor, normal return).
- A decide_intent call appends one event carrying intent, distribution and degraded to the caller's event log, asserted against a loop-state.json phase_history fixture.
- Unit tests in packages/system-one-decisions/tests cover act_floor routing to human_intent and needs_approval flagging for intents in the irreversible set.

## Rationale

Pilot step 0 of the proposal. Landing the helper fallback-only turns every existing rule decision in Group C into a recorded, replayable event before any model is consulted, and gives every later item a single seam to switch on. A package boundary rather than a skills/shared module is required because the three consumers (skills venv, gen-eval, coordinator image) do not share a dependency set: gen-eval is independently installable and the coordinator Dockerfile copies only skills/shared/github_classifier.py.
