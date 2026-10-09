"""Locations the driver needs. The harness root is stable; the repo root sits above it."""

from __future__ import annotations

from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = HARNESS_ROOT / "fixtures"
# skills/tests/multiplayer-simulation -> repo root
REPO_ROOT = HARNESS_ROOT.parents[2]
RUNTIME_SCRIPTS = REPO_ROOT / "skills" / "roadmap-runtime" / "scripts"
