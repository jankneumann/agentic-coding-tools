"""Tests for skill Task()/Agent()/CLI model parameter validation.

Skills author archetype/tier vocabulary and resolve to harness model ids at
dispatch time. String-literal model pins in fenced dispatch examples are
always invalid; ``model=<variable>`` remains valid.

Spec scenarios: agent-archetypes (Skill Model Hint Integration),
skill-workflow (Skill-Authored Model Vocabulary).
Design: retire-skill-literal-model-hints D3.
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

# Pattern for detecting Task( as a function call (not prose reference).
TASK_LINE_PATTERN = re.compile(
    r"(?:^|\s)Task\(\s*$|(?:^|\s)Task\(\s*(?:subagent_type|description|prompt|model|archetype)"
)

# Pattern for detecting Agent( as a function call.
AGENT_LINE_PATTERN = re.compile(
    r"(?:^|\s)Agent\(\s*$|(?:^|\s)Agent\(\s*(?:prompt|description|model|isolation|subagent_type)"
)

# model= parameter — string literal OR variable reference
MODEL_PARAM_PATTERN = re.compile(r'model\s*=\s*(?:"([^"]+)"|([a-z_][a-z0-9_]*))')

# String-literal model= only (always invalid in fenced dispatch)
MODEL_LITERAL_PATTERN = re.compile(r'model\s*=\s*"([^"]+)"')

# Vendor CLI -m <literal-model-id> in fenced dispatch examples.
# Scoped to known vendor CLIs to avoid python -m pytest false positives.
VENDOR_CLI_MODEL_PATTERN = re.compile(
    r"(?:codex|claude|gemini|grok|pi|antigravity)\b[^\n]*?"
    r"(?:^|\s)-m\s+([A-Za-z0-9][A-Za-z0-9._+-]*)",
    re.MULTILINE,
)

# Placeholders / variables that are not policy pins when used with -m
_CLI_MODEL_PLACEHOLDER = re.compile(
    r"^(?:\$[A-Za-z_][A-Za-z0-9_]*"
    r"|<[^>]+>"
    r"|\{[^}]+\}"
    r"|[a-z_][a-z0-9_]*)$"
)

# Narrative policy-shaped version pins (plan-roadmap inventory).
NARRATIVE_MODEL_VERSION_PATTERN = re.compile(
    r"\b(?:gpt-\d+(?:\.\d+)?(?:-[a-z0-9]+)*|gemini-\d+(?:\.\d+)?(?:-[a-z0-9]+)*)\b",
    re.IGNORECASE,
)


def _find_skill_dir() -> Path:
    """Find the skills/ directory relative to the test file."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        skills_dir = parent / "skills"
        if skills_dir.is_dir() and (skills_dir / "plan-feature").is_dir():
            return skills_dir
    pytest.skip("Cannot find skills/ directory")
    return Path()  # unreachable


def _iter_fenced_blocks(content: str) -> list[tuple[int, str]]:
    """Return (start_line, block_text) for each fenced ``` block."""
    blocks: list[tuple[int, str]] = []
    lines = content.split("\n")
    in_fence = False
    start_line = 0
    buf: list[str] = []
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            if not in_fence:
                in_fence = True
                start_line = i + 1
                buf = []
            else:
                blocks.append((start_line, "\n".join(buf)))
                in_fence = False
                buf = []
            continue
        if in_fence:
            buf.append(line)
    return blocks


def _accumulate_call(
    lines: list[str], start_idx: int, start_line_no: int
) -> tuple[int, str]:
    """Accumulate a Task(/Agent( call from start_idx until balanced parens."""
    task_text = lines[start_idx]
    paren_depth = task_text.count("(") - task_text.count(")")
    j = start_idx
    while paren_depth > 0 and j + 1 < len(lines):
        j += 1
        next_line = lines[j]
        task_text += "\n" + next_line
        paren_depth += next_line.count("(") - next_line.count(")")
    return start_line_no, task_text


def _extract_calls_from_fences(
    content: str, line_pattern: re.Pattern[str]
) -> list[tuple[int, str]]:
    """Extract Task()/Agent() calls inside fenced blocks with line numbers."""
    results: list[tuple[int, str]] = []
    for block_start, block_text in _iter_fenced_blocks(content):
        lines = block_text.split("\n")
        for offset, line in enumerate(lines):
            if line_pattern.search(line):
                line_no = block_start + offset
                results.append(_accumulate_call(lines, offset, line_no))
    return results


def _extract_task_calls(content: str) -> list[tuple[int, str]]:
    """Extract fenced Task() calls with their line numbers."""
    return _extract_calls_from_fences(content, TASK_LINE_PATTERN)


def _extract_agent_calls(content: str) -> list[tuple[int, str]]:
    """Extract fenced Agent() calls with their line numbers."""
    return _extract_calls_from_fences(content, AGENT_LINE_PATTERN)


def find_task_model_literals(
    content: str, *, path: str = "<content>"
) -> list[str]:
    """Return file+line findings for string-literal model= on fenced Task()."""
    findings: list[str] = []
    for line_num, task_text in _extract_task_calls(content):
        match = MODEL_LITERAL_PATTERN.search(task_text)
        if match:
            findings.append(
                f"  {path}:{line_num}: Task() model=\"{match.group(1)}\" "
                f"(string literals are invalid; use model=<resolved_variable>)"
            )
    return findings


_INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")


def find_agent_model_literals(
    content: str, *, path: str = "<content>"
) -> list[str]:
    """Return file+line findings for string-literal model= on Agent() examples.

    Scans fenced blocks and inline `` `...` `` spans (cite-requirements style).
    """
    findings: list[str] = []
    for line_num, agent_text in _extract_agent_calls(content):
        match = MODEL_LITERAL_PATTERN.search(agent_text)
        if match:
            findings.append(
                f"  {path}:{line_num}: Agent() model=\"{match.group(1)}\" "
                f"(string literals are invalid; use model=<resolved_variable>)"
            )
    # Inline single-backtick Agent(...) examples outside fences
    lines = content.split("\n")
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for span in _INLINE_CODE_PATTERN.finditer(line):
            code = span.group(1)
            if "Agent(" not in code:
                continue
            match = MODEL_LITERAL_PATTERN.search(code)
            if match:
                findings.append(
                    f"  {path}:{i}: Agent() model=\"{match.group(1)}\" "
                    f"(string literals are invalid; use model=<resolved_variable>)"
                )
    return findings


def _cli_literal_findings_in_text(
    text: str, *, path: str, line_no: int
) -> list[str]:
    findings: list[str] = []
    for match in VENDOR_CLI_MODEL_PATTERN.finditer(text):
        model_id = match.group(1)
        if _CLI_MODEL_PLACEHOLDER.match(model_id):
            # Accept bare variable names (resolved_model); reject roster aliases.
            if model_id.isidentifier() and model_id not in {
                "opus",
                "sonnet",
                "haiku",
                "fable",
            }:
                continue
        findings.append(
            f"  {path}:{line_no}: vendor CLI -m {model_id} "
            f"(literal model ids are invalid; resolve from archetypes.yaml)"
        )
    return findings


def find_vendor_cli_model_literals(
    content: str, *, path: str = "<content>"
) -> list[str]:
    """Return file+line findings for vendor CLI ``-m <literal>`` in dispatch examples."""
    findings: list[str] = []
    for block_start, block_text in _iter_fenced_blocks(content):
        for match in VENDOR_CLI_MODEL_PATTERN.finditer(block_text):
            model_id = match.group(1)
            if _CLI_MODEL_PLACEHOLDER.match(model_id):
                if model_id.isidentifier() and model_id not in {
                    "opus",
                    "sonnet",
                    "haiku",
                    "fable",
                }:
                    continue
            line_offset = block_text[: match.start()].count("\n")
            line_no = block_start + line_offset
            findings.append(
                f"  {path}:{line_no}: vendor CLI -m {model_id} "
                f"(literal model ids are invalid; resolve from archetypes.yaml)"
            )
    # Inline single-backtick vendor CLI examples
    lines = content.split("\n")
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for span in _INLINE_CODE_PATTERN.finditer(line):
            findings.extend(
                _cli_literal_findings_in_text(
                    span.group(1), path=path, line_no=i
                )
            )
    return findings


def find_narrative_model_version_pins(
    content: str, *, path: str = "<content>"
) -> list[str]:
    """Return findings for narrative gpt-/gemini- version tokens used as defaults."""
    findings: list[str] = []
    lines = content.split("\n")
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        # Escape-hatch override docs may show harness ids; skip those lines.
        if "AUTOPILOT_PHASE_MODEL_OVERRIDE" in line or (
            in_fence and "PHASE_MODEL_OVERRIDE" in "\n".join(lines[max(0, i - 5) : i])
        ):
            continue
        if in_fence:
            # Fenced dispatch is covered by Task/Agent/CLI scanners.
            continue
        for match in NARRATIVE_MODEL_VERSION_PATTERN.finditer(line):
            findings.append(
                f"  {path}:{i}: narrative model version pin '{match.group(0)}' "
                f"(use premium-tier / vendor-role language instead)"
            )
    return findings


class TestSkillModelHints:
    """Verify target skill SKILL.md files resolve models; ban string literals."""

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
        """Every fenced Task() call must include a model= parameter."""
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
                preview = task_text[:80].replace("\n", " ")
                missing.append(f"  {skill_name}/SKILL.md:{line_num}: {preview}...")

        assert not missing, (
            f"{skill_name}/SKILL.md has Task() calls without model= parameter:\n"
            + "\n".join(missing)
        )

    @pytest.mark.parametrize("skill_name", TARGET_SKILLS)
    def test_task_model_values_are_not_string_literals(
        self, skills_dir: Path, skill_name: str
    ) -> None:
        """String-literal model=\"…\" on fenced Task() is always invalid."""
        skill_file = skills_dir / skill_name / "SKILL.md"
        if not skill_file.exists():
            pytest.skip(f"{skill_file} not found")

        content = skill_file.read_text()
        findings = find_task_model_literals(
            content, path=f"{skill_name}/SKILL.md"
        )
        assert not findings, (
            f"{skill_name}/SKILL.md has string-literal Task() model= pins:\n"
            + "\n".join(findings)
        )

    def test_plan_feature_resolves_analyst_archetype(
        self, skills_dir: Path
    ) -> None:
        """plan-feature should resolve the analyst archetype for Explore tasks."""
        skill_file = skills_dir / "plan-feature" / "SKILL.md"
        content = skill_file.read_text()
        assert "analyst" in content.lower()
        assert "try_resolve_archetype_for_phase" in content
        assert "src.agents_config" not in content
        task_calls = _extract_task_calls(content)
        for line_num, task_text in task_calls:
            if 'subagent_type="Explore"' in task_text:
                assert MODEL_PARAM_PATTERN.search(task_text), (
                    f"line {line_num}: Explore Task() missing model= parameter"
                )
                assert not MODEL_LITERAL_PATTERN.search(task_text), (
                    f"line {line_num}: Explore Task() must not use model=\"…\" literal"
                )

    def test_implement_feature_resolves_runner_archetype(
        self, skills_dir: Path
    ) -> None:
        """implement-feature should resolve the runner archetype for Bash tasks."""
        skill_file = skills_dir / "implement-feature" / "SKILL.md"
        content = skill_file.read_text()
        assert "runner" in content.lower()
        assert "try_resolve_archetype_for_phase" in content
        assert "src.agents_config" not in content
        task_calls = _extract_task_calls(content)
        for line_num, task_text in task_calls:
            if 'subagent_type="Bash"' in task_text:
                assert MODEL_PARAM_PATTERN.search(task_text), (
                    f"line {line_num}: Bash Task() missing model= parameter"
                )
                assert not MODEL_LITERAL_PATTERN.search(task_text), (
                    f"line {line_num}: Bash Task() must not use model=\"…\" literal"
                )


class TestLiteralRejectionUnit:
    """Synthetic-content unit tests for literal pin rejection (D3)."""

    def test_task_string_literal_is_rejected(self) -> None:
        content = (
            "Dispatch:\n"
            "```\n"
            'Task(subagent_type="Explore", model="haiku", prompt="x")\n'
            "```\n"
        )
        findings = find_task_model_literals(content, path="synth.md")
        assert findings, "expected string-literal Task() model= to fail"
        assert "synth.md:" in findings[0]
        assert 'model="haiku"' in findings[0]

    def test_task_variable_model_is_accepted(self) -> None:
        content = (
            "Dispatch:\n"
            "```\n"
            'Task(subagent_type="Explore", model=analyst_model, prompt="x")\n'
            "```\n"
        )
        assert find_task_model_literals(content) == []

    def test_agent_string_literal_is_rejected_with_file_line(self) -> None:
        content = (
            "Annotate:\n"
            "```\n"
            'Agent(prompt=<annotation prompt>, model="haiku")\n'
            "```\n"
        )
        findings = find_agent_model_literals(content, path="cite.md")
        assert findings, "expected string-literal Agent() model= to fail"
        assert "cite.md:" in findings[0]
        assert 'model="haiku"' in findings[0]

    def test_agent_variable_model_is_accepted(self) -> None:
        content = (
            "Annotate:\n"
            "```\n"
            "Agent(prompt=<annotation prompt>, model=claude_economy_model)\n"
            "```\n"
        )
        assert find_agent_model_literals(content) == []

    def test_vendor_cli_literal_is_rejected_with_file_line(self) -> None:
        content = (
            "Dispatch:\n"
            "```bash\n"
            'codex exec -m gpt-5.6-luna "<annotation prompt>"\n'
            "```\n"
        )
        findings = find_vendor_cli_model_literals(content, path="cite.md")
        assert findings, "expected vendor CLI -m literal to fail"
        assert "cite.md:" in findings[0]
        assert "gpt-5.6-luna" in findings[0]

    def test_vendor_cli_resolved_variable_is_accepted(self) -> None:
        content = (
            "Dispatch:\n"
            "```bash\n"
            'codex exec -m "$codex_economy_model" "<annotation prompt>"\n'
            "```\n"
        )
        assert find_vendor_cli_model_literals(content) == []

    def test_python_module_flag_is_not_a_vendor_cli_pin(self) -> None:
        content = (
            "Checks:\n"
            "```bash\n"
            "python -m pytest skills/validate-packages -q\n"
            "```\n"
        )
        assert find_vendor_cli_model_literals(content) == []


class TestSkillInventoryScans:
    """Real-skill scans for Agent/CLI literals and plan-roadmap narrative pins."""

    @pytest.fixture
    def skills_dir(self) -> Path:
        return _find_skill_dir()

    def test_no_agent_model_string_literals_in_skills(
        self, skills_dir: Path
    ) -> None:
        """Fenced Agent(..., model=\"…\") pins fail with file+line."""
        findings: list[str] = []
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            rel = f"{skill_md.parent.name}/SKILL.md"
            findings.extend(
                find_agent_model_literals(skill_md.read_text(), path=rel)
            )
        assert not findings, (
            "Skill SKILL.md files have string-literal Agent() model= pins:\n"
            + "\n".join(findings)
        )

    def test_no_vendor_cli_model_literals_in_skills(
        self, skills_dir: Path
    ) -> None:
        """Fenced vendor CLI -m <literal> pins fail with file+line."""
        findings: list[str] = []
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            rel = f"{skill_md.parent.name}/SKILL.md"
            findings.extend(
                find_vendor_cli_model_literals(skill_md.read_text(), path=rel)
            )
        # Also scan skill-owned templates that instruct dispatch.
        for template in sorted(skills_dir.glob("*/templates/*.md")):
            rel = f"{template.parent.parent.name}/templates/{template.name}"
            findings.extend(
                find_vendor_cli_model_literals(template.read_text(), path=rel)
            )
        assert not findings, (
            "Skills have vendor CLI -m <literal> pins:\n" + "\n".join(findings)
        )

    def test_plan_roadmap_narrative_avoids_version_pins(
        self, skills_dir: Path
    ) -> None:
        """plan-roadmap prose defaults use tier/vendor-role language, not versions."""
        findings: list[str] = []
        for rel in (
            "plan-roadmap/SKILL.md",
            "plan-roadmap/templates/generation-prompt.md",
        ):
            path = skills_dir / rel
            if not path.exists():
                continue
            findings.extend(
                find_narrative_model_version_pins(path.read_text(), path=rel)
            )
        assert not findings, (
            "plan-roadmap still pins concrete model versions as defaults:\n"
            + "\n".join(findings)
        )
