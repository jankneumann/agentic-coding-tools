"""Path setup for plan-roadmap tests."""

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
for subdir in ["plan-roadmap/scripts", "roadmap-runtime/scripts"]:
    p = str(_SKILLS_DIR / subdir)
    if p not in sys.path:
        sys.path.insert(0, p)
