"""Tests for merge_worktrees.py cloud-mode short-circuit.

Covers spec scenarios:
- worktree-isolation.6 (cloud merge short-circuits with guidance)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import merge_worktrees  # noqa: E402


class TestMergeCloudShortCircuit:
    def test_merge_exits_0_under_cloud_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Cloud merge MUST NOT invoke git merge or read registry."""
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        # Spy: if merge_packages is called, the test fails (it would try
        # to read the registry and invoke git merge).
        called: list[str] = []

        def spy_merge_packages(**kwargs: object) -> dict:
            called.append("merge_packages")
            return {"success": False}

        monkeypatch.setattr(merge_worktrees, "merge_packages", spy_merge_packages)

        rc = merge_worktrees.main(["feature-x", "wp-backend", "wp-frontend"])
        assert rc == 0
        assert called == [], "merge_packages must not be called in cloud mode"

        err = capsys.readouterr().err
        assert "skipped" in err
        assert "isolation_provided=true" in err
        assert "PR-based integration" in err

    def test_merge_json_output_is_structured_skip(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """JSON output under cloud mode reports structured skip metadata."""
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")

        monkeypatch.setattr(
            merge_worktrees,
            "merge_packages",
            lambda **_: pytest.fail("merge_packages must not run in cloud mode"),
        )

        rc = merge_worktrees.main(
            ["feature-x", "wp-backend", "--json"]
        )
        assert rc == 0

        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["success"] is True
        assert payload["skipped"] is True
        assert payload["reason"] == "isolation_provided"
        assert payload["source"] == "env_var"
        assert payload["change_id"] == "feature-x"
        assert payload["package_ids"] == ["wp-backend"]


class TestMergeLocalBackwardCompat:
    def test_merge_proceeds_normally_under_local_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AGENT_EXECUTION_ENV=local does NOT short-circuit merge."""
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("CODESPACES", raising=False)

        called: list[str] = []

        def spy_merge_packages(**kwargs: object) -> dict:
            called.append(str(kwargs.get("change_id")))
            return {"success": True}  # minimal — format_human is mocked

        monkeypatch.setattr(merge_worktrees, "merge_packages", spy_merge_packages)
        # Avoid running real git commands or needing the full result shape
        monkeypatch.setattr(merge_worktrees, "resolve_repo_root", lambda: ".")
        monkeypatch.setattr(merge_worktrees, "format_human", lambda r: "OK")

        rc = merge_worktrees.main(["feature-y", "wp-backend"])
        assert rc == 0
        assert called == ["feature-y"], "merge_packages should run in local mode"
