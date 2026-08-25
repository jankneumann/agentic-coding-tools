"""Shared fixtures for the setup-coordinator entrypoint suite.

The module under test is imported by flat name after inserting the skill's
``scripts/`` directory onto ``sys.path`` — the same convention
``skills/tests/worktree/conftest.py`` uses. This directory deliberately has no
``__init__.py``: an ``__init__.py`` would make the suite a package and shadow
that flat import.

Nothing here may be imported with ``from conftest import ...``. Several sibling
suites ship a ``conftest.py`` and the name resolves to whichever one pytest
loaded first. Everything shared is exposed as a pytest fixture instead.

Every fixture writes only under ``tmp_path`` and points ``HOME`` at a temporary
directory. No test in this suite reads or writes the operator's real home or the
repository's own settings file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / "setup-coordinator" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

ENTRYPOINT = SKILL_SCRIPTS / "setup_coordinator.py"


@pytest.fixture
def entrypoint_path() -> Path:
    """Absolute path to the entrypoint file, for reload-based tests."""
    return ENTRYPOINT


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty home directory that ``Path.home()`` and ``~`` both resolve to."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("USERPROFILE", raising=False)
    return home


@pytest.fixture
def fake_path_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty directory that is the entire ``PATH`` for the test."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", str(bindir))
    return bindir


@pytest.fixture
def make_executable(fake_path_dir: Path):
    """Create a fake CLI on the faked ``PATH``."""

    def _make(name: str) -> Path:
        target = fake_path_dir / name
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
        return target

    return _make


@pytest.fixture
def agents_yaml(tmp_path: Path):
    """Write an agents.yaml roster and return its path.

    Accepts a mapping of ``agent_id -> agent config`` so each test states the
    roster shape it depends on rather than inheriting the live one.
    """

    def _write(agents: dict, *, name: str = "agents.yaml") -> Path:
        import yaml

        target = tmp_path / name
        target.write_text(yaml.safe_dump({"agents": agents}), encoding="utf-8")
        return target

    return _write


@pytest.fixture
def local_agent():
    """Build one ``<vendor>-local`` roster entry."""

    def _entry(command: str, *, agent_type: str = "generic") -> dict:
        return {"type": agent_type, "cli": {"command": command}}

    return _entry


@pytest.fixture
def settings_file(tmp_path: Path):
    """Write a ``.claude/settings.local.json`` under an explicit root.

    Returns ``(root, settings_path)``. The caller supplies the exact text so a
    test can assert on formatting the writer must preserve.
    """

    def _write(text: str, *, root_name: str = "repo") -> tuple[Path, Path]:
        root = tmp_path / root_name
        target = root / ".claude" / "settings.local.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return root, target

    return _write


@pytest.fixture
def settings_json(settings_file):
    """Write a settings file from a Python object using canonical-ish JSON."""

    def _write(data: dict, *, indent: int = 2, root_name: str = "repo") -> tuple[Path, Path]:
        return settings_file(
            json.dumps(data, indent=indent) + "\n",
            root_name=root_name,
        )

    return _write
