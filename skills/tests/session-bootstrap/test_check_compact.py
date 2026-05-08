"""Tests for skills/session-bootstrap/scripts/hooks/check_compact.py.

The Stop hook is invoked as a subprocess so we exercise the real stdin/stdout
contract (Claude Code calls these scripts via shell). Each test creates an
isolated $HOME (for the flag file and SDK cache) and an isolated cwd (for
the handoff-glob scan) using tmp_path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HOOK = (
    Path(__file__).resolve().parents[2]
    / "session-bootstrap" / "scripts" / "hooks" / "check_compact.py"
)


def _run_hook(
    *,
    hook_input: dict,
    home: Path,
    cwd: Path,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    # Strip ANTHROPIC_API_KEY so the proxy path is exercised by default.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("CLAUDE_COMPACT_THRESHOLD_PCT", None)
    env.pop("CLAUDE_CONTEXT_LIMIT", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )


def _write_transcript(path: Path, message_chars: int) -> None:
    """Write a transcript JSONL whose total content length is approximately
    message_chars (split across one large user message). Token estimate via
    proxy = chars // 4."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "x" * message_chars
    row = {"message": {"role": "user", "content": body}}
    path.write_text(json.dumps(row) + "\n")


def _write_handoff(cwd: Path, change_id: str, phase: str, n: int = 1) -> Path:
    """Create a handoff JSON in the local-fallback envelope shape."""
    handoff_dir = cwd / "openspec" / "changes" / change_id / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    target = handoff_dir / f"{phase}-{n}.json"
    target.write_text(json.dumps({
        "schema_version": 1,
        "written_at": "2026-05-08T00:00:00+00:00",
        "coordinator_error": {"error_type": "unreachable", "message": "test"},
        "payload": {
            "agent_name": "claude-opus-4-7",
            "session_id": None,
            "summary": "Test phase complete.",
            "next_steps": ["Continue with next thing"],
        },
    }))
    return target


@pytest.fixture
def isolated(tmp_path: Path) -> tuple[Path, Path]:
    """Yields (home, cwd). Both are scratch directories; setting HOME isolates
    the flag file and SDK cache, and cwd isolates the handoff-glob scan."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    return home, cwd


def test_missing_transcript_no_block(isolated: tuple[Path, Path]) -> None:
    home, cwd = isolated
    result = _run_hook(
        hook_input={"transcript_path": str(cwd / "nonexistent.jsonl")},
        home=home,
        cwd=cwd,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_below_threshold_no_block(isolated: tuple[Path, Path]) -> None:
    home, cwd = isolated
    transcript = cwd / "session.jsonl"
    # 1000 chars = 250 tokens via proxy. Limit 200_000, threshold 70% = 140_000.
    _write_transcript(transcript, 1000)
    result = _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_above_threshold_blocks(isolated: tuple[Path, Path]) -> None:
    home, cwd = isolated
    transcript = cwd / "session.jsonl"
    # Set a small limit so the proxy easily crosses threshold.
    # 4000 chars = 1000 tokens. Limit=1000, threshold=70% → trips at 700.
    _write_transcript(transcript, 4000)
    result = _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
        env_extra={
            "CLAUDE_CONTEXT_LIMIT": "1000",
            "CLAUDE_COMPACT_THRESHOLD_PCT": "70",
        },
    )
    assert result.returncode == 0
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"
    assert "compact" in decision["reason"].lower()
    assert "Context window" in decision["reason"]


def test_phase_boundary_blocks_when_below_threshold(
    isolated: tuple[Path, Path],
) -> None:
    home, cwd = isolated
    transcript = cwd / "session.jsonl"
    _write_transcript(transcript, 1000)  # well below threshold
    _write_handoff(cwd, "test-change", "implementation")
    result = _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
    )
    assert result.returncode == 0
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"
    assert "implementation" in decision["reason"]
    assert "decomposition" in decision["reason"].lower()


def test_old_phase_boundary_does_not_block(isolated: tuple[Path, Path]) -> None:
    home, cwd = isolated
    transcript = cwd / "session.jsonl"
    _write_transcript(transcript, 1000)
    handoff = _write_handoff(cwd, "old-change", "implementation")
    # Backdate the handoff to 10 minutes ago — outside the 60s window.
    old_mtime = time.time() - 600
    os.utime(handoff, (old_mtime, old_mtime))
    result = _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_flag_prevents_reblock(isolated: tuple[Path, Path]) -> None:
    home, cwd = isolated
    # Pre-create the flag for AGENT_ID=test-agent
    flag = home / ".claude" / "compact-pending-test-agent.flag"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()
    transcript = cwd / "session.jsonl"
    _write_transcript(transcript, 4000)  # would otherwise trip
    result = _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
        env_extra={
            "AGENT_ID": "test-agent",
            "CLAUDE_CONTEXT_LIMIT": "1000",
            "CLAUDE_COMPACT_THRESHOLD_PCT": "70",
        },
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_agent_id_isolation(isolated: tuple[Path, Path]) -> None:
    """Agent A's flag must not suppress Agent B's threshold trip."""
    home, cwd = isolated
    flag_a = home / ".claude" / "compact-pending-agent-a.flag"
    flag_a.parent.mkdir(parents=True, exist_ok=True)
    flag_a.touch()
    transcript = cwd / "session.jsonl"
    _write_transcript(transcript, 4000)
    # Agent B has no flag, so the threshold trip should still fire.
    result = _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
        env_extra={
            "AGENT_ID": "agent-b",
            "CLAUDE_CONTEXT_LIMIT": "1000",
            "CLAUDE_COMPACT_THRESHOLD_PCT": "70",
        },
    )
    assert result.returncode == 0
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"
    # And agent-b's own flag was created (not agent-a's modified).
    assert (home / ".claude" / "compact-pending-agent-b.flag").exists()


def test_threshold_trip_creates_flag(isolated: tuple[Path, Path]) -> None:
    home, cwd = isolated
    transcript = cwd / "session.jsonl"
    _write_transcript(transcript, 4000)
    _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
        env_extra={
            "AGENT_ID": "flagger",
            "CLAUDE_CONTEXT_LIMIT": "1000",
            "CLAUDE_COMPACT_THRESHOLD_PCT": "70",
        },
    )
    assert (home / ".claude" / "compact-pending-flagger.flag").exists()


def test_malformed_transcript_does_not_crash(
    isolated: tuple[Path, Path],
) -> None:
    home, cwd = isolated
    transcript = cwd / "session.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("not json\n{}\n{\"message\":{\"role\":\"user\","
                          "\"content\":\"hi\"}}\n")
    result = _run_hook(
        hook_input={"transcript_path": str(transcript)},
        home=home,
        cwd=cwd,
    )
    assert result.returncode == 0
