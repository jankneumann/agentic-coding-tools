"""Content-assertion test for /implement-feature seeding-retry path.

SKILL.md must document a seeding retry at the start of /implement-feature: if
``try_issue_list(labels=["change:<id>"])`` returns empty AND the coordinator is
reachable, invoke the seeder before claiming work (per D11).

Covers task 3.2a.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2].parent
_IMPL_FEATURE_SKILL = _REPO_ROOT / "skills" / "implement-feature" / "SKILL.md"


def _read_skill() -> str:
    return _IMPL_FEATURE_SKILL.read_text(encoding="utf-8")


def test_implement_feature_documents_seeding_retry():
    text = _read_skill()
    # Must mention seed_tasks_from_md.py somewhere in the prose.
    assert "seed_tasks_from_md.py" in text, (
        "implement-feature SKILL.md must document the seeding retry path "
        "(reference seed_tasks_from_md.py per D11)"
    )
    # Must reference the retry condition: empty issue list when coordinator reachable.
    has_retry_clause = (
        "seeding retry" in text.lower()
        or "empty change" in text.lower()
        or "D11" in text
    )
    assert has_retry_clause, (
        "implement-feature SKILL.md must document the seeding-retry condition "
        "(seeding retry / empty change-id / D11 reference)"
    )
