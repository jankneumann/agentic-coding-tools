"""Shared fixtures (owned by wp-contracts; design D1 "Test tree ownership").

Only ``schema_validator`` and ``fixture_project`` live here. Stage packages keep
their own helpers inside their ``test_<stage>*.py`` modules and their data under
``tests/fixtures/<stage>/``; they never edit this file.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from test_oracle_audit.records import validate

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def schema_validator() -> Callable[..., None]:
    """``validate(instance, schema_name="stage-record")``; raises on violation."""

    def _validate(instance: Mapping[str, Any], schema_name: str = "stage-record") -> None:
        validate(instance, schema_name)

    return _validate


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "HOME": str(cwd),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )


@pytest.fixture
def fixture_project(tmp_path: Path) -> Callable[[str], Path]:
    """Copy ``tests/fixtures/<name>`` into a temp dir, ``git init`` it, commit once.

    Returns the copy's root. The committed fixture tree is never modified.
    """

    def _make(name: str) -> Path:
        src = FIXTURES / name
        if not src.is_dir():
            raise FileNotFoundError(f"no fixture directory {src}")
        dest = tmp_path / name
        shutil.copytree(src, dest)
        _git(dest, "init", "-q", "-b", "main")
        _git(dest, "add", "-A")
        _git(dest, "commit", "-q", "-m", "fixture: initial commit")
        return dest

    return _make
