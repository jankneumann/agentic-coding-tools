# Plan Findings: add-the-shared-system-one-decision-helper-fallback-only

## Iteration 1

| # | Type | Criticality | Description | Proposed Fix |
|---|------|-------------|-------------|--------------|
| 1 | completeness | critical | `tasks.md` is the generic five-line scaffold with no real tasks, no TDD ordering, no traceability to the four acceptance outcomes. | Rewrite with concrete, single-commit-sized, dependency-annotated tasks; tests before the code they verify; checkpoint markers. |
| 2 | testability | high | Spec scenarios repeat the acceptance-outcome sentence verbatim as a single WHEN/THEN with no failure/edge paths and no concrete mechanism. | Rewrite each requirement with the actual mechanism (module layout, function signature, branch condition) and add the missing edge scenarios (act_floor boundary, approve_floor boundary, event_sink absent). |
| 3 | assumptions | medium | `decide_intent`'s four "documented checks" (unavailable / act_floor / irreversible+approve_floor / normal return) must all be unit-testable with zero network calls in this item, but the item also says "no network call at all." Resolvable without a design-changing ambiguity: split routing logic (pure, given a distribution) from distribution acquisition (always `None` in this item since no live client exists yet). | Record as design decision D1; not escalated — a single defensible design exists and materially changes only internal factoring, not the public contract or any acceptance outcome. |
| 4 | assumptions | medium | How does `decide_intent` "append one event... to the caller's event log" without importing `skills/autopilot`'s `loop-state.json` schema (a package-boundary violation this item exists to avoid)? | Record as design decision D2: `event_sink: Callable[[dict], None] \| None` parameter, caller-supplied. The test fixture constructs a synthetic `phase_history`-shaped list without importing autopilot code. |
| 5 | completeness | medium | No `contracts/` directory. This is a pure Python library with no API/DB/event surface. | Add `contracts/README.md` stub per Step 7's "no contracts applicable" convention. |
| 6 | completeness | medium | No `work-packages.yaml`. Coordinator is live (coordinated tier), but this item has no internal parallelism to decompose — one package, one scope. | Add a single `wp-main` package honestly scoped to the package directory plus the three consumer touch points named in the proposal. |
| 7 | consistency | low | `design.md`'s "Open questions" (capability, non-goals, decisions to record) were never answered. | Answer them directly: capability is `system-one-decisions`; non-goals and decisions recorded as D1–D4 below. |

## Resolution

All findings at or above `medium` addressed in this iteration. Findings 3 and 4 are `assumptions`-type but were not escalated via AskUserQuestion: each has exactly one defensible resolution given the acceptance outcomes already fixed by the roadmap (no alternative reading changes the public contract, a test's expected behavior, or the deliverable's scope), so escalating would ask the operator to approve an implementation detail rather than resolve a genuine fork in intent.
