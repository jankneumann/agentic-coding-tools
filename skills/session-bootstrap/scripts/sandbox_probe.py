#!/usr/bin/env python3
"""Check that the lead-session Bash sandbox refuses what it is configured to refuse.

Run through the harness's Bash tool, so the probe itself is sandboxed:

    python3 skills/session-bootstrap/scripts/sandbox_probe.py

Each check is reported as ``enforced``, ``not_enforced`` or ``not_applicable``.
The paths probed are read from ``sandbox.filesystem.denyRead`` in the project's
``.claude/settings.json``; this file holds no list of its own. Output is the
check, the path and the verdict. Nothing read from a probed path is kept or
printed.

Exit status: 0 when every check is enforced or not applicable, or when the
probe is skipped or the sandbox is disabled; 1 when any check is not enforced;
2 when the settings file cannot be read.

Where the harness already provides isolation (a cloud container), the probe
reports ``skipped`` and attempts nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from shared.environment_profile import detect as _detect
except ModuleNotFoundError:  # shared/ missing from a stripped install
    _detect = None  # type: ignore[assignment]

ENFORCED = "enforced"
NOT_ENFORCED = "not_enforced"
NOT_APPLICABLE = "not_applicable"

_CONNECT_HOST = "github.com"
_CONNECT_PORT = 443


@dataclass(frozen=True)
class Check:
    check: str
    target: str
    verdict: str


@dataclass
class Report:
    status: str
    source: str
    checks: list[Check] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.status == NOT_ENFORCED else 0


def read_path(path: Path) -> None:
    """Attempt a read and discard the result. Raises OSError when refused."""
    if path.is_dir():
        with os.scandir(path) as entries:
            next(entries, None)
    else:
        with path.open("rb") as handle:
            handle.read(1)


def write_path(directory: Path) -> None:
    """Create and remove an empty file. Raises OSError when refused."""
    target = directory / f".sandbox-probe-{os.getpid()}"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    target.unlink()


def connect_host(host: str, port: int) -> None:
    """Open and close a TCP connection. Raises OSError when refused."""
    with socket.create_connection((host, port), timeout=3):
        pass


def _load_sandbox(project_root: Path) -> dict[str, Any]:
    """Project settings overlaid by the checkout-local settings file."""
    settings_dir = project_root / ".claude"
    merged: dict[str, Any] = dict(
        json.loads((settings_dir / "settings.json").read_text(encoding="utf-8")).get("sandbox", {})
    )
    local = settings_dir / "settings.local.json"
    if local.is_file():
        try:
            override = json.loads(local.read_text(encoding="utf-8")).get("sandbox", {})
        except (OSError, json.JSONDecodeError):
            override = {}
        merged.update({k: v for k, v in override.items() if k != "filesystem"})
    return merged


def _resolve(entry: str, project_root: Path, home: Path) -> Path:
    if entry == "~" or entry.startswith("~/"):
        return Path(os.path.normpath(home / entry[2:]))
    path = Path(entry)
    if path.is_absolute():
        return path
    return Path(os.path.normpath(project_root / path))


def _exists(path: Path) -> bool:
    try:
        return os.path.lexists(path)
    except OSError:
        return True  # cannot even stat: let the read attempt decide


def _refused(action: Callable[[], None]) -> bool:
    try:
        action()
    except OSError:
        return True
    return False


def _first_sibling(project_root: Path) -> Path | None:
    try:
        with os.scandir(project_root.parent) as entries:
            names = sorted(e.name for e in entries if e.is_dir(follow_symlinks=False))
    except OSError:
        return None
    for name in names:
        if name != project_root.name:
            return project_root.parent / name
    return None


def run_probe(
    project_root: Path,
    *,
    home: Path | None = None,
    detect: Callable[[], Any] | None = None,
    read: Callable[[Path], None] = read_path,
    write: Callable[[Path], None] = write_path,
    connect: Callable[[str, int], None] = connect_host,
    sibling: Path | None = None,
) -> Report:
    detect = detect or _detect
    profile = detect() if detect is not None else None
    if profile is not None and profile.isolation_provided:
        return Report(status="skipped", source=str(profile.source))
    source = str(profile.source) if profile is not None else "unavailable"

    project_root = Path(os.path.normpath(project_root))
    home = Path(os.path.normpath(home or Path.home()))
    sandbox = _load_sandbox(project_root)
    if not sandbox.get("enabled", False):
        return Report(status="disabled", source=source)

    checks: list[Check] = []

    def record(check: str, target: object, refused: bool | None, *, want_refused: bool = True) -> None:
        if refused is None:
            verdict = NOT_APPLICABLE
        else:
            verdict = ENFORCED if refused == want_refused else NOT_ENFORCED
        checks.append(Check(check=check, target=str(target), verdict=verdict))

    for entry in sandbox.get("filesystem", {}).get("denyRead", []):
        path = _resolve(entry, project_root, home)
        record("deny_read", path, _refused(lambda p=path: read(p)) if _exists(path) else None)

    # The sibling is found before the parent is probed in a real sandbox only
    # if the parent is listable, which is itself the failure being tested for.
    # A sandbox that hides the parent yields no sibling; that check is then
    # covered by the parent's own deny_read verdict.
    other = sibling or _first_sibling(project_root)
    if other is not None:
        record("sibling_read", other, _refused(lambda: read(other)))
    else:
        parent_refused = _refused(lambda: read(project_root.parent))
        record("sibling_read", project_root.parent, True if parent_refused else None)

    record("project_readable", project_root, _refused(lambda: read(project_root)), want_refused=False)
    record("write_outside", home, _refused(lambda: write(home)))
    record(
        "connect",
        f"{_CONNECT_HOST}:{_CONNECT_PORT}",
        _refused(lambda: connect(_CONNECT_HOST, _CONNECT_PORT)),
    )

    failed = any(c.verdict == NOT_ENFORCED for c in checks)
    return Report(status=NOT_ENFORCED if failed else ENFORCED, source=source, checks=checks)


def render(report: Report, *, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(
            {
                "status": report.status,
                "source": report.source,
                "checks": [asdict(c) for c in report.checks],
            },
            indent=2,
        )
    lines = [f"{report.status}\tdetection={report.source}"]
    lines += [f"{c.verdict}\t{c.check}\t{c.target}" for c in report.checks]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()),
    )
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    try:
        report = run_probe(args.project_root)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error\tcannot read project settings: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(render(report, as_json=args.json))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
