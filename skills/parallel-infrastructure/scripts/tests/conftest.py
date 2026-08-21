"""Put this skill's ``scripts/`` directory on ``sys.path``.

The test modules here import their subjects by flat module name
(``from api_key_resolver import ApiKeyResolver``) without any path setup of
their own, which only resolves when ``scripts/`` is already importable. Nothing
put it there, so the whole directory failed to collect -- and because it was
absent from ``testpaths``, CI never surfaced that.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
