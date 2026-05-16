from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
for candidate in (
    ROOT / "agent-coordinator",
    ROOT / "skills" / "autopilot" / "scripts",
    ROOT / "skills" / "coordination-bridge" / "scripts",
    ROOT / "skills" / "parallel-infrastructure" / "scripts",
    ROOT / "skills" / "session-log" / "scripts",
):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
