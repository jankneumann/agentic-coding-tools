#!/usr/bin/env python3
"""Deterministic hash of the installed toolkit payload.

The payload is every portable skill directory, every declared shared library
directory and ``install-manifest.json``.  Paths containing a ``tests``,
``__pycache__`` or ``node_modules`` component are skipped (``install.sh`` does
not mirror them).  Entries are ordered by POSIX relative path and each
contributes ``relpath\\0sha256(content)\\n`` to the digest, so the value is the
same for a source ``skills/`` root and for an agent mirror synced from it.
Symlinks are followed so ``--mode symlink`` mirrors hash identically.

Dependency-free (standard library only) so it installs in the consumer layout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

EXCLUDED_COMPONENTS = frozenset({"tests", "__pycache__", "node_modules"})
MANIFEST_NAME = "install-manifest.json"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(directory: Path, prefix: str) -> Iterable[tuple[str, Path]]:
    if not directory.is_dir():
        return
    for path in directory.rglob("*"):
        rel = path.relative_to(directory)
        if EXCLUDED_COMPONENTS.intersection(rel.parts):
            continue
        if path.is_file():
            yield f"{prefix}/{rel.as_posix()}", path


def hash_payload(
    root: Path | str,
    skill_names: Iterable[str],
    shared_libraries: Iterable[str],
) -> str:
    """Return ``sha256:<hex>`` for the payload rooted at ``root``."""
    root = Path(root)
    entries: dict[str, Path] = {}
    for name in sorted(set(skill_names) | set(shared_libraries)):
        for rel, path in _walk(root / name, name):
            entries[rel] = path
    manifest = root / MANIFEST_NAME
    if manifest.is_file():
        entries[MANIFEST_NAME] = manifest

    stream = hashlib.sha256()
    for rel in sorted(entries):
        stream.update(f"{rel}\0{_file_digest(entries[rel])}\n".encode("utf-8"))
    return f"sha256:{stream.hexdigest()}"


def payload_names(manifest_path: Path | str) -> tuple[list[str], list[str]]:
    """Return (portable skill names, shared library names) from a manifest."""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    skills = sorted(
        name for name, meta in data["skills"].items() if meta["distribution"] == "portable"
    )
    return skills, sorted(data["shared_libraries"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the toolkit payload hash.")
    parser.add_argument("--root", required=True, help="skills root or agent mirror root")
    parser.add_argument(
        "--manifest",
        help="install-manifest.json naming the payload (default: <root>/install-manifest.json)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    manifest = Path(args.manifest) if args.manifest else root / MANIFEST_NAME
    try:
        skills, libraries = payload_names(manifest)
    except (OSError, ValueError, KeyError) as exc:
        print(f"payload_hash: cannot read manifest {manifest}: {exc}", file=sys.stderr)
        return 2
    print(hash_payload(root, skills, libraries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
