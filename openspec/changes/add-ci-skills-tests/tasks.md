# Tasks: add-ci-skills-tests

## 1. Add skills test job to CI

- [x] 1.1 Add `test-skills` job to `.github/workflows/ci.yml`
  **Dependencies**: None
  **Files**: `.github/workflows/ci.yml`

  Add a new `test-skills` job that:
  - Uses `actions/checkout@v4` and `astral-sh/setup-uv@v5` (same pattern as existing jobs)
  - Installs Python 3.12 via `uv python install 3.12`
  - Installs agent-coordinator venv via `uv sync --all-extras` with `working-directory: agent-coordinator`
  - Runs tests from the repo root: `agent-coordinator/.venv/bin/python -m pytest skills/bug-scrub/tests/ skills/fix-scrub/tests/ -v`
  - No `working-directory` default on the job (runs from repo root) to preserve fix-scrub's `importlib` cross-skill path resolution

## 2. Verify

- [x] 2.1 Verify all 341 tests pass locally using the same command the CI job will use
  **Dependencies**: 1.1
  **Files**: (read-only verification, no file changes)

  Run: `agent-coordinator/.venv/bin/python -m pytest skills/bug-scrub/tests/ skills/fix-scrub/tests/ -v`
  Expected: 214 bug-scrub + 127 fix-scrub = 341 tests pass.
