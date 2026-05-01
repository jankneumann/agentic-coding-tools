"""Reusable invariant assertions for skill content quality.

These functions are imported by per-skill `test_skill_md.py` files and by
`conftest.py` (which exposes them as a fixture). They enforce the
content-invariant test framework requirement (skill-workflow spec).
"""
from __future__ import annotations

import re
from pathlib import Path


import yaml

REQUIRED_FRONTMATTER_KEYS = ("name", "description", "category", "tags", "triggers")

TAIL_BLOCK_HEADERS = (
    "## Common Rationalizations",
    "## Red Flags",
    "## Verification",
)

MIN_RATIONALIZATIONS = 3
MIN_RED_FLAGS = 3
MIN_VERIFICATION_ITEMS = 3

_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TABLE_ROW = re.compile(r"^\|.+\|.+\|", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*]\s+\S", re.MULTILINE)
_NUMBERED = re.compile(r"^\s*\d+\.\s+\S", re.MULTILINE)


def _read_skill(skill_path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text). Raise pytest.fail on parse error."""
    skill_md = skill_path / "SKILL.md" if skill_path.is_dir() else skill_path
    if not skill_md.exists():
        raise AssertionError(f"SKILL.md not found at {skill_md}")
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_PATTERN.match(text)
    if not match:
        raise AssertionError(f"{skill_md}: missing or malformed YAML frontmatter (must start with --- ... ---)")
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise AssertionError(f"{skill_md}: YAML frontmatter parse error: {exc}")
    if not isinstance(fm, dict):
        raise AssertionError(f"{skill_md}: frontmatter must be a mapping, got {type(fm).__name__}")
    body = text[match.end():]
    return fm, body


def assert_frontmatter_parses(skill_path: Path) -> dict:
    """Assert YAML frontmatter loads cleanly. Returns the parsed dict."""
    fm, _ = _read_skill(skill_path)
    return fm


def assert_required_keys_present(skill_path: Path) -> None:
    """Assert all required frontmatter keys are present and non-empty."""
    fm = assert_frontmatter_parses(skill_path)
    missing = [k for k in REQUIRED_FRONTMATTER_KEYS if not fm.get(k)]
    if missing:
        raise AssertionError(
            f"{skill_path}: missing or empty required frontmatter keys: {missing}. "
            f"Required: {list(REQUIRED_FRONTMATTER_KEYS)}"
        )


def _references_root(skill_path: Path) -> Path | None:
    """Find skills/references/ relative to the skill directory."""
    skill_dir = skill_path if skill_path.is_dir() else skill_path.parent
    cursor = skill_dir.resolve()
    for _ in range(6):
        candidate = cursor / "references"
        if candidate.is_dir() and (candidate / "skill-tail-template.md").exists():
            return candidate
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    return None


def assert_references_resolve(skill_path: Path) -> None:
    """Assert every references/<file>.md path cited in SKILL.md body exists."""
    _, body = _read_skill(skill_path)
    cited = set(re.findall(r"references/([A-Za-z0-9._/-]+\.md)", body))
    if not cited:
        return
    refs_root = _references_root(skill_path)
    if refs_root is None:
        raise AssertionError(
            f"{skill_path}: SKILL.md cites references/* but skills/references/ directory not found"
        )
    missing = [name for name in cited if not (refs_root / name).exists()]
    if missing:
        raise AssertionError(
            f"{skill_path}: cited references not found in {refs_root}: {missing}"
        )


def _skills_root(skill_path: Path) -> Path | None:
    """Find skills/ root by walking up from skill_path."""
    skill_dir = skill_path if skill_path.is_dir() else skill_path.parent
    cursor = skill_dir.resolve()
    for _ in range(6):
        if cursor.name == "skills" and (cursor / "install.sh").exists():
            return cursor
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    return None


def assert_related_resolve(skill_path: Path) -> None:
    """Assert every entry in `related:` frontmatter points to an existing skill."""
    fm = assert_frontmatter_parses(skill_path)
    related = fm.get("related") or []
    if not related:
        return
    if not isinstance(related, list):
        raise AssertionError(f"{skill_path}: `related:` must be a list, got {type(related).__name__}")
    skills_root = _skills_root(skill_path)
    if skills_root is None:
        raise AssertionError(f"{skill_path}: cannot locate skills/ root to verify related: targets")
    missing = [name for name in related if not (skills_root / name / "SKILL.md").exists()]
    if missing:
        raise AssertionError(
            f"{skill_path}: related: targets do not exist as skills (no SKILL.md): {missing}"
        )


def _section_text(body: str, start_header: str, end_header: str | None) -> str:
    start = body.find(start_header)
    if start < 0:
        return ""
    if end_header is None:
        return body[start:]
    end = body.find(end_header, start + len(start_header))
    return body[start:end] if end > 0 else body[start:]


def assert_tail_block_present(skill_path: Path) -> None:
    """Assert the three tail-block sections are present, in order, with minimum content.

    Only enforced when frontmatter has user_invocable: true (or is unset; default is
    user-invocable). Skills with explicit user_invocable: false are exempt.
    """
    fm, body = _read_skill(skill_path)
    if fm.get("user_invocable") is False:
        return
    positions: list[tuple[int, str]] = []
    for header in TAIL_BLOCK_HEADERS:
        idx = body.find(header)
        if idx < 0:
            raise AssertionError(
                f"{skill_path}: tail-block section missing: {header!r}. "
                f"All three of {list(TAIL_BLOCK_HEADERS)} are required for user_invocable skills."
            )
        positions.append((idx, header))
    sorted_positions = sorted(positions)
    if [h for _, h in sorted_positions] != list(TAIL_BLOCK_HEADERS):
        raise AssertionError(
            f"{skill_path}: tail-block sections must appear in order "
            f"{list(TAIL_BLOCK_HEADERS)}, got {[h for _, h in sorted_positions]}"
        )
    rationalizations_section = _section_text(body, TAIL_BLOCK_HEADERS[0], TAIL_BLOCK_HEADERS[1])
    rows = [
        r for r in _TABLE_ROW.findall(rationalizations_section)
        if "---" not in r and "Rationalization" not in r
    ]
    if len(rows) < MIN_RATIONALIZATIONS:
        raise AssertionError(
            f"{skill_path}: Common Rationalizations table needs ≥{MIN_RATIONALIZATIONS} content rows, found {len(rows)}"
        )
    red_flags_section = _section_text(body, TAIL_BLOCK_HEADERS[1], TAIL_BLOCK_HEADERS[2])
    bullets = _BULLET.findall(red_flags_section)
    if len(bullets) < MIN_RED_FLAGS:
        raise AssertionError(
            f"{skill_path}: Red Flags list needs ≥{MIN_RED_FLAGS} bullets, found {len(bullets)}"
        )
    verification_section = _section_text(body, TAIL_BLOCK_HEADERS[2], None)
    items = _NUMBERED.findall(verification_section)
    if len(items) < MIN_VERIFICATION_ITEMS:
        raise AssertionError(
            f"{skill_path}: Verification checklist needs ≥{MIN_VERIFICATION_ITEMS} numbered items, found {len(items)}"
        )
