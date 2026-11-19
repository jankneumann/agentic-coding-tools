"""Every irreversible command class keeps a gate that survives auto-allow.

With ``sandbox.autoAllowBashIfSandboxed`` on, "not on the allow list" no
longer means "prompts". A command is gated only if a deny rule, a
content-scoped ask rule, or ``irreversible_guard.check`` stops it (design D6).
Gate recording is included as a class of its own (design D10): before this
change ``gate-answer`` prompted only because no allow rule matched it.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SETTINGS = _REPO / ".claude" / "settings.json"
_HOOK = _REPO / "skills" / "session-bootstrap" / "scripts" / "hooks" / "irreversible_guard.py"

_spec = importlib.util.spec_from_file_location("irreversible_guard", _HOOK)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)

IRREVERSIBLE: dict[str, tuple[str, ...]] = {
    "force-push": (
        "git push --force origin main",
        "git push -f origin main",
        "git push --force-with-lease origin feature",
        "git push origin +main",
    ),
    "deletion": (
        "rm -rf build",
        "git clean -fdx",
        "git reset --hard HEAD~1",
        "git branch -D feature",
        "git push origin --delete feature",
        "gh repo delete owner/repo --yes",
        "find . -name x -delete",
    ),
    "merge": (
        "gh pr merge 12 --squash",
        "gh pr merge 12 --admin",
        "gh api -X PUT repos/o/r/pulls/1/merge",
    ),
    "deploy": (
        "railway up",
        "railway deploy",
        "railway redeploy",
        "docker push registry/img",
        "kubectl apply -f x.yaml",
    ),
    "migration": (
        "alembic upgrade head",
        "alembic downgrade -1",
        "uv run alembic upgrade head",
        "uv run --project agent-coordinator alembic upgrade head",
        "python -m alembic upgrade head",
        "psql -c 'DROP TABLE x'",
    ),
    "secret-write": (
        "railway variable set FOO=bar",
        "railway variables --set FOO=bar",
        "gh secret set FOO",
        "bao kv put secret/x a=b",
        "vault kv put secret/x a=b",
    ),
    "gate-recording": (
        "python3 skills/autopilot/scripts/runner.py gate-answer x --gate plan --decision approved",
        'python3 "$CLAUDE_PROJECT_DIR"/.claude/skills/autopilot/scripts/runner.py gate-answer x',
        "python3 skills/supervise/scripts/cycle_state.py --repo-root . gate-answer --roadmap r"
        " --gate roadmap_approval --decision approved",
    ),
}

# Sandboxed development commands that must stay promptless; a gate matching
# one of these would bring the interruptions back.
NOT_GATED = (
    "git status",
    "uv run --project skills pytest -q",
    "skills/.venv/bin/python -m pytest skills/tests/session-bootstrap -q",
    "python3 skills/autopilot/scripts/runner.py gate-check x --gate plan",
    "python3 skills/autopilot/scripts/runner.py relayed-gate-answer x",
    "git branch -d merged-feature",
)

_CASES = [(cls, cmd) for cls, cmds in IRREVERSIBLE.items() for cmd in cmds]


@pytest.fixture(scope="module")
def settings() -> dict:
    return json.loads(_SETTINGS.read_text(encoding="utf-8"))


def _bash_patterns(rules: list[str]) -> list[str]:
    out = []
    for rule in rules:
        match = re.fullmatch(r"Bash\((.*)\)", rule, flags=re.DOTALL)
        if match:
            out.append(match.group(1))
    return out


def _matches(command: str, pattern: str) -> bool:
    """Approximate the harness rule matcher: ``*`` spans any text.

    A trailing `` *`` also matches the bare command, as ``Bash(ls *)`` does.
    """
    if pattern in ("", "*"):
        return False  # a bare rule is not content-scoped
    if fnmatch.fnmatchcase(command, pattern):
        return True
    return pattern.endswith(" *") and command == pattern[:-2]


def _gate(command: str, settings: dict) -> str | None:
    permissions = settings["permissions"]
    for pattern in _bash_patterns(permissions["deny"]):
        if _matches(command, pattern):
            return f"deny rule {pattern!r}"
    for pattern in _bash_patterns(permissions["ask"]):
        if _matches(command, pattern):
            return f"ask rule {pattern!r}"
    verdict = guard.check(command)
    if verdict is not None and verdict.decision in ("deny", "ask"):
        return f"guard {verdict.decision}"
    return None


@pytest.mark.parametrize(("cls", "command"), _CASES)
def test_irreversible_command_is_gated(settings: dict, cls: str, command: str) -> None:
    assert _gate(command, settings) is not None, f"{cls}: nothing gates {command!r}"


@pytest.mark.parametrize("command", NOT_GATED)
def test_development_command_is_not_gated(settings: dict, command: str) -> None:
    assert _gate(command, settings) is None


def test_every_class_has_representatives() -> None:
    for cls in ("force-push", "deletion", "merge", "deploy", "migration", "secret-write"):
        assert IRREVERSIBLE[cls], cls


def test_guard_hook_is_registered_and_fails_closed(settings: dict) -> None:
    entries = [
        hook
        for group in settings["hooks"]["PreToolUse"]
        if group.get("matcher") == "Bash"
        for hook in group["hooks"]
        if "irreversible_guard.py" in hook.get("command", "")
    ]
    assert len(entries) == 1
    assert entries[0].get("onFailure") == "block"


def test_no_setting_skips_the_hook(settings: dict) -> None:
    """A command gated only by the hook must not be exempt from hooks."""
    assert settings.get("disableAllHooks", False) is False
    for group in settings["hooks"]["PreToolUse"]:
        if group.get("matcher") == "Bash":
            for hook in group["hooks"]:
                assert "if" not in hook, "a conditional hook entry can skip the guard"
