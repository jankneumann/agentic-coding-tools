"""The three .agentic-toolkit artifacts must stay registered in the state-artifacts guide."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GUIDE = REPO_ROOT / "docs" / "guides" / "state-artifacts.md"
SKILLS_GUIDE = REPO_ROOT / "docs" / "guides" / "skills.md"
SKILLS_ROOT = REPO_ROOT / "skills"
PRUNED_DIRS = {"tests", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
PROJECTION_READERS = {
    "improve-harness/scripts/analyze_failures.py",
    "improve-harness/scripts/export_shared_learnings.py",
}
# Naming the file, or importing the functions that read or merge it, both count as reading.
PROJECTION_MARKERS = ("learnings.jsonl", "load_shared_learnings", "merge_shared_learnings")

ARTIFACTS = {
    ".agentic-toolkit/stamp.json": "install.sh",
    ".agentic-toolkit/config.json": "humans",
    ".agentic-toolkit/learnings.jsonl": "export_shared_learnings.py",
}


def _row_for(path: str) -> list[str]:
    for line in GUIDE.read_text(encoding="utf-8").splitlines():
        if line.startswith("|") and f"`<consumer-root>/{path}`" in line:
            # Strip the leading/trailing pipe and split the six table columns.
            return [cell.strip() for cell in line.strip().strip("|").split("|")]
    pytest.fail(f"{path} is not registered as a row in {GUIDE}")


@pytest.mark.parametrize(("path", "writer"), ARTIFACTS.items())
def test_artifact_row_names_writer_and_missing_behavior(path: str, writer: str) -> None:
    cells = _row_for(path)
    assert len(cells) == 6, "row must fill all six inventory columns"
    artifact, holder, canonical_writer, authority, consumers, missing = cells
    assert path in holder
    assert writer in canonical_writer
    assert authority and consumers
    assert missing, "missing/stale behavior column must not be empty"
    assert "Absent" in missing or "Missing" in missing


def test_learnings_projection_never_feeds_canonical_state() -> None:
    cells = _row_for(".agentic-toolkit/learnings.jsonl")
    assert "never derive loop state, checkpoint state or trust posture" in cells[5].lower()


def test_learnings_projection_is_read_only_by_improve_harness() -> None:
    """Only the exporter and the read-only analysis read the projection.

    No loop-state, checkpoint, trust-posture or installer code names the file
    or imports its loader/merger, so the projection cannot feed canonical state.
    """
    readers: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(SKILLS_ROOT):
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIRS]
        for name in filenames:
            if not name.endswith((".py", ".sh")):
                continue
            path = Path(dirpath) / name
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(marker in text for marker in PROJECTION_MARKERS):
                readers.add(path.relative_to(SKILLS_ROOT).as_posix())
    assert readers == PROJECTION_READERS


def test_skills_guide_documents_stamp_check_and_opt_in() -> None:
    text = SKILLS_GUIDE.read_text(encoding="utf-8")
    for needle in (
        ".agentic-toolkit/stamp.json",
        "--check",
        "checkout drift",
        "runtime drift",
        "unpinned",
        ".agentic-toolkit/config.json",
        "shared_learnings",
    ):
        assert needle in text, f"docs/guides/skills.md must mention {needle!r}"
