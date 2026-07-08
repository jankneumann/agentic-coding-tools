"""One-shot migration: move openspec/changes/prioritized-proposals.{md,json}
into the new openspec/priorities/2026-05-04-legacy/ entry.

Idempotent: re-running after a successful migration is a no-op. Refuses to
clobber an existing migrated entry — the operator must resolve a collision
manually (this is a one-shot, not a recurring sync).

Design decision: D6 (legacy file migration + header allowance).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

LEGACY_RUN_NAME = "2026-05-04-legacy"
SOURCE_BASENAME = "prioritized-proposals"
SOURCE_DIR_REL = "openspec/changes"
DEST_DIR_REL = f"openspec/priorities/{LEGACY_RUN_NAME}"


@dataclass(frozen=True)
class MigrationResult:
    moved: list[tuple[str, str]] = field(default_factory=list)
    skipped_reason: str | None = None


def migrate_legacy(repo_root: Path) -> MigrationResult:
    """Move the stale legacy report files into the new priorities tree.

    Returns the list of `(src_rel, dst_rel)` pairs that were actually moved,
    or `skipped_reason` if nothing was moved.
    """
    src_dir = repo_root / SOURCE_DIR_REL
    dst_dir = repo_root / DEST_DIR_REL

    src_md = src_dir / f"{SOURCE_BASENAME}.md"
    src_json = src_dir / f"{SOURCE_BASENAME}.json"

    if not src_md.exists() and not src_json.exists():
        return MigrationResult(moved=[], skipped_reason="no_source")

    # Refuse to overwrite an already-migrated entry — collision is operator-resolved.
    if dst_dir.exists() and any(dst_dir.iterdir()):
        return MigrationResult(moved=[], skipped_reason="already_migrated")

    dst_dir.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[str, str]] = []

    if src_md.exists():
        dst_md = dst_dir / "report.md"
        shutil.move(str(src_md), str(dst_md))
        moved.append((f"{SOURCE_DIR_REL}/{SOURCE_BASENAME}.md", f"{DEST_DIR_REL}/report.md"))

    if src_json.exists():
        dst_json = dst_dir / "report.json"
        shutil.move(str(src_json), str(dst_json))
        moved.append((f"{SOURCE_DIR_REL}/{SOURCE_BASENAME}.json", f"{DEST_DIR_REL}/report.json"))

    return MigrationResult(moved=moved)


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    args = p.parse_args()
    result = migrate_legacy(Path(args.repo_root))
    if result.skipped_reason:
        print(f"skipped: {result.skipped_reason}")
        return 0
    for src, dst in result.moved:
        print(f"moved: {src} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
