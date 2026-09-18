## ADDED Requirements

### Requirement: `decide()` declares a "live" extra and imports the vendor SDK nowhere else
`packages/system-one-decisions` SHALL declare a `live` optional extra containing
`typesafe-sdk`. The default install of the package, and of every consumer that
does not request the extra, SHALL succeed without `typesafe-sdk` installed.
`typesafe_sdk` SHALL be imported only inside `packages/system-one-decisions`
(including its own test suite) and nowhere else in the repository, enforced by
a grep-style guard test.

#### Scenario: Fallback-only install succeeds without the live extra
WHEN `packages/system-one-decisions` is installed with no extras into a fresh
virtual environment
THEN the install SHALL succeed and `import system_one_decisions` SHALL NOT raise,
even though `typesafe_sdk` is not installed.

#### Scenario: No other package or skill imports the vendor SDK
WHEN a grep-style guard test scans every `.py` file in the repository outside
`packages/system-one-decisions`
THEN it SHALL find no `import typesafe_sdk` or `from typesafe_sdk import ...`
statement.

### Requirement: `decide()` returns `None`, never raises, on any of four unavailability branches
`decide()` SHALL return `None` without raising in each of the following cases,
checked in this order: (1) `typesafe_sdk` is not installed (the `live` extra is
absent), (2) `TYPESAFE_API_KEY` is not set in the environment, (3) the estimated
token count of `state` plus the single longest serialized question exceeds
32,000 tokens, (4) `client.system_one(...)` raises any `typesafe_sdk.TypeSafeError`.
No network call SHALL be attempted for branches (1)-(3).

#### Scenario: Extra not installed
WHEN `decide()` is called in an environment where `typesafe_sdk` cannot be
imported
THEN it SHALL return `None` and SHALL NOT raise `ImportError` to the caller.

#### Scenario: Key absent
WHEN `decide()` is called with `TYPESAFE_API_KEY` unset in the environment and
`typesafe_sdk` importable
THEN it SHALL return `None` and SHALL NOT construct a live client or attempt a
network call.

#### Scenario: Token budget exceeded
WHEN `decide()` is called with a key set and `state` plus the longest question's
serialized form estimated at more than 32,000 tokens (using the repo's
~4-chars/token heuristic)
THEN it SHALL return `None` and SHALL NOT attempt a network call.

#### Scenario: Network or API failure
WHEN `decide()` is called with a key set, the extra installed, the token
estimate within budget, and the underlying `client.system_one(...)` call raises
a `typesafe_sdk.TypeSafeError` subclass (e.g. `TypeSafeAPIConnectionError` or
`TypeSafeAuthenticationError`)
THEN `decide()` SHALL return `None` and SHALL NOT propagate the exception.

### Requirement: `decide()` accepts an optional `event_sink`, invoked once per completed call
`decide(state, questions, *, site, event_sink=None)` SHALL, on a completed
(successful) call only, invoke `event_sink` exactly once with a dict carrying
`site`, `latency_ms`, `usage_input_tokens`, and `probabilities` (a per-question
mapping of label to probability, or `{"noul": <float>}` for a `Noul` answer).
`event_sink` SHALL NOT be invoked on any of the four unavailability branches.
Omitting `event_sink` SHALL be safe (no error).

#### Scenario: event_sink receives one record on a completed call
WHEN `decide()` completes successfully against a mocked client and an
`event_sink` callable is supplied
THEN `event_sink` SHALL be called exactly once with a dict containing `site`,
`latency_ms`, `usage_input_tokens`, and `probabilities` matching the mocked
response.

#### Scenario: event_sink is not invoked on any unavailability branch
WHEN `decide()` returns `None` via any of its four unavailability branches and
an `event_sink` callable is supplied
THEN `event_sink` SHALL NOT be called.

#### Scenario: Omitting event_sink is safe
WHEN `decide()` completes successfully with `event_sink` omitted
THEN it SHALL return the answer dict without raising.

### Requirement: Threshold defaults resolve from a package-owned data file, never a literal
`_route()`'s and `decide_intent()`'s `act_floor`/`approve_floor` defaults SHALL
resolve from `packages/system-one-decisions/config/thresholds.yaml` rather than
from a literal in `_core.py`. A guard test SHALL assert that no bare float
literal used as a threshold value appears anywhere in
`packages/system-one-decisions/src/` outside the config loader module.

#### Scenario: Defaults load from the config file
WHEN `packages/system-one-decisions` is imported and `decide_intent()` is
called without explicit `act_floor`/`approve_floor`
THEN the values used SHALL equal `thresholds.yaml`'s `defaults.act_floor` and
`defaults.approve_floor`.

#### Scenario: No threshold literal in scoring logic
WHEN a guard test scans `packages/system-one-decisions/src/system_one_decisions/_core.py`
THEN it SHALL find no bare float literal used as an `act_floor`/`approve_floor`
default — both SHALL be named constants imported from the config loader.
