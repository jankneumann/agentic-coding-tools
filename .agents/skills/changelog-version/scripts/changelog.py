#!/usr/bin/env python3
"""Changelog generator and semantic version bump advisor.

Analyzes git history using conventional commit conventions to:
- Categorize changes into Keep a Changelog sections
- Suggest semantic version bumps (MAJOR, MINOR, PATCH)
- Update VERSION and CHANGELOG.md files

Usage:
    python changelog.py analyze [--repo-root PATH] [--since REF]
    python changelog.py apply   [--repo-root PATH] [--bump LEVEL] [--date DATE]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum
from pathlib import Path


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class BumpLevel(IntEnum):
    PATCH = 0
    MINOR = 1
    MAJOR = 2

    def __str__(self) -> str:
        return self.name


# Mapping from conventional commit type to (changelog section, bump level)
COMMIT_TYPE_MAP: dict[str, tuple[str, BumpLevel]] = {
    "feat": ("Added", BumpLevel.MINOR),
    "fix": ("Fixed", BumpLevel.PATCH),
    "docs": ("Documentation", BumpLevel.PATCH),
    "refactor": ("Changed", BumpLevel.PATCH),
    "chore": ("Changed", BumpLevel.PATCH),
    "test": ("Changed", BumpLevel.PATCH),
    "perf": ("Changed", BumpLevel.PATCH),
    "style": ("Changed", BumpLevel.PATCH),
    "ci": ("Changed", BumpLevel.PATCH),
    "build": ("Changed", BumpLevel.PATCH),
    "archive": ("Changed", BumpLevel.PATCH),
}

# Keep a Changelog section ordering
SECTION_ORDER = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Documentation"]


@dataclass
class ParsedCommit:
    hash: str
    type: str
    scope: str
    description: str
    breaking: bool = False
    raw: str = ""


@dataclass
class AnalysisResult:
    current_version: str
    suggested_bump: BumpLevel
    next_version: str
    sections: dict[str, list[str]] = field(default_factory=dict)
    commits: list[ParsedCommit] = field(default_factory=list)
    breaking_commits: list[ParsedCommit] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git(args: list[str], repo_root: Path) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def get_commits_since(repo_root: Path, since: str | None) -> list[str]:
    """Return list of 'hash subject' lines from git log."""
    cmd = ["log", "--oneline", "--no-merges"]
    if since:
        cmd.append(f"{since}..HEAD")
    return git(cmd, repo_root).splitlines()


def get_commit_body(repo_root: Path, commit_hash: str) -> str:
    """Return the full body of a commit for BREAKING CHANGE detection."""
    return git(["log", "-1", "--format=%b", commit_hash], repo_root)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Matches: type(scope)!: description  or  type!: description  or  type: description
CONVENTIONAL_RE = re.compile(
    r"^(?P<hash>[0-9a-f]+)\s+"
    r"(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^)]*)\))?"
    r"(?P<breaking>!)?"
    r":\s+"
    r"(?P<desc>.+)$"
)


def parse_commit_line(line: str, repo_root: Path) -> ParsedCommit | None:
    """Parse a single git log --oneline line into a ParsedCommit."""
    m = CONVENTIONAL_RE.match(line)
    if not m:
        return None

    commit_hash = m.group("hash")
    breaking = bool(m.group("breaking"))

    # Also check body for BREAKING CHANGE footer
    if not breaking:
        body = get_commit_body(repo_root, commit_hash)
        if "BREAKING CHANGE" in body or "BREAKING-CHANGE" in body:
            breaking = True

    return ParsedCommit(
        hash=commit_hash,
        type=m.group("type"),
        scope=m.group("scope") or "",
        description=m.group("desc"),
        breaking=breaking,
        raw=line,
    )


# ---------------------------------------------------------------------------
# Version arithmetic
# ---------------------------------------------------------------------------

def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse 'MAJOR.MINOR.PATCH' into a tuple."""
    parts = version_str.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version_str!r} (expected MAJOR.MINOR.PATCH)")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(current: str, level: BumpLevel) -> str:
    """Compute the next version string."""
    major, minor, patch = parse_version(current)
    if level == BumpLevel.MAJOR:
        return f"{major + 1}.0.0"
    elif level == BumpLevel.MINOR:
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze(repo_root: Path, since: str | None) -> AnalysisResult:
    """Analyze git history and produce changelog sections + version suggestion."""
    version_file = repo_root / "VERSION"
    if version_file.exists():
        current_version = version_file.read_text().strip()
    else:
        current_version = "0.0.0"

    raw_lines = get_commits_since(repo_root, since)
    if not raw_lines:
        return AnalysisResult(
            current_version=current_version,
            suggested_bump=BumpLevel.PATCH,
            next_version=bump_version(current_version, BumpLevel.PATCH),
        )

    commits: list[ParsedCommit] = []
    for line in raw_lines:
        parsed = parse_commit_line(line, repo_root)
        if parsed:
            commits.append(parsed)

    # Build sections and determine bump
    sections: dict[str, list[str]] = {}
    max_bump = BumpLevel.PATCH
    breaking_commits: list[ParsedCommit] = []

    for c in commits:
        if c.breaking:
            max_bump = BumpLevel.MAJOR
            breaking_commits.append(c)

        type_info = COMMIT_TYPE_MAP.get(c.type)
        if type_info:
            section, bump = type_info
            if not c.breaking and bump > max_bump:
                max_bump = bump
            scope_prefix = f"**{c.scope}**: " if c.scope else ""
            entry = f"- {scope_prefix}{c.description} (`{c.hash}`)"
            sections.setdefault(section, []).append(entry)

    next_version = bump_version(current_version, max_bump)

    return AnalysisResult(
        current_version=current_version,
        suggested_bump=max_bump,
        next_version=next_version,
        sections=sections,
        commits=commits,
        breaking_commits=breaking_commits,
    )


def format_changelog_section(result: AnalysisResult, version: str, release_date: str) -> str:
    """Format analyzed commits into a Keep a Changelog version section."""
    lines = [f"## [{version}] - {release_date}", ""]
    for section in SECTION_ORDER:
        entries = result.sections.get(section)
        if entries:
            lines.append(f"### {section}")
            lines.extend(entries)
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_version_bump(repo_root: Path, bump: BumpLevel, release_date: str | None) -> dict:
    """Update VERSION and CHANGELOG.md with the new version."""
    if release_date is None:
        release_date = date.today().isoformat()

    result = analyze(repo_root, since=None)

    # Determine the actual bump (allow override)
    next_version = bump_version(result.current_version, bump)
    new_section = format_changelog_section(result, next_version, release_date)

    # Update VERSION
    version_file = repo_root / "VERSION"
    version_file.write_text(next_version + "\n")

    # Update CHANGELOG.md
    changelog_file = repo_root / "CHANGELOG.md"
    if changelog_file.exists():
        content = changelog_file.read_text()
        # Insert new version section after [Unreleased]
        unreleased_marker = "## [Unreleased]"
        if unreleased_marker in content:
            content = content.replace(
                unreleased_marker,
                f"{unreleased_marker}\n\n{new_section}",
            )
        else:
            # Append after the header
            header_end = content.find("\n\n", content.find("# Changelog"))
            if header_end != -1:
                content = (
                    content[: header_end + 2]
                    + f"{unreleased_marker}\n\n{new_section}\n"
                    + content[header_end + 2:]
                )
        changelog_file.write_text(content)
    else:
        changelog_file.write_text(
            "# Changelog\n\n"
            "All notable changes to this project will be documented in this file.\n\n"
            "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),\n"
            "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n\n"
            f"## [Unreleased]\n\n{new_section}\n"
        )

    return {
        "previous_version": result.current_version,
        "new_version": next_version,
        "bump_level": str(bump),
        "release_date": release_date,
        "changelog_file": str(changelog_file),
        "version_file": str(version_file),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace) -> None:
    """Handle the 'analyze' subcommand."""
    repo_root = Path(args.repo_root).resolve()
    result = analyze(repo_root, args.since)

    if args.json:
        output = {
            "current_version": result.current_version,
            "suggested_bump": str(result.suggested_bump),
            "next_version": result.next_version,
            "total_commits": len(result.commits),
            "breaking_changes": len(result.breaking_commits),
            "sections": {k: len(v) for k, v in result.sections.items()},
        }
        print(json.dumps(output, indent=2))
        return

    print(f"Current version: {result.current_version}")
    print(f"Commits analyzed: {len(result.commits)}")
    print(f"Suggested bump: {result.suggested_bump}")
    print(f"Next version: {result.next_version}")

    if result.breaking_commits:
        print(f"\n⚠ Breaking changes ({len(result.breaking_commits)}):")
        for c in result.breaking_commits:
            print(f"  - {c.raw}")

    print()
    for section in SECTION_ORDER:
        entries = result.sections.get(section)
        if entries:
            print(f"### {section}")
            for entry in entries:
                print(f"  {entry}")
            print()


def cmd_apply(args: argparse.Namespace) -> None:
    """Handle the 'apply' subcommand."""
    repo_root = Path(args.repo_root).resolve()
    bump = BumpLevel[args.bump.upper()]
    info = apply_version_bump(repo_root, bump, args.date)

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"Version bumped: {info['previous_version']} → {info['new_version']} ({info['bump_level']})")
        print(f"Updated: {info['version_file']}")
        print(f"Updated: {info['changelog_file']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Changelog generator and semantic version bump advisor",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze commits and suggest version bump")
    analyze_parser.add_argument("--since", default=None, help="Git ref to start analysis from")

    # apply
    apply_parser = subparsers.add_parser("apply", help="Apply version bump to VERSION and CHANGELOG.md")
    apply_parser.add_argument(
        "--bump",
        required=True,
        choices=["major", "minor", "patch"],
        help="Bump level to apply",
    )
    apply_parser.add_argument(
        "--date",
        default=None,
        help="Release date in YYYY-MM-DD format (default: today)",
    )

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "apply":
        cmd_apply(args)


if __name__ == "__main__":
    main()
