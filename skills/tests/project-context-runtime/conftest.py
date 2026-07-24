"""Path setup for project-context-runtime tests.

Prepend the runtime's ``scripts/`` directory so tests import bare module names
(``import models``, ``import store``), matching the repo's shared-runtime
convention.
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "project-context-runtime" / "scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
