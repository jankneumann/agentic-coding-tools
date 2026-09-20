## ADDED Requirements

### Requirement: Package exports and dependency-free import
`packages/system-one-decisions` (importable as `system_one_decisions`) SHALL export
`Decision`, `decide`, and `decide_intent`, SHALL declare no required dependencies in
its `pyproject.toml`, and SHALL NOT import any vendor SDK (`typesafe_sdk` or
otherwise) at module load time.

#### Scenario: Importing the package requires nothing beyond the standard library
WHEN `import system_one_decisions` runs in a fresh virtual environment with only
the package itself installed (no optional extras)
THEN the import SHALL succeed, and `system_one_decisions.Decision`,
`system_one_decisions.decide`, and `system_one_decisions.decide_intent` SHALL all
be attributes of the module.

#### Scenario: No vendor SDK is imported at module load time
WHEN `system_one_decisions` is imported and `typesafe_sdk` is not installed
THEN the import SHALL NOT raise `ImportError`, proving the package does not import
`typesafe_sdk` eagerly.

### Requirement: `Decision` is a frozen dataclass with a fixed field set
`Decision` SHALL be a frozen (immutable) dataclass with fields `intent: str`,
`p: float`, `distribution: dict[str, float]`, `degraded: bool`, and
`evidence_class: str` defaulting to `"judgment"`.

#### Scenario: Decision instances are immutable
WHEN code attempts to set an attribute on an already-constructed `Decision`
instance
THEN it SHALL raise `dataclasses.FrozenInstanceError`.

#### Scenario: evidence_class defaults to judgment
WHEN a `Decision` is constructed without specifying `evidence_class`
THEN `evidence_class` SHALL equal `"judgment"`.

### Requirement: `decide()` is an unconditional stub with a stable signature
`decide(state: dict, questions: dict, *, site: str) -> None` SHALL accept the
documented keyword-only `site` parameter and SHALL always return `None` in this
item — no network call, no environment-variable check, and no token-budget check
exist yet (deferred to a later roadmap item that wires the live client).

#### Scenario: decide() always returns None regardless of input
WHEN `decide()` is called with any `state` dict, any `questions` dict, and any
`site` string
THEN it SHALL return `None` and SHALL make no network call.

### Requirement: `decide_intent()` always takes the fallback branch in this item
`decide_intent(state, intents, *, fallback, human_intent, act_floor=0.6,
irreversible=frozenset(), approve_floor=0.9, site) -> Decision` SHALL, because no
live acquisition path exists yet, always invoke `fallback(state)` and return
`Decision(intent=fallback(state), p=1.0, distribution={}, degraded=True,
evidence_class="judgment")`, and SHALL never raise regardless of `state` or
`intents` content.

#### Scenario: decide_intent falls back with degraded=True when unavailable
WHEN `decide_intent()` is called with any `state`, `intents`, and a `fallback`
callable that returns `"my_default_intent"`
THEN the returned `Decision.intent` SHALL equal `"my_default_intent"`,
`Decision.degraded` SHALL be `True`, and `Decision.evidence_class` SHALL equal
`"judgment"`.

#### Scenario: decide_intent never raises even when fallback raises
WHEN `decide_intent()` is called with a `fallback` callable that itself raises an
exception
THEN `decide_intent()` SHALL NOT suppress that exception silently in a way that
hides the caller's own bug — the documented contract is that `decide_intent`
itself introduces no new failure mode; the fallback's own exception propagates
unchanged (verified by asserting the specific exception type and message surface
unmodified).

### Requirement: `_route()` implements confidence-based routing over a distribution
`_route(distribution: dict[str, float], intents: dict[str, str], *, human_intent:
str, act_floor: float, irreversible: frozenset[str], approve_floor: float) ->
Decision` SHALL be a pure, synchronous function with no I/O that: routes to
`human_intent` when the top probability in `distribution` is below `act_floor`;
flags `needs_approval` (via a truthy attribute or field on the returned value, or
by routing to `human_intent`, whichever the implementation records — the test
asserts on `Decision.intent` and a recorded approval flag) when the top intent is
in `irreversible` and its probability is below `approve_floor`; and otherwise
returns the top intent unmodified.

#### Scenario: Below act_floor routes to human_intent
WHEN `_route()` is called with `distribution={"a": 0.4, "b": 0.3, "c": 0.3}` and
`act_floor=0.6`
THEN the returned `Decision.intent` SHALL equal `human_intent` and
`Decision.degraded` SHALL be `False`.

#### Scenario: At or above act_floor and not irreversible returns the top intent
WHEN `_route()` is called with `distribution={"a": 0.8, "b": 0.2}`, `act_floor=0.6`,
and `irreversible=frozenset()`
THEN the returned `Decision.intent` SHALL equal `"a"`.

#### Scenario: Irreversible intent below approve_floor is flagged for approval
WHEN `_route()` is called with `distribution={"delete": 0.75, "keep": 0.25}`,
`act_floor=0.6`, `irreversible=frozenset({"delete"})`, and `approve_floor=0.9`
THEN the returned `Decision.intent` SHALL equal `"delete"` and the result SHALL be
distinguishable (via a field or attribute the test asserts on) from an irreversible
intent that met `approve_floor`.

#### Scenario: Irreversible intent at or above approve_floor is not flagged
WHEN `_route()` is called with `distribution={"delete": 0.95, "keep": 0.05}`,
`act_floor=0.6`, `irreversible=frozenset({"delete"})`, and `approve_floor=0.9`
THEN the returned `Decision.intent` SHALL equal `"delete"` with no approval flag
set.

#### Scenario: Boundary probability equal to act_floor is treated as meeting it
WHEN `_route()` is called with a top probability exactly equal to `act_floor`
THEN the top intent SHALL be returned (the routing rule is "below act_floor", not
"at or below").

### Requirement: `decide_intent` records one event through a caller-supplied sink
`decide_intent` SHALL accept an optional keyword-only `event_sink:
Callable[[dict], None] | None = None` parameter. When provided, `decide_intent`
SHALL call it exactly once per invocation with a dict containing at least `site`,
`intent`, `p`, `distribution`, `degraded`, and `evidence_class`. When omitted (the
default), `decide_intent` SHALL NOT raise or require a sink — it simply records
nothing.

#### Scenario: event_sink receives exactly one call with the decision's fields
WHEN `decide_intent()` is called with an `event_sink` that appends its argument to
a list, against a synthetic list shaped like a `loop-state.json` `phase_history`
array
THEN the list SHALL contain exactly one new entry, and that entry's `intent`,
`degraded`, and `evidence_class` keys SHALL match the returned `Decision`'s
corresponding fields.

#### Scenario: Omitting event_sink is safe
WHEN `decide_intent()` is called without an `event_sink` argument
THEN it SHALL return a `Decision` normally and SHALL NOT raise.

### Requirement: The package is importable from every declared consumer
The package SHALL be declared as a dependency from the skills venv
(`skills/pyproject.toml`), from `packages/gen-eval` under an optional `decisions`
extra, and from `agent-coordinator` (a path dependency plus a `COPY` line in the
coordinator `Dockerfile` beside the existing `gen-eval` and `code-search` copies).

#### Scenario: Import succeeds from the skills venv
WHEN the skills venv (`skills/.venv`) is synced per its `pyproject.toml` and
`python -c "import system_one_decisions"` is run inside it
THEN the import SHALL succeed.

#### Scenario: Import succeeds from a standalone gen-eval install with the decisions extra
WHEN `packages/gen-eval` is installed standalone with its `decisions` extra (e.g.
`uv pip install packages/gen-eval[decisions]`) in an otherwise-empty virtual
environment
THEN `python -c "import system_one_decisions"` SHALL succeed in that environment.

#### Scenario: Import succeeds inside the coordinator Docker image
WHEN the coordinator Docker image is built and `docker-smoke-import`'s CI check
runs `import system_one_decisions` inside it
THEN the import SHALL succeed.
