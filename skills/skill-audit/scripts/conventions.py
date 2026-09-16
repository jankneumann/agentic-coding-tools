"""Convention lint: ``rightsizing`` (default) or ``current`` (design D7).

``rightsizing`` is the post-``rewrite-skill-frontmatter`` /
post-``delete-rationalizations-relax-tail-block`` shape: ``triggers:`` is
absent by design, the tail block is optional, ``SKILL.md`` is at most 500
lines, and references are one level deep. ``current`` applies the assertions
in ``skills/tests/_shared/skill_invariants.py`` unchanged, so the finding
names the assertion that failed (for example ``assert_tail_block_present``).

Every failure is a ``convention_drift`` finding whose ``evidence.rule`` is
the rule name. Remediations: ``move_to_reference`` for size and depth,
``add_probe`` for the tail block, ``keep`` for the rest (they are in-place
fixes, not rightsizing work).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable

from audit_paths import SKILLS_ROOT
from findings import Finding

CONVENTIONS = ("rightsizing", "current")
RIGHTSIZING_MAX_LINES = 500
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_NESTED_REF_RE = re.compile(r"references/[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+\.md")

_REMEDIATION_BY_RULE = {
    "max_lines": "move_to_reference",
    "reference_depth": "move_to_reference",
    "assert_tail_block_present": "add_probe",
}


def _invariants():
    shared = SKILLS_ROOT / "tests" / "_shared"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import skill_invariants  # type: ignore[import-not-found]

    return skill_invariants


def _drift(rule: str, message: str, section_id: str = "SKILL.md") -> Finding:
    return Finding(
        kind="convention_drift",
        layer="contract",
        section_id=section_id,
        remediation=_REMEDIATION_BY_RULE.get(rule, "keep"),
        rationale=message,
        evidence={"rule": rule},
    )


def _run(rule: str, check: Callable[[], None], section_id: str = "SKILL.md") -> Finding | None:
    try:
        check()
    except AssertionError as exc:
        return _drift(rule, str(exc).splitlines()[0][:300], section_id)
    return None


def _frontmatter(skill_md: Path) -> dict:
    import yaml

    match = _FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    if not match:
        raise AssertionError(f"{skill_md}: missing or malformed YAML frontmatter")
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        raise AssertionError(f"{skill_md}: frontmatter must be a mapping")
    return data


def lint_rightsizing(skill_dir: Path) -> list[Finding]:
    inv = _invariants()
    skill_md = skill_dir / "SKILL.md"
    out: list[Finding] = []

    def keys_present() -> None:
        fm = _frontmatter(skill_md)
        missing = [k for k in ("name", "description") if not fm.get(k)]
        if missing:
            raise AssertionError(f"{skill_md}: missing frontmatter keys {missing}")

    for rule, check, section in (
        ("frontmatter_keys", keys_present, "SKILL.md#00-frontmatter"),
        ("references_resolve", lambda: inv.assert_references_resolve(skill_dir), "SKILL.md"),
        ("related_resolve", lambda: inv.assert_related_resolve(skill_dir), "SKILL.md#00-frontmatter"),
    ):
        finding = _run(rule, check, section)
        if finding:
            out.append(finding)

    line_count = len(skill_md.read_text(encoding="utf-8").splitlines())
    if line_count > RIGHTSIZING_MAX_LINES:
        out.append(_drift("max_lines", f"SKILL.md has {line_count} lines; the rightsizing cap is {RIGHTSIZING_MAX_LINES}"))

    nested: list[str] = sorted(set(_NESTED_REF_RE.findall(skill_md.read_text(encoding="utf-8"))))
    refs = skill_dir / "references"
    if refs.is_dir():
        for path in sorted(refs.rglob("*.md")):
            if path.parent != refs:
                nested.append(str(path.relative_to(skill_dir)))
    if nested:
        out.append(
            _drift(
                "reference_depth",
                "references nested more than one level below references/: " + ", ".join(sorted(set(nested))),
                "references/",
            )
        )
    return out


def lint_current(skill_dir: Path) -> list[Finding]:
    inv = _invariants()
    out: list[Finding] = []
    checks = (
        ("assert_frontmatter_parses", inv.assert_frontmatter_parses, "SKILL.md#00-frontmatter"),
        ("assert_required_keys_present", inv.assert_required_keys_present, "SKILL.md#00-frontmatter"),
        ("assert_references_resolve", inv.assert_references_resolve, "SKILL.md"),
        ("assert_related_resolve", inv.assert_related_resolve, "SKILL.md#00-frontmatter"),
        ("assert_tail_block_present", inv.assert_tail_block_present, "SKILL.md"),
    )
    for rule, fn, section in checks:
        finding = _run(rule, lambda fn=fn: fn(skill_dir), section)
        if finding:
            out.append(finding)
    return out


def lint(skill_dir: Path, convention: str) -> list[Finding]:
    if convention == "rightsizing":
        return lint_rightsizing(skill_dir)
    if convention == "current":
        return lint_current(skill_dir)
    raise ValueError(f"unknown convention: {convention!r} (expected one of {CONVENTIONS})")


__all__ = ["CONVENTIONS", "RIGHTSIZING_MAX_LINES", "lint", "lint_current", "lint_rightsizing"]
