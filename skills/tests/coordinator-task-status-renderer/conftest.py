"""Test helpers for coordinator-task-status-renderer."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the renderer + seeder importable as modules in tests.
_RENDERER_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "coordinator-task-status-renderer"
    / "scripts"
)
if str(_RENDERER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RENDERER_SCRIPTS))

_BRIDGE_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
)
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))
