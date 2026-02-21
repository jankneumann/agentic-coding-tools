#!/usr/bin/env python3
"""Detect repository security-review profile(s) from project signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROFILE_SIGNAL_FILES: dict[str, tuple[str, ...]] = {
    "python": (
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "setup.py",
        "Pipfile",
        "poetry.lock",
    ),
    "node": (
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    ),
    "java": (
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
    ),
    "docker-api": (
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "openapi.yaml",
        "openapi.yml",
        "swagger.yaml",
        "swagger.yml",
    ),
}


def _walk_with_depth(root: Path, max_depth: int = 4) -> list[Path]:
    """Collect files under root with bounded recursion depth."""
    files: list[Path] = []
    root_depth = len(root.parts)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if len(path.parts) - root_depth > max_depth:
            continue
        files.append(path)
    return files


def detect_profiles(repo: Path) -> dict[str, object]:
    """Detect profiles and confidence from known manifest/config signals."""
    files = _walk_with_depth(repo)
    by_name: dict[str, list[str]] = {}
    for file_path in files:
        by_name.setdefault(file_path.name, []).append(str(file_path.relative_to(repo)))

    detected: list[str] = []
    profile_signals: dict[str, list[str]] = {}
    all_signals: list[str] = []

    for profile, names in PROFILE_SIGNAL_FILES.items():
        hits: list[str] = []
        for name in names:
            hits.extend(by_name.get(name, []))
        if hits:
            detected.append(profile)
            deduped = sorted(set(hits))
            profile_signals[profile] = deduped
            all_signals.extend(deduped)

    profiles: list[str]
    primary_profile: str
    confidence: str

    if not detected:
        profiles = ["generic"]
        primary_profile = "generic"
        confidence = "low"
    elif len(detected) == 1:
        profile = detected[0]
        profiles = [profile]
        primary_profile = profile
        signal_count = len(profile_signals.get(profile, []))
        confidence = "high" if signal_count >= 2 else "med"
    else:
        profiles = sorted(set(detected + ["mixed"]))
        primary_profile = "mixed"
        confidence = "high" if len(set(all_signals)) >= 3 else "med"

    return {
        "primary_profile": primary_profile,
        "profiles": profiles,
        "confidence": confidence,
        "signals": sorted(set(all_signals)),
        "profile_signals": profile_signals,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to inspect (default: current directory)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repository path does not exist or is not a directory: {repo}")

    result = detect_profiles(repo)
    print(json.dumps(result, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
