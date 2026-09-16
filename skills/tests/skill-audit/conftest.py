"""Path setup for the skill-audit test suite.

The skill's scripts import each other by flat module name (``from findings
import ...``) and resolve sibling skills relative to their own location, so
the scripts directory goes first on ``sys.path``.
"""
from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = TESTS_DIR.parents[1]
SKILL_DIR = SKILLS_ROOT / "skill-audit"
SCRIPTS_DIR = SKILL_DIR / "scripts"
FIXTURES_DIR = TESTS_DIR / "fixtures"

for _p in (SCRIPTS_DIR, SKILLS_ROOT / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
