"""Tests for skill Task() model parameter validation.

Validates that all Task() calls in skill SKILL.md files include a valid
`model=` parameter (Phase 1) per the specialized-workflow-agents spec.

Spec scenarios: agent-archetypes.3 (skill model hint integration)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Skills that must have model hints on all Task() calls
TARGET_SKILLS = [
    "plan-feature",
    "implement-feature",
    "iterate-on-plan",
    "iterate-on-implementation",
    "fix-scrub",
]

VALID_MODELS = {"opus", "sonnet", "haiku"}

# Regex to match Task( calls in markdown code blocks
# Captures the full Task(...) call including multiline
TASK_CALL_PATTERN = re.compile(
    r"Task\(\s*"
    r"(?:subagent_type\s*=\s*\"[^\"]+\"\s*,\s*)?"
    r"(?:.*?)"
    r"\)",
    re.DOTALL,
)

# Pattern for detecting Task( as a function call (not prose reference).
# Matches Task( at line start or after whitespace. Handles both single-line
# Task(subagent_type=...) and multiline Task(\n    subagent_type=...) forms.
TASK_LINE_PATTERN = re.compile(r"(?:^|\s)Task\(\s*$|(?:^|\s)Task\(\s*(?:subagent_type|description|prompt|model|archetype)")

# Pattern to detect model= parameter — matches both string literals (model="sonnet")
# and variable references (model=resolved_model) for Phase 2 archetype resolution
MODEL_PARAM_PATTERN = re.compile(r'model\s*=\s*(?:"([^"]+)"|([a-z_][a-z0-9_]*))')

# Stricter pattern for extracting string literal model values only
MODEL_LITERAL_PATTERN = re.compile(r'model\s*=\s*"([^"]+)"')


def _find_skill_dir() -> Path:
    """Find the skills/ directory relative to the test file."""
    # Walk up from test file to find skills/ at repo root
    current = Path(__file__).resolve()
    for parent in current.parents:
        skills_dir = parent / "skills"
        if skills_dir.is_dir() and (skills_dir / "plan-feature").is_dir():
            return skills_dir
    pytest.skip("Cannot find skills/ directory")
    return Path()  # unreachable


def _extract_task_calls(content: str) -> list[tuple[int, str]]:
    """Extract Task() calls with their line numbers from SKILL.md content.

    Returns list of (line_number, task_call_text) tuples.
    Only includes Task() calls inside code blocks (``` fenced).
    """
    results: list[tuple[int, str]] = []
    in_code_block = False
    lines = content.split("\n")

    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue

        # Only look at Task() calls inside code blocks or inline code
        if TASK_LINE_PATTERN.search(line):
            # Check if this line has a model= parameter
            # For multiline Task() calls, also check following lines
            task_text = line
            j = i
            # Accumulate lines until we find the closing )
            paren_depth = task_text.count("(") - task_text.count(")")
            while paren_depth > 0 and j < len(lines):
                j += 1
                next_line = lines[j - 1]
                task_text += "\n" + next_line
                paren_depth += next_line.count("(") - next_line.count(")")

            results.append((i, task_text))

    return results


class TestSkillModelHints:
    """Verify all target skill SKILL.md files have model= on Task() calls."""

    @pytest.fixture
    def skills_dir(self) -> Path:
        return _find_skill_dir()

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_skill_exists(self, skills_dir: Path, skill_name: str) -> None:
        """Each target skill SKILL.md must exist."""
        skill_file = skills_dir / skill_name / "SKILL.md"
        assert skill_file.exists(), f"Missing: {skill_file}"

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_all_task_calls_have_model(
        self, skills_dir: Path, skill_name: str
    ) -> None:
        """Every Task() call must include a model= parameter."""
        skill_file = skills_dir / skill_name / "SKILL.md"
        if not skill_file.exists():
            pytest.skip(f"{skill_file} not found")

        content = skill_file.read_text()
        task_calls = _extract_task_calls(content)

        if not task_calls:
            pytest.skip(f"No Task() calls found in {skill_name}/SKILL.md")

        missing: list[str] = []
        for line_num, task_text in task_calls:
            match = MODEL_PARAM_PATTERN.search(task_text)
            if not match:
                # Truncate for readability
                preview = task_text[:80].replace("\n", " ")
                missing.append(f"  line {line_num}: {preview}...")

        assert not missing, (
            f"{skill_name}/SKILL.md has Task() calls without model= parameter:\n"
            + "\n".join(missing)
        )

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_model_values_are_valid(
        self, skills_dir: Path, skill_name: str
    ) -> None:
        """model= values must be one of: opus, sonnet, haiku."""
        skill_file = skills_dir / skill_name / "SKILL.md"
        if not skill_file.exists():
            pytest.skip(f"{skill_file} not found")

        content = skill_file.read_text()
        task_calls = _extract_task_calls(content)

        invalid: list[str] = []
        for line_num, task_text in task_calls:
            match = MODEL_LITERAL_PATTERN.search(task_text)
            if match and match.group(1) not in VALID_MODELS:
                invalid.append(
                    f"  line {line_num}: model=\"{match.group(1)}\" "
                    f"(expected one of {VALID_MODELS})"
                )

        assert not invalid, (
            f"{skill_name}/SKILL.md has invalid model= values:\n"
            + "\n".join(invalid)
        )

    def test_plan_feature_resolves_analyst_archetype(
        self, skills_dir: Path
    ) -> None:
        """plan-feature should resolve the analyst archetype for Explore tasks."""
        skill_file = skills_dir / "plan-feature" / "SKILL.md"
        content = skill_file.read_text()
        # Verify archetype resolution block exists
        assert "analyst" in content.lower()
        assert "resolve_model" in content
        # Verify Explore tasks use the resolved variable
        task_calls = _extract_task_calls(content)
        for line_num, task_text in task_calls:
            if 'subagent_type="Explore"' in task_text:
                assert MODEL_PARAM_PATTERN.search(task_text), (
                    f"line {line_num}: Explore Task() missing model= parameter"
                )

    def test_implement_feature_resolves_runner_archetype(
        self, skills_dir: Path
    ) -> None:
        """implement-feature should resolve the runner archetype for Bash tasks."""
        skill_file = skills_dir / "implement-feature" / "SKILL.md"
        content = skill_file.read_text()
        # Verify archetype resolution block exists
        assert "runner" in content.lower()
        assert "resolve_model" in content
        # Verify Bash tasks use the resolved variable
        task_calls = _extract_task_calls(content)
        for line_num, task_text in task_calls:
            if 'subagent_type="Bash"' in task_text:
                assert MODEL_PARAM_PATTERN.search(task_text), (
                    f"line {line_num}: Bash Task() missing model= parameter"
                )
