"""Path setup for archive-roadmap tests."""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "archive-roadmap" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
