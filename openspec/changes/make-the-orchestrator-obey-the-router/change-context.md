# Change Context: make-the-orchestrator-obey-the-router (dg-06)

Canonical traceability for dispatch-governance item dg-06.

## Requirement Traceability Matrix

| Req | Requirement | Contract | Design | Tests | Implementation | Status |
|---|---|---|---|---|---|---|
| roadmap-orchestration.1 | Resolve and validate a durable route before each host dispatch; preserve canonical isolation and require ledger-correlated completion | `contracts/routing-dispatch-context.schema.json` | D1-D3 | `test_orchestrator.py` | `orchestrator.py`, `SKILL.md` | in progress |
| roadmap-orchestration.2 | Bound orchestration loops with checkpointed iteration and no-progress state that survives restart | checkpoint schema | D4-D5 | `test_orchestrator.py`, roadmap-runtime tests | `orchestrator.py`, `models.py` | pending |

## Coverage Summary

- Two normative requirements are in scope.
- The single sequential package reflects shared state-machine and checkpoint surfaces.
- dg-07 enforcement and direct vendor SDK execution remain out of scope.
