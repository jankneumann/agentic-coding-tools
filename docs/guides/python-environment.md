# Python Environment

- **uv for all Python environments**: Use `uv` (not pip, pipenv, or poetry) for dependency management and virtual environments across all Python projects. CI uses `astral-sh/setup-uv@v5`.
- **agent-coordinator**: `cd agent-coordinator && uv sync --all-extras` to install. Venv at `agent-coordinator/.venv`.
- **skills (infrastructure)**: `cd skills && uv sync --all-extras` to install. Venv at `skills/.venv`. Covers worktree, validation, architecture, and other infrastructure skill scripts.
- **Running tools**: Activate the relevant venv first (`source .venv/bin/activate`) or use the venv's Python directly (e.g., `skills/.venv/bin/python -m pytest`).
