# Change Context: write-durable-state-artifacts-guide

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Design Decision | Test(s) | Files Changed | Contract Ref | Evidence |
|---|---|---|---|---|---|---|---|
| skill-workflow.state-artifacts-inventory | `specs/skill-workflow/spec.md` | Five artifact classes expose path, holder, writer, authority, consumers, and missing/stale behavior. | D1, D2 | `skills/tests/state-artifacts/test_state_artifacts_guide.py` | `docs/guides/state-artifacts.md` | --- | Focused GREEN: 16 passed |
| skill-workflow.state-artifacts-authority | `specs/skill-workflow/spec.md` | Canonical loop/checkpoint state wins conflicts with advisory records or projections. | D2, D3 | `skills/tests/state-artifacts/test_state_artifacts_guide.py` | `docs/guides/state-artifacts.md` | --- | Focused GREEN: 16 passed |
| skill-workflow.state-artifacts-rehydration | `specs/skill-workflow/spec.md` | Bootstrap discovery is separated from ordered canonical verification. | D2, D3 | `skills/tests/state-artifacts/test_state_artifacts_guide.py` | `docs/guides/state-artifacts.md`, `skills/supervise/SKILL.md` | --- | Focused GREEN: 16 passed |
| skill-workflow.state-artifacts-missing | `specs/skill-workflow/spec.md` | Missing canonical state degrades rather than reconstructing truth. | D2, D3 | `skills/tests/state-artifacts/test_state_artifacts_guide.py` | `docs/guides/state-artifacts.md`, `skills/supervise/SKILL.md` | --- | Focused GREEN: 16 passed |
| skill-workflow.state-artifacts-links | `specs/skill-workflow/spec.md` | Relevant skill sources reference the guide and supervise follows its order. | D1, D4 | `skills/tests/state-artifacts/test_state_artifacts_guide.py` | `docs/guides/documentation.md`, six canonical `skills/*/SKILL.md` files, `docs/decisions/skill-workflow.md` | --- | Reference checks and install portability pass |
| skill-workflow.state-artifacts-mirrors | `specs/skill-workflow/spec.md` | Changed runtime mirrors are byte-identical. | D4 | `skills/tests/state-artifacts/test_state_artifacts_guide.py` | Installed `.agents/skills/` and `.claude/skills/` mirrors (ignored runtime copies) | --- | Local installed run compares 12 files; fresh CI runs 10 structural tests and skips six mirror cases while `install.sh --check` validates payload portability |
| skill-workflow.state-artifacts-ci-discovery | `specs/skill-workflow/spec.md` | The structural drift guard is collected by default CI. | D4 | `skills/tests/ci_coverage/test_ci_test_coverage.py` | `skills/pyproject.toml` | --- | Focused suite plus CI coverage guard pass |

## Design Decision Trace

| Decision | Implemented By | Verification |
|---|---|---|
| D1 - One normative inventory | Canonical guide plus thin skill links | Inventory/link structural tests |
| D2 - Question-scoped authority | Artifact table and conflict rules | Inventory/authority structural tests |
| D3 - Separate bootstrap from verification | Eight-step guide and supervise order | Rehydration-order structural test |
| D4 - Structural drift tests | Focused pytest plus mirror parity | RED evidence and 16-test GREEN result |
| D5 - No hand-authored ADR | Generated decision index is allowlisted as a derived projection | Scope review and context checkpoint |

## Implementation Evidence

- RED: `validation/red-state-artifacts.md` records 9 failed, 6 passed before product documentation.
- GREEN: focused suite passed 16 tests after guide, references, supervise/design alignment, and mirror installation.
- Package context: `context-checkpoints/wp-state-artifacts-docs.json`; declaration status `declared` for `documentation` and `semantic_code`.
- Context checkpoint caveat: checkpoint status is degraded by pre-existing repository-wide pending OpenSpec projections and an unconfigured semantic index, not by a ri-10 scope or contract failure.

## Coverage Summary

- Requirements traced: 6
- Tests mapped: 6
- Evidence collected: 6
- Gaps: complete validation matrix pending
- Deferred: none
