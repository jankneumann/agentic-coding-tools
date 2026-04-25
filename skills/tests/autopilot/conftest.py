"""Shared fixtures for skills/tests/autopilot/.

Adds skills/autopilot/scripts/ and skills/coordination-bridge/scripts/ to
``sys.path`` so the test modules can ``import phase_agent``,
``import autopilot``, and ``import coordination_bridge`` without an
editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parents[2]
for sub in ("autopilot/scripts", "coordination-bridge/scripts", "session-log/scripts"):
    candidate = _SKILLS_DIR / sub
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
