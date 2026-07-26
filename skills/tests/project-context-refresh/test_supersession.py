"""Supersession guard tests (task 2.3).

Prove ``add-update-documentation-skill`` has been fully neutralized: no
executable task or work package remains, and its spec delta no longer directs
the standalone hook / cleanup / post-merge / validate-feature / auto-commit
lifecycle. This change is named as the replacement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUPERSEDED = _REPO_ROOT / "openspec/changes/add-update-documentation-skill"
_REPLACEMENT_ID = "add-deterministic-context-producer-checks"


def test_superseded_change_still_present():
    assert _SUPERSEDED.is_dir(), "historical change directory must be retained"


def test_no_executable_tasks_remain():
    tasks = (_SUPERSEDED / "tasks.md").read_text(encoding="utf-8")
    # No unchecked task checkboxes.
    assert not re.search(r"(?m)^\s*-\s*\[\s*\]", tasks)
    assert _REPLACEMENT_ID in tasks


def test_no_work_packages_remain():
    wp_text = (_SUPERSEDED / "work-packages.yaml").read_text(encoding="utf-8")
    assert _REPLACEMENT_ID in wp_text
    if yaml is not None:
        data = yaml.safe_load(wp_text)
        assert not data.get("packages"), "no dispatchable work package may remain"


def test_proposal_marks_superseded_and_names_replacement():
    proposal = (_SUPERSEDED / "proposal.md").read_text(encoding="utf-8")
    lowered = proposal.lower()
    assert "superseded" in lowered
    assert _REPLACEMENT_ID in proposal


def test_spec_delta_has_no_lifecycle_directives():
    spec = (_SUPERSEDED / "specs/skill-workflow/spec.md").read_text(encoding="utf-8")
    lowered = spec.lower()
    # The neutralized delta must not direct any standalone lifecycle wiring.
    for forbidden in ("pre-commit", "post-merge", "auto-commit", "githooks"):
        assert forbidden not in lowered, f"lifecycle directive {forbidden!r} still present"
    assert _REPLACEMENT_ID in spec


@pytest.mark.parametrize("artifact", ["proposal.md", "tasks.md", "work-packages.yaml", "design.md"])
def test_every_artifact_references_replacement(artifact: str):
    text = (_SUPERSEDED / artifact).read_text(encoding="utf-8")
    assert _REPLACEMENT_ID in text or "superseded" in text.lower()
