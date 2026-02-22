"""Tests for the generate_prompts module."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fix_models import ClassifiedFinding, Finding, FixGroup  # noqa: E402

from generate_prompts import generate_prompts  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    *,
    id: str = "F001",
    source: str = "ruff",
    severity: str = "high",
    category: str = "lint",
    title: str = "Unused import",
    detail: str = "os is imported but unused",
    file_path: str = "src/app.py",
    line: int | None = 10,
) -> Finding:
    return Finding(
        id=id,
        source=source,
        severity=severity,
        category=category,
        title=title,
        detail=detail,
        file_path=file_path,
        line=line,
    )


def _make_classified(
    finding: Finding | None = None,
    *,
    tier: str = "agent",
    fix_strategy: str = "Remove the unused import statement",
) -> ClassifiedFinding:
    return ClassifiedFinding(
        finding=finding or _make_finding(),
        tier=tier,
        fix_strategy=fix_strategy,
    )


def _make_group(
    file_path: str = "src/app.py",
    classified_findings: list[ClassifiedFinding] | None = None,
) -> FixGroup:
    return FixGroup(
        file_path=file_path,
        classified_findings=classified_findings or [_make_classified()],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFileScopeRestriction:
    """Prompt content includes file scope restriction ('MAY ONLY modify')."""

    def test_prompt_contains_may_only_modify(self) -> None:
        group = _make_group(file_path="src/utils.py")
        result = generate_prompts([group])

        assert len(result) == 1
        _, prompt_text = result[0]
        assert "MAY ONLY modify" in prompt_text

    def test_prompt_scope_references_correct_file(self) -> None:
        group = _make_group(file_path="lib/helpers.py")
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert "MAY ONLY modify: `lib/helpers.py`" in prompt_text

    def test_prompt_contains_must_not_modify_other_files(self) -> None:
        group = _make_group(file_path="src/main.py")
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert "must NOT modify any other files" in prompt_text


class TestFindingDetailsInPrompt:
    """Prompt includes finding details: title, location, source, strategy."""

    def test_prompt_includes_finding_title(self) -> None:
        finding = _make_finding(title="Missing return type annotation")
        group = _make_group(
            classified_findings=[_make_classified(finding, fix_strategy="Add -> None")]
        )
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert "Missing return type annotation" in prompt_text

    def test_prompt_includes_location_with_line(self) -> None:
        finding = _make_finding(file_path="src/app.py", line=42)
        group = _make_group(
            file_path="src/app.py",
            classified_findings=[_make_classified(finding)],
        )
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert "src/app.py:42" in prompt_text

    def test_prompt_includes_location_without_line(self) -> None:
        finding = _make_finding(file_path="src/app.py", line=None)
        group = _make_group(
            file_path="src/app.py",
            classified_findings=[_make_classified(finding)],
        )
        result = generate_prompts([group])

        _, prompt_text = result[0]
        # When line is None, location should be just the file path (no colon)
        assert "Location: src/app.py\n" in prompt_text

    def test_prompt_includes_source(self) -> None:
        finding = _make_finding(source="mypy")
        group = _make_group(classified_findings=[_make_classified(finding)])
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert "Source: mypy" in prompt_text

    def test_prompt_includes_fix_strategy(self) -> None:
        group = _make_group(
            classified_findings=[
                _make_classified(fix_strategy="Wrap call in try/except block")
            ]
        )
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert "Strategy: Wrap call in try/except block" in prompt_text

    def test_prompt_includes_severity(self) -> None:
        finding = _make_finding(severity="critical")
        group = _make_group(classified_findings=[_make_classified(finding)])
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert "[CRITICAL]" in prompt_text


class TestSameFileBatching:
    """Multiple findings for the same file appear in one prompt."""

    def test_two_findings_same_file_one_prompt(self) -> None:
        f1 = _make_finding(id="F001", title="Unused import", line=1)
        f2 = _make_finding(id="F002", title="Missing docstring", line=15)
        group = _make_group(
            file_path="src/app.py",
            classified_findings=[
                _make_classified(f1, fix_strategy="Remove import"),
                _make_classified(f2, fix_strategy="Add module docstring"),
            ],
        )
        result = generate_prompts([group])

        assert len(result) == 1
        _, prompt_text = result[0]
        assert "Unused import" in prompt_text
        assert "Missing docstring" in prompt_text
        assert "Remove import" in prompt_text
        assert "Add module docstring" in prompt_text

    def test_three_findings_all_present(self) -> None:
        findings = [
            _make_finding(id=f"F{i}", title=f"Issue {i}", line=i * 10)
            for i in range(1, 4)
        ]
        group = _make_group(
            file_path="src/app.py",
            classified_findings=[
                _make_classified(f, fix_strategy=f"Fix issue {i}")
                for i, f in enumerate(findings, 1)
            ],
        )
        result = generate_prompts([group])

        assert len(result) == 1
        _, prompt_text = result[0]
        for i in range(1, 4):
            assert f"Issue {i}" in prompt_text
            assert f"Fix issue {i}" in prompt_text


class TestReturnFormat:
    """Each prompt is a (file_path, prompt_text) tuple."""

    def test_single_group_returns_tuple(self) -> None:
        group = _make_group(file_path="src/module.py")
        result = generate_prompts([group])

        assert len(result) == 1
        item = result[0]
        assert isinstance(item, tuple)
        assert len(item) == 2

    def test_tuple_first_element_is_file_path(self) -> None:
        group = _make_group(file_path="pkg/core.py")
        result = generate_prompts([group])

        file_path, _ = result[0]
        assert file_path == "pkg/core.py"

    def test_tuple_second_element_is_string(self) -> None:
        group = _make_group()
        result = generate_prompts([group])

        _, prompt_text = result[0]
        assert isinstance(prompt_text, str)
        assert len(prompt_text) > 0

    def test_multiple_groups_return_multiple_tuples(self) -> None:
        groups = [
            _make_group(
                file_path="src/a.py",
                classified_findings=[
                    _make_classified(
                        _make_finding(id="F1", file_path="src/a.py"),
                    )
                ],
            ),
            _make_group(
                file_path="src/b.py",
                classified_findings=[
                    _make_classified(
                        _make_finding(id="F2", file_path="src/b.py"),
                    )
                ],
            ),
        ]
        result = generate_prompts(groups)

        assert len(result) == 2
        paths = [fp for fp, _ in result]
        assert paths == ["src/a.py", "src/b.py"]


class TestEmptyInput:
    """Empty input returns empty list."""

    def test_empty_list_returns_empty(self) -> None:
        result = generate_prompts([])

        assert result == []

    def test_empty_list_returns_list_type(self) -> None:
        result = generate_prompts([])

        assert isinstance(result, list)
