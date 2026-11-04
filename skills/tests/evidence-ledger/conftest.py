"""Shared helpers for the evidence-ledger tests.

The validator module is imported by its flat name, ``evidence_ledger``, from the canonical
skill directory. The name is unique across ``skills/``, so the shared pytest session
resolves it unambiguously (design D10).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "evidence-ledger" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
