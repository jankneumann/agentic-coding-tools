"""Antigravity (agy) CLI transcript adapter.

Antigravity is Claude-shaped (design.md § Empirical CLI findings, E7): its
non-interactive output and its on-disk session transcripts follow the same
JSONL schema as Claude Code, so this adapter delegates parsing to
``ClaudeCodeCLIAdapter`` and only overrides the harness identifier and the
default data directory.

Reads session transcripts from
``~/.antigravity/projects/<encoded-cwd>/<session-id>.jsonl``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from adapters.claude_code_cli import ClaudeCodeCLIAdapter

logger = logging.getLogger(__name__)


class AntigravityCLIAdapter(ClaudeCodeCLIAdapter):
    """Adapter for Antigravity (agy) CLI session transcripts.

    Antigravity's transcript schema matches Claude Code's (E7), so discovery
    and normalization are inherited wholesale; every parsed event is stamped
    with this adapter's ``HARNESS_ID`` because the base class reads
    ``self.HARNESS_ID``.

    Parameters
    ----------
    base_dir:
        Override for the projects directory.  Defaults to
        ``~/.antigravity/projects``.
    """

    HARNESS_ID = "antigravity_cli"
    SCHEMA_VERSION = "1.0"

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is not None:
            super().__init__(base_dir=base_dir)
        else:
            super().__init__(base_dir=str(Path.home() / ".antigravity" / "projects"))
