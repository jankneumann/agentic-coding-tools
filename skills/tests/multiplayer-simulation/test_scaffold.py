"""Scaffold sanity: the offline guard is active and the launcher is wired (D2, D9)."""

from __future__ import annotations

import socket
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent


def test_inet_connect_is_blocked():
    """O.1/O.3: a connect to 127.0.0.1:9 raises under the autouse fixture."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(OSError, match="blocked"):
            s.connect(("127.0.0.1", 9))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(OSError, match="blocked"):
            s.connect_ex(("127.0.0.1", 9))


def test_inet6_connect_is_blocked():
    """AF_INET6 is covered through a stand-in `self`, since some hosts lack IPv6 sockets."""
    fake = types.SimpleNamespace(family=socket.AF_INET6)
    with pytest.raises(OSError, match="blocked"):
        socket.socket.connect(fake, ("::1", 9))
    with pytest.raises(OSError, match="blocked"):
        socket.socket.connect_ex(fake, ("::1", 9))


def test_launcher_is_executable_and_imports_package():
    launcher = HARNESS / "bin" / "mpsim"
    assert launcher.stat().st_mode & stat.S_IXUSR
    out = subprocess.run(
        [sys.executable, "-c", "import mpsim, mpsim.errors, mpsim.scenarios"],
        cwd=HARNESS, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr


def test_scenario_registry_discovers_nothing_yet_or_sorted():
    from mpsim.scenarios import scenario_ids

    ids = scenario_ids()
    assert ids == sorted(ids)
