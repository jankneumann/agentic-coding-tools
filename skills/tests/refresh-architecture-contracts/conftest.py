"""Shared fixtures/path wiring for the architecture-refresh contract tests.

These tests deliberately import the *installed* ri-06 canonical types from
``skills/project-context-runtime/scripts`` rather than copying the shared
operation/result schemas into this change. Both packages use flat module
imports, so we prepend their ``scripts`` directories to ``sys.path`` once.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUNTIME_SCRIPTS = _REPO_ROOT / "skills" / "project-context-runtime" / "scripts"
_ARCH_SCRIPTS = _REPO_ROOT / "skills" / "refresh-architecture" / "scripts"

for _p in (_RUNTIME_SCRIPTS, _ARCH_SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
