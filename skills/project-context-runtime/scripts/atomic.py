"""Atomic, crash-safe persistence and advisory file locking.

Runtime-core infrastructure for ``project-context-runtime``. Both the durable
operation store and the deterministic manifest writer build on these
primitives so that:

* concurrent writers never observe a partial file (same-directory temp file +
  ``os.replace`` + parent-directory fsync);
* a same-revision rewrite is a byte-observable no-op (``atomic_write_bytes``
  returns ``False`` and never touches the target); and
* mutations on one operation serialize across processes and linked worktrees
  (``file_lock`` uses a cross-process advisory ``flock``).

This is a private module. Consumers import through the package facade
(``skills.project-context-runtime.scripts``), not directly.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize *data* to canonical UTF-8 JSON bytes.

    Canonical form is sorted object keys, two-space indentation, and exactly
    one trailing newline. The same logical structure always produces identical
    bytes, which is what makes same-revision manifest rewrites observable
    no-ops.
    """
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
    return (text + "\n").encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *payload*."""
    return hashlib.sha256(payload).hexdigest()


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of *directory* so a rename is durably recorded."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        # Some filesystems (notably a few network mounts) reject directory
        # fsync. The atomic ``os.replace`` still provides crash-atomicity for
        # the target file itself, so this is non-fatal.
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(target: Path, payload: bytes) -> bool:
    """Atomically write *payload* to *target*; return whether bytes changed.

    Returns ``False`` without touching the filesystem when *target* already
    contains exactly *payload*. Otherwise the bytes are written to a
    same-directory temporary file, flushed, fsynced, atomically renamed over
    *target*, and the parent directory is fsynced. A failure before the rename
    removes the temporary file and re-raises.
    """
    target = Path(target)
    if target.exists():
        try:
            if target.read_bytes() == payload:
                return False
        except OSError:
            # Fall through and rewrite if the existing file cannot be read.
            pass

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    # A temp file in the same directory keeps ``os.replace`` on one filesystem,
    # which is the precondition for an atomic rename.
    fd, tmp_name = tempfile.mkstemp(dir=str(parent), prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    _fsync_dir(parent)
    return True


def atomic_write_json(target: Path, data: Any) -> tuple[bool, str]:
    """Atomically persist *data* as canonical JSON.

    Returns ``(changed, sha256_hex)`` where *changed* is ``False`` for a
    byte-for-byte no-op rewrite. The digest is over the canonical bytes that
    are (or already were) on disk.
    """
    payload = canonical_json_bytes(data)
    changed = atomic_write_bytes(Path(target), payload)
    return changed, sha256_hex(payload)


def read_json(source: Path) -> Any:
    """Read and parse a JSON document, raising ``json.JSONDecodeError`` on a
    truncated or malformed file so callers can fail closed."""
    return json.loads(Path(source).read_text(encoding="utf-8"))


@contextlib.contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive cross-process advisory lock on *lock_path*.

    Uses ``fcntl.flock`` so separate processes and linked worktrees in the same
    clone serialize on one operation. The lock file is created if absent and
    intentionally left in place afterwards; its presence is not state.
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
