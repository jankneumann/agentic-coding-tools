#!/usr/bin/env python3
"""Report metadata of a vendor CLI's credential paths. Never their content.

Usage:
    observe_vendor_auth.py <vendor>
    observe_vendor_auth.py <vendor> --watch -- <command> [args...]

Without --watch, prints one line per candidate path: type, permission bits,
size and modification time. With --watch, takes that snapshot, runs the
command, takes it again and prints which paths changed. That answers whether a
vendor's token refresh writes to disk.

Only lstat() and directory listing are used. No credential file is opened, so
the output cannot contain a token. Hosts are not captured here; the guide at
docs/guides/vendor-auth-audit.md gives the manual procedure.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    """A path a vendor CLI may keep credentials in.

    `relative` is joined to the directory named by `env_var` when that variable
    is set, and to `home / default_dir` otherwise.
    """

    default_dir: str
    relative: str
    env_var: str | None = None


# Must list the same vendors as docs/guides/vendor-auth-audit.yaml (tested).
CANDIDATE_PATHS: dict[str, tuple[Candidate, ...]] = {
    "claude": (
        Candidate(".claude", ".credentials.json", "CLAUDE_CONFIG_DIR"),
        Candidate("", ".claude.json"),
    ),
    "codex": (Candidate(".codex", "auth.json", "CODEX_HOME"),),
    "antigravity": (
        Candidate(".gemini/antigravity-cli", ""),
        Candidate(".gemini/config", ""),
        Candidate(".gemini", "oauth_creds.json"),
    ),
    "grok": (
        Candidate(".grok", "auth.json", "GROK_HOME"),
        Candidate(".grok", "mcp_credentials.json", "GROK_HOME"),
        Candidate(".grok", "auth.json.lock", "GROK_HOME"),
    ),
}


@dataclass(frozen=True)
class Entry:
    path: Path
    kind: str  # absent | file | dir | symlink | other
    mode: str = ""
    size: int = 0
    mtime_ns: int = 0


def format_mode(st_mode: int) -> str:
    """Permission bits only, as four octal digits."""
    return f"{stat.S_IMODE(st_mode):04o}"


def _format_time(mtime_ns: int) -> str:
    moment = datetime.fromtimestamp(mtime_ns // 1_000_000_000, tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve(candidate: Candidate, home: Path) -> Path:
    override = os.environ.get(candidate.env_var) if candidate.env_var else None
    base = Path(override) if override else home / candidate.default_dir
    return base / candidate.relative if candidate.relative else base


def _entry(path: Path) -> Entry:
    try:
        info = os.lstat(path)
    except OSError:
        return Entry(path=path, kind="absent")
    if stat.S_ISLNK(info.st_mode):
        kind = "symlink"
    elif stat.S_ISDIR(info.st_mode):
        kind = "dir"
    elif stat.S_ISREG(info.st_mode):
        kind = "file"
    else:
        kind = "other"
    return Entry(path, kind, format_mode(info.st_mode), info.st_size, info.st_mtime_ns)


def snapshot(vendor: str, home: Path) -> dict[Path, Entry]:
    """Metadata for each candidate path, and for the entries of a candidate directory.

    A directory's own modification time changes only when an entry is added or
    removed, so its direct children are listed to catch a rewrite in place.
    """
    entries: dict[Path, Entry] = {}
    for candidate in CANDIDATE_PATHS[vendor]:
        path = _resolve(candidate, home)
        entry = _entry(path)
        entries[path] = entry
        if entry.kind != "dir":
            continue
        try:
            children = sorted(os.listdir(path))
        except OSError:
            continue
        for name in children:
            entries[path / name] = _entry(path / name)
    return entries


def changed_paths(before: dict[Path, Entry], after: dict[Path, Entry]) -> list[Path]:
    absent = Entry(path=Path(), kind="absent")
    changed = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path, absent)
        new = after.get(path, absent)
        if (old.kind, old.mode, old.size, old.mtime_ns) != (
            new.kind,
            new.mode,
            new.size,
            new.mtime_ns,
        ):
            changed.append(path)
    return changed


def _print_snapshot(entries: dict[Path, Entry]) -> None:
    for path, entry in entries.items():
        if entry.kind == "absent":
            print(f"absent   {path}")
            continue
        print(
            f"{entry.kind:<8} {path}  mode={entry.mode} size={entry.size} "
            f"mtime={_format_time(entry.mtime_ns)}"
        )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in args:
        split = args.index("--")
        args, command = args[:split], args[split + 1 :]

    parser = argparse.ArgumentParser(
        description="Report metadata of a vendor CLI's credential paths, never content."
    )
    parser.add_argument("vendor", help=f"one of: {', '.join(sorted(CANDIDATE_PATHS))}")
    parser.add_argument("--home", type=Path, default=Path.home(), help="home directory to inspect")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="run the command given after -- and report which paths it changed",
    )
    try:
        options = parser.parse_args(args)
    except SystemExit as exit_:
        return int(exit_.code or 0)

    if options.vendor not in CANDIDATE_PATHS:
        known = ", ".join(sorted(CANDIDATE_PATHS))
        print(f"unknown vendor {options.vendor!r}; known vendors: {known}", file=sys.stderr)
        return 2
    if options.watch and not command:
        print("--watch needs a command after --", file=sys.stderr)
        return 2
    if command and not options.watch:
        print("a command after -- is only run with --watch", file=sys.stderr)
        return 2

    before = snapshot(options.vendor, options.home)
    _print_snapshot(before)
    if not options.watch:
        return 0

    status = subprocess.run(command, check=False).returncode
    after = snapshot(options.vendor, options.home)
    changed = changed_paths(before, after)
    print("--- after command ---")
    _print_snapshot(after)
    if not changed:
        print("changed: none")
    for path in changed:
        print(f"changed: {path}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
