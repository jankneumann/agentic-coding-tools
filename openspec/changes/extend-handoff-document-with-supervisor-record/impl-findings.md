# Implementation Findings

## Iteration 1

<!-- Date: 2026-08-31 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | bug | medium | Adding `supervisor_record` before `created_at` changed the positional `HandoffDocument` constructor ABI. | Moved the new field after `created_at` and added a positional compatibility regression test. |
| 2 | UX | medium | The coordinator help example produced a supervisor record missing required schema sections. | Replaced it with a complete minimal v1 record and added an AST-based example contract test. |
| 3 | workflow | low | The OpenAPI contract promised byte-identical JSONB round-tripping although PostgreSQL JSONB normalizes representation. | Synchronized both contract copies on structural equality after JSON decoding. |
| 4 | workflow | high | Supervisor schema tests loaded contracts from the active change directory and would fail after cleanup archives it. | Pointed both consumers at canonical `openspec/schemas/` paths and added an archival-path guard. |
| 5 | edge-case | medium | Rehydration omitted `Degraded: handoff` when both durable sources were absent or when a newer mirror superseded a stale handoff. | Added source-aware prior selection and explicit degradation reporting for both paths. |
| 6 | edge-case | medium | Sanitization could turn required decision or stub fields into schema-invalid empty strings, while future schema versions could be silently rewritten as v1. | Sanitized before required-field checks, validated final records against canonical schemas, and rejected unsupported versions without overwrite. |
| 7 | bug | medium | A symlinked mirror destination could overwrite a file outside the repository write audit. | Rejected symlinked destination components and switched mirror persistence to an atomic same-directory replace. |

### Quality Checks

- Focused coordinator handoff tests: pass — 30 passed.
- Feature-adjacent skills tests: pass — 121 passed.
- Ruff (all changed Python surfaces): pass.
- Mypy `--strict` (changed coordinator implementation): pass — 2 source files, no issues.
- OpenSpec strict validation: pass.
- Broad coordinator suite: 2,403 passed, 88 skipped, 7 ambient failures (unavailable local PostgreSQL and baseline runtime configuration/policy assumptions); no supervisor-record failures.
- Broad skills suite: collection blocked by 36 pre-existing flat-module import collisions (`models`, `runner`, `cli`); targeted package suites provide the usable signal.

### Spec Drift

None detected. The approved behavior remains unchanged; both OpenAPI copies received a wording correction from byte equality to the specified structural equality.

---

## Summary

- Total iterations: 1
- Total findings addressed: 7
- Remaining findings: none within this change
- Termination reason: threshold met

## Validation Fix 1

<!-- Date: 2026-08-31 -->

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 8 | workflow | critical | Generated `.agents` and `.claude` supervise skill mirrors were stale. | Ran the canonical installer and proved exact equality for `SKILL.md` and `cycle_state.py` in both runtime trees. |
| 9 | workflow | high | The active Session Continuity delta copied stale `database_unavailable` wording that contradicted the established public `rpc_failed:` behavior and the proposal's compatibility promise. | Preserved runtime behavior and existing tests; corrected the active delta to require the stable prefix plus diagnostic type/message. |
| 10 | correctness | high | Migration 034 and the RPC round-trip had not been exercised against PostgreSQL. | Started the pinned ParadeDB image with isolated rootless Podman, applied 000–033 then 034 with `ON_ERROR_STOP`, verified unique RPC signatures, and passed the 4-test live suite. |
| 11 | workflow | high | Integration acceptance made unrelated repository-wide collection/configuration failures conjunctive with feature correctness. | Refined proposal, design D9, tasks, and work-package verification to require all changed-surface and live-database gates while retaining broad suites as explicit diagnostics. |

No changed-surface finding was deferred or reclassified. The repository-wide failures
remain recorded in the validation report and are outside this change's approved write scope.
