# Design: Add the shared system_one decision helper, fallback-only

## Context

`packages/system-one-decisions` is the seam every other item in
`roadmap-jev-system-one-integration-assessment` calls through to reach TypeSafe's
Jev (a "System One" model). Source: `docs/proposals/jev-system-one-integration-assessment.md`
§ Integration seam, and the companion `docs/proposals/jev-twelve-factor-decision-loops.md`.

This item builds the seam with **zero network calls**: every call falls back to the
rule it replaces. Group C's `decide_intent` primitive is the harder half — its
confidence-routing logic (act_floor, approve_floor) must be fully unit-testable now,
before ri-02 wires a live client behind it.

## Capability

`system-one-decisions` (this is a new capability; the spec delta's directory name
reflects it, not the roadmap workspace name plan-roadmap defaulted to).

## Decisions

### D1 — Split routing (pure) from acquisition (stubbed)

`decide_intent`'s contract requires four independently testable branches
(unavailable → fallback; `max(distribution) < act_floor` → `human_intent`;
irreversible + `p < approve_floor` → flag `needs_approval`; otherwise return the
intent) while this item makes no network call at all. Resolved by splitting:

- `_route(distribution, intents, *, human_intent, act_floor, irreversible, approve_floor) -> Decision`
  — pure, synchronous, no I/O. Implements the three post-acquisition branches over
  an already-obtained `dict[str, float]` distribution. Exported as a private
  helper; unit-tested directly with synthetic distributions covering both sides of
  each threshold.
- `decide_intent(state, intents, *, fallback, human_intent, act_floor=0.6, irreversible=frozenset(), approve_floor=0.9, site) -> Decision`
  — the public entry point. In this item, the internal acquisition step always
  yields "unavailable" (there is no live client yet — that is ri-02's job), so
  `decide_intent` always takes the fallback branch: `Decision(intent=fallback(state),
  p=1.0, distribution={}, degraded=True, evidence_class="judgment")`. Its own tests
  cover the always-fallback behavior and the `event_sink` call; `_route`'s tests
  cover the confidence-routing logic. Together they satisfy every acceptance
  outcome without either function requiring a network call.

ri-02 replaces `decide_intent`'s internal acquisition step with a real call to
`decide()`; when that succeeds, it hands the resulting distribution to this same
`_route()`, unchanged.

### D2 — Caller-supplied event sink, not an import of autopilot's state model

`decide_intent` cannot import `skills/autopilot`'s `loop-state.json` schema without
violating the package-boundary reason this item exists (gen-eval and the
coordinator image do not carry `skills/autopilot`). Resolved with a caller-supplied
sink: `event_sink: Callable[[dict[str, Any]], None] | None = None`. When provided,
called exactly once per `decide_intent` call with
`{"site": site, "intent": ..., "p": ..., "distribution": ..., "degraded": ...,
"evidence_class": "judgment"}`. When `None` (the default), no event is recorded —
the caller must wire one to get provenance, matching the assessment's "every
decision... is recorded to the caller's event log."

The test fixture proving compatibility with `loop-state.json`'s `phase_history`
constructs a synthetic list shaped like that file's `phase_history` array and
passes `phase_history.append` as the sink — proving the event dict's shape is
appendable there, without this package importing autopilot code.

### D3 — `decide()` is an unconditional stub in this item

`decide(state, questions, *, site) -> SystemOneResponse | None` is exported (so the
public API surface is stable from this item forward) but its body is
`return None` unconditionally — there is no `TYPESAFE_API_KEY` check, no HTTP call,
and no token-budget check yet, because none of those exist until ri-02 wires the
live client and ri-02's own token-budget guard. Calling it before ri-02 lands is
always safe and always degrades.

### D4 — Package layout

```
packages/system-one-decisions/
  pyproject.toml              # name = "system-one-decisions"; no required deps
  src/system_one_decisions/
    __init__.py                # exports Decision, decide, decide_intent
    _core.py                   # Decision dataclass, _route(), decide(), decide_intent()
  tests/
    test_route.py               # _route() branch coverage
    test_decide_intent.py       # always-fallback behavior, event_sink, degraded flag
    test_decide_stub.py         # decide() always returns None
```

Mirrors `packages/code-search`'s `pyproject.toml` shape (`[project]` name,
`requires-python = ">=3.12"`, `dependencies = []`, `[project.optional-dependencies]`
reserved for ri-02's `live` extra, `[project.optional-dependencies] dev` for
`pytest`).

## Non-goals

- No live TypeSafe client, no `TYPESAFE_API_KEY` handling, no token-budget
  check, no Langfuse telemetry — all ri-02.
- No consumer wiring beyond declaring the dependency (skills venv path dep, gen-eval
  `decisions` extra, coordinator path dep + Dockerfile `COPY`) — no call site in this
  repository is migrated to use the helper in this item; that is each Group
  A/B/C item's own job.
- No `system-one-adapter` test substitute — ri-03.

## Risks

- **Risk**: a future item imports `_route` directly and starts depending on its
  exact threshold semantics before `decide_intent`'s public contract is final.
  **Mitigation**: `_route` stays private (leading underscore, not re-exported from
  `__init__.py`); only `decide_intent` is public routing surface.
