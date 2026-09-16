"""Keep standalone skill scripts isolated in a shared pytest process.

Skills intentionally expose their scripts as flat modules (for example,
``models``, ``runner``, and ``cli``).  When pytest collects multiple skill test
directories, those names otherwise remain cached in ``sys.modules`` and can be
reused by the next suite even after its conftest changes ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_TESTS_ROOT = Path(__file__).resolve().parent
_SKILLS_ROOT = _TESTS_ROOT.parent
_ACTIVE_SUITE: str | None = None
_SUITE_MODULES: dict[str, dict[str, object]] = {}
_SCRIPT_DEPENDENCIES = {
    "archive-roadmap": ("roadmap-runtime",),
    "autopilot-roadmap": ("roadmap-runtime",),
    "candidate-work": ("plan-roadmap", "roadmap-runtime"),
    "context-engineering": (
        "project-context-refresh",
        "project-context-runtime",
    ),
    "merge-pull-requests": (
        "project-context-refresh",
        "project-context-runtime",
    ),
    "plan-roadmap": (
        "autopilot-roadmap",
        "refine-roadmap",
        "roadmap-runtime",
    ),
    "project-context-refresh": ("project-context-runtime",),
    "refine-roadmap": ("plan-roadmap", "roadmap-runtime"),
    "refresh-architecture-contracts": (
        "refresh-architecture",
        "project-context-runtime",
    ),
    "supervise": ("autopilot-roadmap", "roadmap-runtime"),
}


def _suite_for(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(_TESTS_ROOT)
    except ValueError:
        return None
    return relative.parts[0] if len(relative.parts) > 1 else None


def _is_flat_skill_module(module: object) -> bool:
    source = getattr(module, "__file__", None)
    if source is None:
        return False
    try:
        relative = Path(source).resolve().relative_to(_SKILLS_ROOT)
    except (OSError, ValueError):
        return False
    return len(relative.parts) >= 3 and relative.parts[1] == "scripts"


def _activate_suite(path: Path) -> None:
    global _ACTIVE_SUITE

    suite = _suite_for(path)
    if suite is None or suite == _ACTIVE_SUITE:
        return

    if _ACTIVE_SUITE is not None:
        _SUITE_MODULES[_ACTIVE_SUITE] = {
            name: module
            for name, module in sys.modules.items()
            if "." not in name and _is_flat_skill_module(module)
        }

    for name, module in tuple(sys.modules.items()):
        if "." not in name and _is_flat_skill_module(module):
            sys.modules.pop(name, None)

    script_roots = (suite, *_SCRIPT_DEPENDENCIES.get(suite, ()))
    for script_root in reversed(script_roots):
        scripts = _SKILLS_ROOT / script_root / "scripts"
        if not scripts.is_dir():
            continue
        scripts_path = str(scripts)
        if scripts_path in sys.path:
            sys.path.remove(scripts_path)
        sys.path.insert(0, scripts_path)

    sys.modules.update(_SUITE_MODULES.get(suite, {}))
    _ACTIVE_SUITE = suite


def pytest_collectstart(collector: pytest.Collector) -> None:
    if isinstance(collector, pytest.Module):
        _activate_suite(Path(str(collector.path)))


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Reactivate the coherent flat-module graph collected for this suite."""
    _activate_suite(Path(str(item.path)))
