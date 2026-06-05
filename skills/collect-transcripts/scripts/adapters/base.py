"""Abstract base class for session transcript adapters.

Each adapter discovers sessions from its vendor-specific source and
normalizes raw events into NormalizedEvent instances.  All adapters MUST
fail soft (log a structured warning and skip) when their source is
unavailable.
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

# Allow importing normalize from the parent scripts directory
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from normalize import NormalizedEvent, SessionSummary  # noqa: E402

logger = logging.getLogger(__name__)


class AdapterError(Exception):
    """Raised when an adapter encounters a recoverable error.

    Adapters MUST NOT raise this to callers — they should catch it
    internally and log a structured warning instead.
    """
    pass


class AdapterBase(ABC):
    """Abstract base class for transcript adapters.

    Subclasses implement two methods:
    - ``discover_sessions()`` — enumerate available sessions
    - ``normalize_session(session_id)`` — produce NormalizedEvent stream

    Both methods MUST fail soft: log a structured warning and return
    empty results when the source is unavailable.
    """

    # Subclasses set this to their harness identifier (e.g. "claude_code_cli")
    HARNESS_ID: str = ""

    # Schema version this adapter targets (vendor-specific)
    SCHEMA_VERSION: str = ""

    @abstractmethod
    def discover_sessions(self) -> list[SessionSummary]:
        """Enumerate available sessions from this adapter's source.

        Returns an empty list (with a warning log) if the source is
        unavailable.
        """
        ...

    @abstractmethod
    def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
        """Normalize a single session into NormalizedEvent instances.

        Returns an empty list (with a warning log) if the session cannot
        be parsed.
        """
        ...

    def _warn_unavailable(self, reason: str) -> None:
        """Log a structured warning about source unavailability."""
        logger.warning(
            "Adapter %s: source unavailable — %s. Skipping.",
            self.HARNESS_ID,
            reason,
        )

    def _warn_parse_error(self, session_id: str, reason: str) -> None:
        """Log a structured warning about a parse error."""
        logger.warning(
            "Adapter %s: failed to parse session %s — %s. Skipping.",
            self.HARNESS_ID,
            session_id,
            reason,
        )
