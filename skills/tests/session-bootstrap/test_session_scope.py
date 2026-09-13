"""Tests for skills/session-bootstrap/scripts/hooks/session_scope.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "session-bootstrap" / "scripts" / "hooks" / "session_scope.py"
)


@pytest.fixture(scope="module")
def scope_module() -> Any:
    spec = importlib.util.spec_from_file_location("session_scope_under_test",
                                                  _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean_identity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_ID", raising=False)
    monkeypatch.delenv("AGENT_ID", raising=False)


def test_session_key_prefers_payload_session_id(
    scope_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_ID", "env-session")
    monkeypatch.setenv("AGENT_ID", "env-agent")
    assert scope_module.session_key({"session_id": "payload-session"}) == \
        "payload-session"


def test_session_key_env_fallbacks(
    scope_module: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_ID", "env-agent")
    assert scope_module.session_key({}) == "env-agent"
    monkeypatch.setenv("SESSION_ID", "env-session")
    assert scope_module.session_key({"session_id": ""}) == "env-session"


def test_session_key_hashes_transcript_before_unknown(scope_module: Any) -> None:
    a = scope_module.session_key({"transcript_path": "/t/a.jsonl"})
    b = scope_module.session_key({"transcript_path": "/t/b.jsonl"})
    assert a.startswith("transcript-") and a != b
    assert scope_module.session_key({}) == "unknown"


def test_session_key_is_filesystem_safe(scope_module: Any) -> None:
    key = scope_module.session_key({"session_id": "../../etc/pass wd"})
    assert "/" not in key and " " not in key


def test_owning_root_prefers_most_specific(scope_module: Any) -> None:
    main = Path("/repo")
    nested = Path("/repo/.git-worktrees/x")
    roots = [main, nested]
    assert scope_module.owning_root(Path("/repo/skills"), roots) == main
    assert scope_module.owning_root(nested / "openspec", roots) == nested
    assert scope_module.owning_root(Path("/elsewhere"), roots) is None


def test_load_session_scope_collects_transcript_cwds(
    scope_module: Any, tmp_path: Path,
) -> None:
    transcript = tmp_path / "t.jsonl"
    rows = [
        {"cwd": "/repo", "message": {"role": "user", "content": "hi"}},
        {"cwd": "/repo/.git-worktrees/x/skills"},
        # A cwd serialized inside a string is conversation content, not a
        # working directory of this session.
        {"message": {"role": "user",
                     "content": json.dumps({"cwd": "/someone/else"})}},
        "not an object",
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in rows)
                          + "not json\n")
    scope = scope_module.load_session_scope(
        {"transcript_path": str(transcript), "cwd": "/start"},
    )
    assert scope.cwds == {
        Path("/start"), Path("/repo"), Path("/repo/.git-worktrees/x/skills"),
    }


def test_load_session_scope_survives_missing_transcript(
    scope_module: Any, tmp_path: Path,
) -> None:
    scope = scope_module.load_session_scope(
        {"transcript_path": str(tmp_path / "missing.jsonl")},
        fallback_cwd=tmp_path,
    )
    assert scope.cwds == {tmp_path}
    assert scope.text == ""
