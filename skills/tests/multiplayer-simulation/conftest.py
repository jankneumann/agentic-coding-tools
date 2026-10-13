"""Path setup and offline enforcement for the multiplayer-simulation harness.

Puts the harness root (so ``import mpsim`` works) and ``roadmap-runtime/scripts``
(so the driver can call the real admission rule) on ``sys.path``, following
``skills/tests/roadmap-runtime/conftest.py``. The autouse fixture below implements
design D9: any ``AF_INET``/``AF_INET6`` connect raises, so an accidental network
call fails the test immediately instead of hanging in CI.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parent
_RUNTIME_SCRIPTS = HARNESS_ROOT.parent.parent / "roadmap-runtime" / "scripts"

for _p in (HARNESS_ROOT, _RUNTIME_SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


class NetworkBlockedError(OSError):
    """Raised when a harness test tries to open an inet socket connection."""


_INET_FAMILIES = (socket.AF_INET, socket.AF_INET6)


@pytest.fixture(autouse=True)
def _block_inet_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(self: socket.socket, *args: object, **kwargs: object) -> None:
        if self.family in _INET_FAMILIES:
            raise NetworkBlockedError(
                "network access is blocked in multiplayer-simulation tests (design D9)"
            )
        raise AssertionError("non-inet connect is not expected in this harness")

    def _wrap(original):
        def patched(self: socket.socket, *args: object, **kwargs: object):
            if self.family in _INET_FAMILIES:
                return _blocked(self, *args, **kwargs)
            return original(self, *args, **kwargs)

        return patched

    monkeypatch.setattr(socket.socket, "connect", _wrap(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _wrap(socket.socket.connect_ex))
