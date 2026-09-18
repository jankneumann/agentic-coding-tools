# Change Context: add-the-shared-system-one-decision-helper-fallback-only

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| system-one-decisions.1 | specs/system-one-decisions/spec.md | Package exports and dependency-free import | --- | D4 | packages/system-one-decisions/pyproject.toml, packages/system-one-decisions/src/system_one_decisions/__init__.py | tests/test_package_import.py | --- |
| system-one-decisions.2 | specs/system-one-decisions/spec.md | Decision is a frozen dataclass with a fixed field set | --- | D4 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_decision.py | --- |
| system-one-decisions.3 | specs/system-one-decisions/spec.md | decide() is an unconditional stub with a stable signature | --- | D3 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_decide_stub.py | --- |
| system-one-decisions.4 | specs/system-one-decisions/spec.md | decide_intent() always takes the fallback branch in this item | --- | D1 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_decide_intent.py | --- |
| system-one-decisions.5 | specs/system-one-decisions/spec.md | _route() implements confidence-based routing over a distribution | --- | D1 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_route.py | --- |
| system-one-decisions.6 | specs/system-one-decisions/spec.md | decide_intent records one event through a caller-supplied sink | --- | D2 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_decide_intent.py | --- |
| system-one-decisions.7 | specs/system-one-decisions/spec.md | The package is importable from every declared consumer | --- | --- | skills/pyproject.toml, packages/gen-eval/pyproject.toml, agent-coordinator/pyproject.toml, agent-coordinator/Dockerfile | tests/test_package_import.py, work-packages.yaml verification steps | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Split routing (pure) from acquisition (stubbed) | The four documented checks must be unit-testable with zero network calls | `_route()` (pure) + `decide_intent()` (always-fallback in this item) in `_core.py` | Only defensible design given both constraints hold simultaneously |
| D2 — Caller-supplied event sink | Avoids importing `skills/autopilot`'s state model, preserving the package boundary | `event_sink: Callable[[dict], None] \| None` parameter on `decide_intent()` | Keeps the package importable by consumers that do not carry `skills/autopilot` |
| D3 — `decide()` is an unconditional stub | No live client exists yet; deferred entirely to ri-02 | `decide()` returns `None` unconditionally | Simplest correct behavior until the live client lands |
| D4 — Package layout | Mirrors `packages/code-search`'s proven pyproject.toml shape | `packages/system-one-decisions/{pyproject.toml,src/system_one_decisions/,tests/}` | Consistency with an existing, working repo pattern |

## Coverage Summary

- **Requirements traced**: 7/7
- **Tests mapped**: 7 requirements have at least one test
- **Evidence collected**: 0/7 requirements have pass/fail evidence
- **Gaps identified**: none
- **Deferred items**: none
