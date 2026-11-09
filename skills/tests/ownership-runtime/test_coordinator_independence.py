"""The resolver works from the git checkout alone (design D7, spec: Coordinator Independence)."""

from __future__ import annotations

import ast
import os
import re
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from check_owners import check
from owners import load_ownership

MakeRepo = Callable[..., Path]

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "ownership-runtime" / "scripts"
JAN = {"display_name": "Jan Neumann", "github": "jankneumann"}
KIM = {"display_name": "Kim Lee", "github": "kimlee"}


@pytest.fixture(autouse=True)
def unreachable_coordinator(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Point the coordinator at a closed port and fail on any socket connection."""
    monkeypatch.setenv("COORDINATION_API_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("COORDINATION_TRANSPORT", raising=False)
    attempts: list[str] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        attempts.append(repr(args))
        raise AssertionError(f"network connection attempted: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    return attempts


def test_resolution_with_the_coordinator_unreachable(
    make_repo: MakeRepo, unreachable_coordinator: list[str]
) -> None:
    repo = make_repo(
        humans={"jan": JAN, "kim": KIM},
        owners={
            "schema_version": 1,
            "default_owner": "jan",
            "assignments": {
                "capabilities": {"agent-identity": {"owners": ["kim"]}},
                "paths": {"docs/**": {"owners": ["kim"]}},
            },
        },
        specs=["agent-identity"],
    )
    ctx = load_ownership(repo)
    assert ctx.resolve_capability("agent-identity").owner_ids == ("kim",)
    assert ctx.resolve_path("docs/a.md").owner_ids == ("kim",)
    assert ctx.resolve_roadmap_item("r", "i").owner_ids == ("jan",)
    assert check(repo)["findings"] == []
    assert unreachable_coordinator == []


def test_solo_resolution_with_the_coordinator_unreachable(
    make_repo: MakeRepo, unreachable_coordinator: list[str]
) -> None:
    repo = make_repo(git_email="dev@example.org")
    assert load_ownership(repo).resolve_path("a").owner_ids == ("git:dev@example.org",)
    assert unreachable_coordinator == []


def test_cli_runs_with_the_coordinator_unreachable(make_repo: MakeRepo) -> None:
    repo = make_repo(humans={"jan": JAN}, owners={"schema_version": 1, "default_owner": "jan"})
    env = {**os.environ, "COORDINATION_API_URL": "http://127.0.0.1:9"}
    done = subprocess.run(
        [sys.executable, str(SCRIPTS / "check_owners.py"), "--repo-root", str(repo), "--strict"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def _script_sources() -> list[Path]:
    return sorted(SCRIPTS.glob("*.py"))


def test_scripts_exist() -> None:
    names = {p.name for p in _script_sources()}
    assert {"owners.py", "principals.py", "check_owners.py"} <= names


@pytest.mark.parametrize("path", _script_sources(), ids=lambda p: p.name)
def test_no_private_coordinator_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] != "src", f"{path.name}: from {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "src", f"{path.name}: import {alias.name}"


_COORDINATOR_SYS_PATH = re.compile(
    r"(?:sys\.path|parents?\[[^]]+\])[^\n]*agent-coordinator"
    r"|agent-coordinator[^\n]*(?:sys\.path|parents?\[[^]]+\])"
)


@pytest.mark.parametrize("path", _script_sources(), ids=lambda p: p.name)
def test_no_path_walk_into_the_coordinator(path: Path) -> None:
    assert not _COORDINATOR_SYS_PATH.search(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _script_sources(), ids=lambda p: p.name)
def test_no_network_libraries_imported(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    banned = {"socket", "requests", "httpx", "urllib3", "aiohttp", "http"}
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for name in names:
            assert name.split(".")[0] not in banned, f"{path.name} imports {name}"
