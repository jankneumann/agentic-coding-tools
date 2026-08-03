"""Path setup and shared fixtures for validate-packages tests.

Prepend the skill's ``scripts/`` directory so tests import bare module names
(``import context_impact``), matching the repo's shared-runtime convention, and
this directory so ``wp_fixtures`` resolves regardless of pytest's rootdir.

Tests live here rather than in ``skills/validate-packages/scripts/tests/`` so
that ``install.sh`` does not ship them into consumer runtime copies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPTS_DIR = _HERE.parents[1] / "validate-packages" / "scripts"

for _path in (str(_HERE), str(_SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from wp_fixtures import SCHEMA_PATH  # noqa: E402


@pytest.fixture(scope="session")
def schema() -> dict[str, Any]:
    """The canonical work-packages schema (install-asset source, not the copy)."""
    return json.loads(SCHEMA_PATH.read_text())
