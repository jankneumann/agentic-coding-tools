# Validation Report — define-evidence-ledger-schema-with-immutable-facts

Run inline (no sub-agent adapter), cloud container (`AGENT_EXECUTION_ENV=cloud`), 2026-10-12.

| Check | Result |
| --- | --- |
| `openspec validate define-evidence-ledger-schema-with-immutable-facts --strict` | pass |
| `pytest tests/evidence-ledger` | 66 passed |
| `pytest tests/ci_coverage tests/openspec_paths tests/install_sh/test_install_manifest.py` | pass |
| `ruff check .` (skills) | pass |
| `ruff format --check` (new files) | pass |
| `mypy --strict evidence-ledger/scripts/evidence_ledger.py` | pass |
| Full `skills` suite (shared testpaths) | 5997 passed, 47 skipped, 51 failed (all environmental; see below) |

## Environmental failures (not caused by this change)

None of the 51 failing tests reference a file this change touches. Each failure has an
environmental cause:

| Tests | Count | Cause |
| --- | --- | --- |
| `worktree/scripts/tests/test_worktree.py`, `test_merge_worktrees.py` | 29 | Cloud harness short-circuits worktree operations (`AGENT_EXECUTION_ENV=cloud`). |
| `tests/validate-feature/test_validation_worktree.py` | 7 | Same: ephemeral validation worktrees. |
| `tests/cleanup-feature/test_submodule_teardown.py` | 6 | Same: worktree teardown with submodules. |
| `coordination-bridge/scripts/tests/test_generated_bindings.py` | 6 | `datamodel_code_generator` is not installed in `skills/.venv`. |
| `tests/project-context-refresh/*` (shared-checkout refusal) | 2 | Running from inside a `.git-worktrees/` checkout. |
| `refresh-architecture/scripts/tests/test_interpreter_resolution.py` | 1 | Interpreter and environment layout. |

Verdict: **passed**.
