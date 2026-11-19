"""The project-shared settings enable the Bash sandbox for the lead session.

These tests read the real ``.claude/settings.json``. They pin the contract of
``sandbox-the-interactive-lead-session`` (design D1-D5, D9): the sandbox is on
with auto-allow, it is not required, credential paths and the parent of the
checkout are unreadable, outward commands leave the sandbox, and the allow
list no longer approves a general reader or interpreter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SETTINGS = _REPO / ".claude" / "settings.json"

# Entries of permissions.allow before this change. The spec requires the list
# to shrink below half of this.
ALLOW_COUNT_BEFORE = 100

# Every host the sandbox may reach. Adding a host means editing this list in
# the same commit, which is the review point.
RECORDED_ALLOWED_DOMAINS = frozenset(
    {
        "pypi.org",
        "files.pythonhosted.org",
        "registry.npmjs.org",
        "coord.rotkohl.ai",
    }
)

DENIED_CREDENTIAL_PATHS = (
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.netrc",
    "~/.kube",
    "~/.docker",
    "~/.config/gh",
    "~/.config/gcloud",
    "~/.claude/.credentials.json",
    "~/.codex",
)

EXCLUDED_COMMANDS = ("git push", "git fetch", "git pull", "gh", "railway", "docker")

READER_OR_INTERPRETER_WORDS = frozenset(
    {
        "cat", "head", "tail", "grep", "rg", "find", "sed", "jq", "sort",
        "uniq", "wc", "ls", "python", "python3", "uv", "pytest", "bash", "sh",
    }
)  # fmt: skip


@pytest.fixture(scope="module")
def settings() -> dict:
    return json.loads(_SETTINGS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sandbox(settings: dict) -> dict:
    assert "sandbox" in settings, ".claude/settings.json has no sandbox block"
    return settings["sandbox"]


def _bash_patterns(rules: list[str]) -> list[str]:
    out = []
    for rule in rules:
        match = re.fullmatch(r"Bash\((.*)\)", rule, flags=re.DOTALL)
        if match:
            out.append(match.group(1))
    return out


# --- Requirement: Lead Session Bash Sandbox Configuration -------------------


def test_sandbox_and_auto_allow_are_on(sandbox: dict) -> None:
    assert sandbox.get("enabled") is True
    assert sandbox.get("autoAllowBashIfSandboxed") is True


def test_sandbox_is_not_required(sandbox: dict) -> None:
    """A host without bubblewrap/socat, and the cloud container, still work."""
    assert sandbox.get("failIfUnavailable", False) is False
    assert sandbox.get("allowUnsandboxedCommands", True) is True


def test_toolchain_caches_are_writable(sandbox: dict) -> None:
    allow_write = sandbox["filesystem"]["allowWrite"]
    assert "~/.cache/uv" in allow_write, "Linux uv cache"
    assert "~/Library/Caches/uv" in allow_write, "macOS uv cache"


def test_local_binding_is_allowed(sandbox: dict) -> None:
    assert sandbox["network"].get("allowLocalBinding") is True


# --- Requirement: Sandboxed Commands Cannot Read Credentials or Siblings ----


@pytest.mark.parametrize("path", DENIED_CREDENTIAL_PATHS)
def test_credential_location_is_denied(sandbox: dict, path: str) -> None:
    assert path in sandbox["filesystem"]["denyRead"]


def test_parent_is_denied_and_project_is_allowed(sandbox: dict) -> None:
    filesystem = sandbox["filesystem"]
    assert ".." in filesystem["denyRead"]
    assert "." in filesystem["allowRead"]


def test_whole_config_and_claude_dirs_are_not_denied(sandbox: dict) -> None:
    """uv and git read ~/.config; skills read transcripts under ~/.claude."""
    deny_read = sandbox["filesystem"]["denyRead"]
    assert "~/.config" not in deny_read
    assert "~/.claude" not in deny_read


# --- Requirement: Outward Commands Run Outside the Sandbox ------------------


@pytest.mark.parametrize("command", EXCLUDED_COMMANDS)
def test_outward_command_is_excluded(sandbox: dict, command: str) -> None:
    assert f"{command} *" in sandbox["excludedCommands"]


def test_git_hosts_are_not_reachable(sandbox: dict) -> None:
    for domain in sandbox["network"]["allowedDomains"]:
        bare = domain.lstrip("*.").lower()
        assert bare != "github.com" and not bare.endswith(".github.com"), domain
        assert "github" not in bare, domain


def test_allowed_domains_are_recorded(sandbox: dict) -> None:
    domains = set(sandbox["network"]["allowedDomains"])
    assert domains, "an empty allowlist would make uv sync prompt"
    assert domains <= RECORDED_ALLOWED_DOMAINS, domains - RECORDED_ALLOWED_DOMAINS


# --- Requirement: Allow List Grants No General Reader or Interpreter --------


def test_no_reader_or_interpreter_is_allowed(settings: dict) -> None:
    offenders = []
    for pattern in _bash_patterns(settings["permissions"]["allow"]):
        first = pattern.split()[0].strip("\"'") if pattern.split() else ""
        if first in READER_OR_INTERPRETER_WORDS or first.endswith(
            ("/python", "/python3", "/pytest")
        ):
            offenders.append(pattern)
    assert offenders == []


def test_allow_list_is_less_than_half(settings: dict) -> None:
    assert len(settings["permissions"]["allow"]) < ALLOW_COUNT_BEFORE / 2


def test_fetch_and_pull_stay_promptless(settings: dict) -> None:
    allow = settings["permissions"]["allow"]
    assert "Bash(git fetch *)" in allow
    assert "Bash(git pull *)" in allow


def test_kept_rules_are_still_present(settings: dict) -> None:
    """Excluded commands rely on these; removing them would add prompts."""
    allow = settings["permissions"]["allow"]
    for rule in (
        "Bash(git status)",
        "Bash(git commit *)",
        "Bash(git push origin openspec/*)",
        "Bash(git push -u origin claude/*)",
        "WebFetch(domain:api.github.com)",
    ):
        assert rule in allow


def test_ask_rules_are_content_scoped(settings: dict) -> None:
    ask = settings["permissions"]["ask"]
    assert "Bash" not in ask
    assert "Bash(*)" not in ask
