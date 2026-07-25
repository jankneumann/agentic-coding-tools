"""Path setup and registry isolation for project-context-refresh tests.

Prepend the skill's ``scripts/`` directory so tests import bare module names
(``import registry``, ``import markers``), matching the repo's shared-runtime
convention. The runtime's own ``scripts/`` is added by ``_runtime`` on import.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "project-context-refresh"
    / "scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Reset the module-global producer registry around every test.

    The registry lazily self-populates the four canonical producers; tests that
    register a fake producer must start from an empty registry, and tests that
    exercise the defaults must not see leftovers from a prior test.
    """
    import registry as registry_mod

    saved = dict(registry_mod._REGISTRY)
    registry_mod._REGISTRY.clear()
    try:
        yield
    finally:
        registry_mod._REGISTRY.clear()
        registry_mod._REGISTRY.update(saved)
