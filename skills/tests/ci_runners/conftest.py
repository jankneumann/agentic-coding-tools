"""Shared fixtures for the CI runner lane tests.

Tests read the promoted ``.github/`` copies only; they never pin
``openspec/changes/<id>/`` (archival moves that directory).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def manifest(repo_root: Path) -> dict[str, Any]:
    """A fresh (mutable) copy of the lane manifest per test."""
    data = yaml.safe_load((repo_root / ".github" / "runner-lanes.yaml").read_text())
    return copy.deepcopy(data)


@pytest.fixture(scope="session")
def load_workflow(repo_root: Path):
    """Return ``load_workflow(name)`` -> parsed workflow dict.

    PyYAML parses the bare key ``on`` as boolean ``True``; it is normalised to
    the string ``"on"`` so tests can address triggers by name.
    """

    def _load(name: str) -> dict[str, Any]:
        data = yaml.safe_load((repo_root / ".github" / "workflows" / name).read_text())
        if True in data:
            data["on"] = data.pop(True)
        return data

    return _load
