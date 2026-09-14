"""Install-manifest contract for candidate-work runtime consumers."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = REPO_ROOT / "skills" / "install-manifest.json"


def test_candidate_work_consumers_declare_the_shared_runtime() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dependencies = manifest["cross_skill_dependencies"]

    for skill in (
        "bug-scrub",
        "explore-feature",
        "improve-harness",
        "plan-roadmap",
        "prioritize-proposals",
    ):
        assert "shared" in dependencies.get(skill, []), skill
