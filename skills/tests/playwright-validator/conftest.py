"""Path setup for playwright-validator tests.

Adds ``skills/playwright-validator/scripts/`` to ``sys.path`` so the test
modules can import the validator's modules by their plain names
(``descriptor``, ``parser``, ``generator``, ``runner``, ``findings``,
``auth_flow``, ``cli``) -- mirroring how :mod:`cli` itself imports them.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _SKILLS_DIR / "playwright-validator" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
