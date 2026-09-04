"""Content invariant: the Test quality checklist and Finding Types entries.

Spec: skill-workflow "Implementation Review Test-Quality Findings" —
Scenario: Checklist present in the skill.

`parallel-review-implementation/SKILL.md` must contain a Test quality
checklist, under the Code Quality Review step, naming every smell from the
`simplify-implementation` Delete catalog and every test-induced seam pattern
by name, plus a Finding Types list that includes `test_quality`,
`simplification`, and `behavioral_failure`.
"""
from __future__ import annotations

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "parallel-review-implementation"
SKILL_MD = SKILL_DIR / "SKILL.md"

CODE_QUALITY_HEADER = "### 4. Code Quality Review"
NEXT_STEP_HEADER = "### 5. Verification Result Cross-Check"
FINDING_TYPES_HEADER = "#### Finding Types"
DISPOSITIONS_HEADER = "#### Dispositions"

# The simplify-implementation Delete catalog (eight smells) — named identifiers,
# not the full catalog table, per skills/simplify-implementation/SKILL.md
# "### Delete catalog".
DELETE_CATALOG_SMELLS = (
    "source-mirroring",
    "change-detector",
    "self-mocking",
    "duplicative",
    "accessor-only",
    "library-under-test",
    "vacuous",
    "unreviewed-snapshot",
)

# The five test-induced seam patterns, per skills/simplify-implementation/SKILL.md
# "### Test-induced seams (only after pruning)".
SEAM_PATTERNS = (
    "mock-only interface",
    "test-only constructor parameter",
    "visibility widened for tests",
    "factory-of-one",
    "_for_testing",
    "reset_state()",
)


def _section(body: str, start_header: str, end_header: str) -> str:
    start = body.find(start_header)
    assert start >= 0, f"{start_header!r} not found in SKILL.md"
    end = body.find(end_header, start + len(start_header))
    assert end > start, f"{end_header!r} not found after {start_header!r} in SKILL.md"
    return body[start:end]


def _read_body() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_test_quality_checklist_present_under_code_quality_review():
    body = _read_body()
    section = _section(body, CODE_QUALITY_HEADER, NEXT_STEP_HEADER)
    assert "Test quality" in section, (
        "Code Quality Review step must contain a 'Test quality' checklist/subsection"
    )


def test_test_quality_checklist_names_all_delete_catalog_smells():
    body = _read_body()
    section = _section(body, CODE_QUALITY_HEADER, NEXT_STEP_HEADER)
    # Normalize markdown line-wrap whitespace so a multi-word identifier that
    # happens to wrap across lines in the .md source still matches.
    normalized = " ".join(section.split()).lower()
    missing = [s for s in DELETE_CATALOG_SMELLS if s.lower() not in normalized]
    assert not missing, (
        f"Test quality checklist is missing Delete catalog smells: {missing}"
    )


def test_test_quality_checklist_names_all_seam_patterns():
    body = _read_body()
    section = _section(body, CODE_QUALITY_HEADER, NEXT_STEP_HEADER)
    normalized = " ".join(section.split()).lower()
    missing = [p for p in SEAM_PATTERNS if p.lower() not in normalized]
    assert not missing, (
        f"Test quality checklist is missing test-induced seam patterns: {missing}"
    )


def test_test_quality_checklist_states_criticality_and_axis_rules():
    body = _read_body()
    section = _section(body, CODE_QUALITY_HEADER, NEXT_STEP_HEADER)
    assert "criticality: low" in section, (
        "Test quality checklist must state findings are criticality: low"
    )
    assert "readability" in section and "correctness" in section, (
        "Test quality checklist must state the readability/correctness axis mapping"
    )


def test_test_quality_checklist_states_read_only_constraint():
    body = _read_body()
    section = _section(body, CODE_QUALITY_HEADER, NEXT_STEP_HEADER)
    assert "read-only" in section.lower(), (
        "Test quality checklist must state the reviewer never deletes tests or seams"
    )


def test_finding_types_includes_new_enum_values():
    body = _read_body()
    section = _section(body, FINDING_TYPES_HEADER, DISPOSITIONS_HEADER)
    for value in ("test_quality", "simplification", "behavioral_failure"):
        assert f"`{value}`" in section, (
            f"Finding Types list must include `{value}`"
        )
