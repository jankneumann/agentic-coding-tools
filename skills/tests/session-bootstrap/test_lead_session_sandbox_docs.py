"""Guidance for the lead-session sandbox agrees with the settings file.

``CLAUDE.md`` tells an agent how to write Bash commands; the guide tells an
operator how to install, verify and switch off the sandbox. Both are checked
against the real ``.claude/settings.json`` so they cannot drift from it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SETTINGS = _REPO / ".claude" / "settings.json"
_CLAUDE_MD = _REPO / "CLAUDE.md"
_GUIDE = _REPO / "docs" / "guides" / "lead-session-sandbox.md"
_SECTION_HEADING = "### Write Bash commands that permission rules can match"


@pytest.fixture(scope="module")
def settings() -> dict:
    return json.loads(_SETTINGS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def section() -> str:
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    assert _SECTION_HEADING in text
    body = text.split(_SECTION_HEADING, 1)[1]
    return re.split(r"\n#{1,3} ", body, maxsplit=1)[0]


@pytest.fixture(scope="module")
def guide() -> str:
    assert _GUIDE.is_file(), "docs/guides/lead-session-sandbox.md is missing"
    return _GUIDE.read_text(encoding="utf-8")


# --- Scenario: Claude-specific guidance matches the settings ----------------


def test_section_says_sandboxed_commands_need_no_allow_rule(section: str) -> None:
    flat = " ".join(section.split())
    assert "sandbox" in flat.lower()
    assert "need no allow rule" in flat


def test_section_names_every_excluded_command(settings: dict, section: str) -> None:
    for pattern in settings["sandbox"]["excludedCommands"]:
        name = pattern.removesuffix(" *")
        assert f"`{name}`" in section, name


def test_section_relies_on_no_removed_allow_rule(settings: dict, section: str) -> None:
    """Any ``Bash(...)`` rule the section cites must exist in the settings."""
    permissions = settings["permissions"]
    known = set(permissions["allow"]) | set(permissions["ask"]) | set(permissions["deny"])
    cited = set(re.findall(r"`(Bash\([^`]*\))`", section))
    assert cited <= known, cited - known


def test_section_points_to_the_guide(section: str) -> None:
    assert "docs/guides/lead-session-sandbox.md" in section


# --- Scenario: Guide covers prerequisites and rollback ----------------------


def test_guide_names_linux_prerequisites(guide: str) -> None:
    assert "bubblewrap" in guide
    assert "socat" in guide


def test_guide_gives_the_probe_command(guide: str) -> None:
    assert "skills/session-bootstrap/scripts/sandbox_probe.py" in guide
    assert (_REPO / "skills" / "session-bootstrap" / "scripts" / "sandbox_probe.py").is_file()


def test_guide_gives_the_rollback_setting(guide: str) -> None:
    assert ".claude/settings.local.json" in guide
    blocks = re.findall(r"```json\n(.*?)```", guide, flags=re.DOTALL)
    assert any(json.loads(block) == {"sandbox": {"enabled": False}} for block in blocks)


def test_guide_has_the_host_checklist(guide: str) -> None:
    for command in (
        "uv run --project skills pytest -q",
        "git status",
        "alembic --help",
        "git push origin main",
    ):
        assert command in guide, command


def test_guide_lists_every_probe_verdict(guide: str) -> None:
    for word in ("enforced", "not_enforced", "not_applicable", "skipped", "disabled"):
        assert f"`{word}`" in guide, word


def test_guide_is_indexed() -> None:
    index = (_REPO / "docs" / "guides" / "documentation.md").read_text(encoding="utf-8")
    assert "lead-session-sandbox.md" in index
