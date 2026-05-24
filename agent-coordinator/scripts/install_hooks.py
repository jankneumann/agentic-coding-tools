#!/usr/bin/env python3
"""Install coordinator lifecycle hooks for supported agent CLIs."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

HOOK_SCRIPTS = {
    "print_env": "print_coordinator_env.py",
    "register": "register_agent.py",
    "report": "report_status.py",
    "deregister": "deregister_agent.py",
}


def _command(
    scripts_dir: Path,
    script_name: str,
    *,
    extra_args: str = "",
) -> str:
    command = ["python3", shlex.quote(str(scripts_dir / script_name))]
    if extra_args:
        command.append(extra_args)
    return " ".join(command)


def _command_hook(command: str, timeout: int | None = None) -> dict[str, Any]:
    hook: dict[str, Any] = {"type": "command", "command": command}
    if timeout is not None:
        hook["timeout"] = timeout
    return hook


def _claude_hook_group(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"matcher": "", "hooks": commands}]


def build_hooks(
    *,
    agent: str,
    scripts_dir: Path,
) -> dict[str, Any]:
    """Build the provider-specific hooks mapping."""
    print_env = _command(
        scripts_dir,
        HOOK_SCRIPTS["print_env"],
    )
    register = _command(
        scripts_dir,
        HOOK_SCRIPTS["register"],
    )
    report = _command(
        scripts_dir,
        HOOK_SCRIPTS["report"],
    )

    if agent == "codex":
        return {
            "SessionStart": [
                _command_hook(print_env),
                _command_hook(register),
            ],
            "Stop": [
                _command_hook(report),
            ],
        }

    deregister = _command(
        scripts_dir,
        HOOK_SCRIPTS["deregister"],
    )
    return {
        "SessionStart": _claude_hook_group([
            _command_hook(print_env),
            _command_hook(register),
        ]),
        "Stop": _claude_hook_group([
            _command_hook(report),
        ]),
        "SubagentStop": _claude_hook_group([
            _command_hook(
                _command(
                    scripts_dir,
                    HOOK_SCRIPTS["report"],
                    extra_args="--subagent",
                )
            ),
        ]),
        "SessionEnd": _claude_hook_group([
            _command_hook(deregister),
        ]),
    }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as handle:
        parsed = json.load(handle)
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed


def write_hooks(path: Path, hooks: dict[str, Any]) -> None:
    existing = load_json(path)
    existing["hooks"] = hooks
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, choices=["claude", "codex"])
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--scripts-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--agent-id", default="", help=argparse.SUPPRESS)
    parser.add_argument("--agent-type", default="", help=argparse.SUPPRESS)
    parser.add_argument("--coordination-api-url", default="", help=argparse.SUPPRESS)
    parser.add_argument("--coordination-api-key", default="", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hooks = build_hooks(
        agent=args.agent,
        scripts_dir=args.scripts_dir.resolve(),
    )
    write_hooks(args.target, hooks)
    print(f"Merged {args.agent} hooks into {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
