#!/usr/bin/env python3
"""install_stop_hook.py — wire the Langfuse Stop hook into .claude/settings.json.

Adds (idempotently) an entry to the Stop hook array in either the project-scoped
.claude/settings.json (default) or the user-scoped ~/.claude/settings.json
(--user flag). The entry invokes skills/langfuse/scripts/run_stop_hook.sh, which
in turn resolves credentials and runs agent-coordinator/scripts/langfuse_hook.py.

Other Stop hook entries (e.g. session-bootstrap report_status) are preserved.

Usage:
    python3 skills/langfuse/scripts/install_stop_hook.py            # project-scoped
    python3 skills/langfuse/scripts/install_stop_hook.py --user     # user-scoped
    python3 skills/langfuse/scripts/install_stop_hook.py --remove   # uninstall
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WRAPPER_REL = "skills/langfuse/scripts/run_stop_hook.sh"
HOOK_COMMAND = f'bash "$CLAUDE_PROJECT_DIR"/{WRAPPER_REL}'


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def upsert(settings: dict) -> bool:
    hooks = settings.setdefault("hooks", {})
    stop = hooks.setdefault("Stop", [])
    new_hook = {"type": "command", "command": HOOK_COMMAND, "timeout": 30}

    for group in stop:
        for hook in group.get("hooks", []):
            if hook.get("command", "").endswith(WRAPPER_REL):
                hook.update(new_hook)
                return False

    for group in stop:
        if group.get("matcher", "") == "":
            group.setdefault("hooks", []).append(new_hook)
            return True

    stop.append({"matcher": "", "hooks": [new_hook]})
    return True


def remove(settings: dict) -> bool:
    stop = settings.get("hooks", {}).get("Stop", [])
    changed = False
    for group in list(stop):
        group["hooks"] = [
            h for h in group.get("hooks", [])
            if not h.get("command", "").endswith(WRAPPER_REL)
        ]
        if not group["hooks"]:
            stop.remove(group)
            changed = True
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", action="store_true",
                        help="Modify ~/.claude/settings.json instead of project-scoped file")
    parser.add_argument("--remove", action="store_true",
                        help="Remove the Langfuse Stop hook entry")
    args = parser.parse_args()

    if args.user:
        target = Path.home() / ".claude" / "settings.json"
    else:
        target = repo_root() / ".claude" / "settings.json"

    settings = load(target)

    if args.remove:
        changed = remove(settings)
        action = "Removed" if changed else "Not present in"
    else:
        added = upsert(settings)
        action = "Added to" if added else "Already present in"

    save(target, settings)
    print(f"{action} {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
