# Design: Wire the live TypeSafe client, thresholds and telemetry

> Change ID: `wire-the-live-typesafe-client-thresholds-and-telemetry`
> Roadmap item: `ri-02` of `roadmap-jev-system-one-integration-assessment`

## Context

`ri-01` (merged) shipped `packages/system-one-decisions` with `decide()` as an
unconditional stub (always `None`) and `decide_intent()` always taking the
fallback branch. This item turns `decide()` into a real call against the live
TypeSafe API, while leaving `decide_intent()`'s fallback-only behavior
**unchanged** — wiring the acquisition step into `decide_intent()`'s routing is
explicitly deferred to `ri-03` (which adds the adapter-backed test substitute
and dry-run policy that make it safe to flip). This item's job is narrower:
make `decide()` itself live, establish the threshold-config convention, and
emit telemetry.

## Real API surface (grounding, not aspiration)

`typesafe-sdk` is a real, published PyPI package (confirmed by querying
`https://pypi.org/pypi/typesafe-sdk/json`: latest `0.7.0`, "Python SDK for
TypeSafe AI API", source at `github.com/typesafe-ai/typesafe-sdk-python`).
Installed into a scratch venv and introspected directly (no network calls
attempted — introspection only) to ground this design in the real API rather
than the assessment doc's paraphrase:

- `TypeSafeClient(*, api_key: str | None = None, model=None, retry=None,
  timeout=None, ...)` — a context manager (`with TypeSafeClient() as client:`).
  `api_key=None` reads `TYPESAFE_API_KEY` from the environment per the
  package's own quickstart.
- `client.system_one(state: JSONContent, questions: Mapping[str, Noul | Choice
  | Score | ...], *, model=None, retry=None, timeout=None, ...) ->
  SystemOneResponse`.
- `SystemOneResponse`: `model: str`, `usage: Usage`, `answers: dict[str,
  NoulAnswer | ChoiceAnswer | ScoreAnswer]`.
  - `Usage`: `input_tokens: int | None`, `output_tokens: int | None`.
  - `ChoiceAnswer`: `choice: str`, `confidence: float`, `probabilities: dict[str, float]`.
  - `ScoreAnswer`: `score: float`, `confidence: float`, `probabilities: dict[int, float]`.
  - `NoulAnswer`: `noul: float` (a calibrated scalar probability; no distribution).
- Exception hierarchy, all deriving from `TypeSafeError(Exception)`:
  `TypeSafeAPIConnectionError` (also `ConnectionError`),
  `TypeSafeAPITimeoutError` (also `TimeoutError`), `TypeSafeAuthenticationError`,
  `TypeSafeRateLimitError`, `TypeSafeBadRequestError`,
  `TypeSafeAPIResponseValidationError`, and others — all `TypeSafeAPIError`
  subclasses.

## Decisions

### D1 — `decide()`'s four failure branches, checked in this order

1. **Extra not installed**: `import typesafe_sdk` (done lazily, inside
   `decide()`, never at module load) raises `ImportError` → return `None`.
   Checked first so a fallback-only install (no `live` extra) never reaches
   the key check and never logs a spurious traceback.
2. **Key absent**: `os.environ.get("TYPESAFE_API_KEY")` is falsy → return
   `None` before constructing a client. (The SDK would itself raise
   `TypeSafeAuthenticationError` on first real request if a client were
   constructed with no key and then called, but checking locally makes the
   "no attempt" case explicit and avoids depending on the SDK's own lazy vs.
   eager key validation.)
3. **Token budget exceeded**: estimate the token count of `state` plus the
   single longest serialized question using the repo's existing ~4-chars/token
   heuristic (`skills/autopilot/scripts/token_budget_check.py::_estimate_tokens`
   — reused as the documented convention, not re-derived) over
   `json.dumps(state, default=str)` and each question's own `repr()`. If the
   estimate exceeds 32,000 tokens → return `None` without calling the client.
4. **Network / API failure**: any `typesafe_sdk.TypeSafeError` raised by
   `client.system_one(...)` → return `None`.

Every branch returns bare `None` — `decide()`'s return type stays
`dict[str, Any] | None`, matching `ri-01`'s "never raises" contract exactly.
On success, `decide()` returns `response.answers` (the real SDK answer dict)
unchanged: no repackaging into a `system_one_decisions`-owned type. Callers
that want `Decision`/`_route`'s confidence-based routing already have it
available for `decide_intent()`'s own domain (intent classification); `decide()`
remains the thinner, more general primitive that mirrors `client.system_one`
one level up.

### D2 — `decide()` gains the same optional `event_sink` `decide_intent()` already has

`decide(state, questions, *, site, event_sink=None) -> dict[str, Any] | None`.
`event_sink`, when provided, is called exactly once per **completed** call
(the success path only — none of the four failure branches call it, since
there is nothing to report yet: no latency was spent talking to the API, no
`usage` exists). The record shape:

```python
{
    "site": site,
    "latency_ms": ...,               # wall-clock around client.system_one()
    "usage_input_tokens": response.usage.input_tokens,
    "probabilities": {               # per-question, per-label
        key: (answer.probabilities if hasattr(answer, "probabilities") else {"noul": answer.noul})
        for key, answer in response.answers.items()
    },
}
```

This mirrors `ri-01`'s D2 exactly (same rationale: avoid importing a
consumer's telemetry stack — Langfuse in this case — from inside the package).
No `langfuse` dependency is added to `packages/system-one-decisions`. Whether
a caller's `event_sink` actually forwards to Langfuse is that caller's
decision, made when it migrates a call site (a later roadmap item, `ri-09`
onward) — not this item's job, matching `ri-01`'s explicit non-goal ("no
migration of any existing call site").

### D3 — Threshold config: a package-owned data file, not `architecture.config.yaml`

`architecture.config.yaml` (repo root) is scoped exclusively to
`skills/refresh-architecture`'s report generator — its schema
(`config_schema.py`) has no threshold concept and adding one there would be
unrelated coupling, not reuse. The acceptance outcome's actual intent — "no
threshold literal in a scoring module, defaults resolve from data" — is the
same rule `packages/context-eval` already enforces (`corpus/manifest.yaml` +
`test_thresholds_are_not_readable_from_the_scoring_modules`), just misnamed in
the original assessment doc's paraphrase.

Add `packages/system-one-decisions/src/system_one_decisions/config/thresholds.json`
(inside the importable package, not at the package root — `context-eval`'s
`corpus/` can live outside `src/` because it's a checkout-only tool; this
package is installed as a real wheel into three consumer venvs including a
Docker image built via `uv sync --no-install-project`, so its data file must
be resolvable through `importlib.resources` regardless of whether the install
is editable or a built wheel):

```json
{
  "schema_version": 1,
  "defaults": {
    "act_floor": 0.6,
    "approve_floor": 0.9
  }
}
```

JSON, not YAML: `ri-01`'s still-active spec requirement ("Package exports and
dependency-free import") requires `packages/system-one-decisions` to declare
no required dependencies, and parsing YAML would require adding `pyyaml` as
one. `json` is stdlib, so the config file moved from `.yaml` to `.json`
without adding a dependency.

`[tool.hatch.build.targets.wheel]` needs `packages = ["src/system_one_decisions"]`
unchanged (hatchling includes non-`.py` files under an included package
directory by default) — verified as part of task 1.3's checkpoint by
inspecting the built wheel's file listing. A small loader (`_config.py`) reads
it once via `importlib.resources.files("system_one_decisions") / "config" /
"thresholds.json"` (never a filesystem path relative to `__file__`, which
would break under a zipped wheel), caches on first access, and exposes
`DEFAULT_ACT_FLOOR: float` and `DEFAULT_APPROVE_FLOOR: float`. `_route()`'s and `decide_intent()`'s existing
`act_floor: float = 0.6` / `approve_floor: float = 0.9` keyword defaults become
`act_floor: float = DEFAULT_ACT_FLOOR` / `approve_floor: float =
DEFAULT_APPROVE_FLOOR` — callers that already pass explicit values (none exist
yet; no call site migration has happened) are unaffected either way. A guard
test (`test_no_threshold_literals.py`) greps `src/system_one_decisions/*.py`
for bare float literals outside `_config.py` and the two named constants'
definitions, failing the build the same way `context-eval`'s equivalent guard
does.

### D4 — Lazy, cached client construction

`typesafe_sdk` is imported and a `TypeSafeClient` is constructed lazily inside
`decide()`'s call path (a module-level `_get_client()` helper with a
`functools.lru_cache(maxsize=1)`), never at package import time. This keeps
`ri-01`'s "no vendor SDK import at module load time" guarantee intact — the
fallback-only requirement scenario from `ri-01`'s own spec
(`No vendor SDK is imported at module load time`) still holds after this item,
because that assertion is about *import*, not about calling `decide()`, and
`decide()` was already documented as the seam where the live client would
eventually appear (`ri-01` design D3: "Simplest correct behavior until the
live client lands").

### D5 — Test doubles: real SDK types, no real network

`packages/system-one-decisions/tests` may import `typesafe_sdk` directly (it
is "inside the package", not a violation of the single-import constraint,
which is about *runtime* code reachable from other packages/skills). Tests
construct real `Choice`/`Noul`/`Score` question instances and real
`ChoiceAnswer`/`NoulAnswer`/`ScoreAnswer`/`Usage`/`SystemOneResponse` instances
for monkeypatched-client fixtures, so the branch logic is exercised against
the SDK's actual shapes rather than a hand-rolled fake that could silently
drift from the real one. No test contacts the real API — `TYPESAFE_API_KEY`
is never read from the real environment in CI; tests set/unset it via
`monkeypatch.setenv`/`delenv`.

## Non-goals (out of scope for this item)

- `decide_intent()`'s acquisition step remains "always fallback" — unchanged
  from `ri-01`. Wiring it to `decide()`'s new live path is `ri-03`'s job (the
  adapter-backed test substitute and dry-run policy make that switch safe).
- No migration of any existing call site (same non-goal as `ri-01`).
- No `langfuse` dependency added to this package; `event_sink` is the seam,
  not an integration.
- No public `Choice`/`Noul`/`Score` re-export from `system_one_decisions` —
  no caller in this roadmap constructs a question yet.

## Risks

- **PyPI package drift**: this design is grounded in `typesafe-sdk==0.7.0`'s
  actual introspected shapes. If a future version changes `SystemOneResponse`
  field names, `decide()`'s D1/D2 branches would need updating; pin the extra
  loosely (`>=0.7,<1`) rather than exactly. `packages/system-one-decisions`
  already has a dependabot `pip` entry (added in `ri-01`'s CI-coverage fix),
  so a future `typesafe-sdk` release is already watched — no new dependabot
  entry is needed for this item.
- **No live credential in any CI or sandbox environment reachable from this
  session**: every success-path assertion (D1 branch 4 not firing, `event_sink`
  receiving the right shape) is tested against a monkeypatched client, never
  the real API. This is consistent with `ri-01`'s own verification approach
  (no docker daemon there either) and does not block merging — the coverage
  the acceptance outcomes actually ask for is the four failure branches plus
  the telemetry shape, all of which are fully testable without credentials.
