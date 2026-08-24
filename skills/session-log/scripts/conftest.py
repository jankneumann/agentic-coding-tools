"""Put this skill's ``scripts/`` directory on ``sys.path``.

``test_extract_session_log.py`` and ``test_sanitize_session_log.py`` sit beside
the modules they test and import them by flat module name, which only resolves
when this directory is importable. Nothing put it there, so both files failed to
collect -- invisibly, because the directory was absent from ``testpaths``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
