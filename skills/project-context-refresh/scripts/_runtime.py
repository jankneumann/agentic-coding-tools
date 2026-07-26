"""Bootstrap and re-export the ri-06 ``project-context-runtime`` facade (ri-05 D2).

ri-05 is an *adapter* layer: it imports the canonical ``ProducerResult`` and its
value objects from the sibling ``project-context-runtime`` skill and never
copies, narrows, or extends them. This module centralizes the one ``sys.path``
insertion that makes the runtime's bare modules importable, matching the
convention ri-04's ``context_runtime_adapter`` established.

Import from here (``from _runtime import ProducerResult, ...``) so every ri-05
module shares a single runtime-resolution point.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The runtime lives at ``skills/project-context-runtime/scripts`` relative to
# this file (``skills/project-context-refresh/scripts/_runtime.py``). parents[2]
# is the ``skills/`` root in the canonical checkout and in every install target.
_RUNTIME_SCRIPTS = Path(__file__).resolve().parents[2] / "project-context-runtime" / "scripts"
if _RUNTIME_SCRIPTS.is_dir() and str(_RUNTIME_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SCRIPTS))

# ri-06 canonical types — imported, never redefined.
from models import (  # noqa: E402
    ChangeKind,
    ContextRefreshError,
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    RecordValidationError,
    Remediation,
    RepositoryArtifact,
    SafeError,
    UnsafePathError,
    ValidationResult,
    ValidationStatus,
    ensure_git_revision,
    ensure_repository_relative,
    is_safe_repository_path,
)

# ri-06 canonical deterministic serialization + digest helpers. The ``atomic``
# module is runtime-core infrastructure; ri-05 uses only these pure helpers and
# never its durable-store writers (ri-07 owns durable persistence).
from atomic import canonical_json_bytes, sha256_hex  # noqa: E402

RUNTIME_SCRIPTS_DIR = _RUNTIME_SCRIPTS

__all__ = [
    "RUNTIME_SCRIPTS_DIR",
    "ChangeKind",
    "ContextRefreshError",
    "Fallback",
    "FallbackKind",
    "ProducerResult",
    "ProducerStatus",
    "RecordValidationError",
    "Remediation",
    "RepositoryArtifact",
    "SafeError",
    "UnsafePathError",
    "ValidationResult",
    "ValidationStatus",
    "ensure_git_revision",
    "ensure_repository_relative",
    "is_safe_repository_path",
    "canonical_json_bytes",
    "sha256_hex",
]
