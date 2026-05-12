"""Guard test: autopilot-roadmap must not make direct LLM API calls.

The skill is host-assisted by design — all reasoning goes through the
orchestrating Claude Code agent via ``dispatch_fn``, or through
deterministic code. Reaching for ``llm_client`` or a vendor SDK inside
``skills/autopilot-roadmap/scripts/`` or ``skills/autopilot/scripts/``
defeats the host-assisted pattern and double-bills the user's session.
See ``skills/autopilot-roadmap/SKILL.md`` / "Design Principle: Host-Assisted Only".

If a legitimate future need arises (e.g., a genuinely offline / batch-
triggered autopilot path), update this test's allowlist with a comment
pointing to the SKILL.md section that justifies the exception.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_FORBIDDEN_IMPORTS = {
    "llm_client",                # the in-repo multi-vendor client
    "anthropic",                 # Anthropic SDK
    "openai",                    # OpenAI SDK
    "google.generativeai",       # Google Gemini SDK
    "google.genai",              # Google Gemini SDK (newer package name)
}

_SCOPES = [
    "autopilot-roadmap/scripts",
    "autopilot/scripts",
]


def _skills_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_python_files() -> list[Path]:
    root = _skills_root()
    files: list[Path] = []
    for scope in _SCOPES:
        scope_dir = root / scope
        if not scope_dir.exists():
            continue
        files.extend(scope_dir.rglob("*.py"))
    return files


def _toplevel_imports(path: Path) -> set[str]:
    """Return the set of fully-qualified top-level module names imported.

    Uses ``ast`` to avoid false positives on strings / comments that
    mention module names.
    """
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def test_no_direct_llm_api_imports():
    """No file under autopilot-roadmap/scripts or autopilot/scripts may
    import an LLM client or vendor SDK. See module docstring for rationale."""
    offenders: list[tuple[Path, str]] = []
    for path in _collect_python_files():
        imports = _toplevel_imports(path)
        for imp in imports:
            # Forbid exact match or any dotted prefix match — e.g.
            # `from anthropic.types import X` maps to module name
            # `anthropic.types`, which starts with forbidden `anthropic`.
            for forbidden in _FORBIDDEN_IMPORTS:
                if imp == forbidden or imp.startswith(forbidden + "."):
                    offenders.append((path, imp))

    if offenders:
        msg_lines = [
            "autopilot-roadmap / autopilot scripts must not import LLM API clients.",
            "See skills/autopilot-roadmap/SKILL.md -> 'Design Principle: Host-Assisted Only'.",
            "Offenders:",
        ]
        for path, imp in offenders:
            rel = path.relative_to(_skills_root())
            msg_lines.append(f"  {rel}: imports {imp}")
        pytest.fail("\n".join(msg_lines))


def test_guard_actually_runs():
    """Sanity check: the scopes exist and we're examining at least one file."""
    files = _collect_python_files()
    assert files, "No Python files found under autopilot-roadmap/scripts — guard is a no-op"
