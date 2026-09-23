from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_to_local_worktree_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Core worktree tests are local unless a scenario explicitly says cloud."""
    monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
