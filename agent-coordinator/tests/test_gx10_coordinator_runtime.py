"""Behaviour of deploy/gx10/coordinator-runtime.sh against stand-in podman binaries.

Both binaries only append their argv to a shared log, so a test reads the
order of operations the script performed -- the thing that matters here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "gx10" / "coordinator-runtime.sh"

# `ps` reports one leftover container; `inspect` reports every service healthy.
# `network exists` fails until it has been asked $NETWORK_AFTER times, standing
# in for an analyzer that is still bringing its networks up.
FAKE_PODMAN = """#!/usr/bin/env bash
echo "podman $*" >>"$CALLS"
case "$1" in
  ps) echo leftover-id ;;
  inspect) echo healthy ;;
  network)
    asked=$(grep -c '^podman network exists' "$CALLS")
    ((asked > ${NETWORK_AFTER:-0})) ;;
esac
"""
FAKE_COMPOSE = """#!/usr/bin/env bash
echo "compose $*" >>"$CALLS"
"""


def _run(tmp_path: Path, action: str, network_after: int = 0, check: bool = True) -> list[str]:
    calls = tmp_path / "calls"
    for name, body in (("podman", FAKE_PODMAN), ("podman-compose", FAKE_COMPOSE)):
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    subprocess.run(
        ["bash", str(SCRIPT), action],
        env={
            "PATH": "/usr/bin:/bin",
            "CALLS": str(calls),
            "COORD_PODMAN_BIN": str(tmp_path / "podman"),
            "COORD_COMPOSE_BIN": str(tmp_path / "podman-compose"),
            "NETWORK_AFTER": str(network_after),
            "COORD_NETWORK_WAIT_SECONDS": "2",
            "COORD_NETWORK_RETRY_INTERVAL": "0",
        },
        check=check,
        capture_output=True,
        text=True,
    )
    return calls.read_text(encoding="utf-8").splitlines()


def _index(calls: list[str], prefix: str) -> int:
    return next(i for i, call in enumerate(calls) if call.startswith(prefix))


def test_up_recreates_containers_a_failed_start_left_behind(tmp_path: Path) -> None:
    """A failed start keeps its containers for a post-mortem. Given the same
    names, podman-compose 1.0.6 falls back to `podman start` and revives them
    as they were created -- old healthcheck, old image -- instead of from the
    current compose file."""
    calls = _run(tmp_path, "up")
    assert _index(calls, "podman rm -f") < _index(calls, "compose -p aca-gx10-coord")
    assert "leftover-id" in calls[_index(calls, "podman rm -f")]


def test_down_removes_the_project_containers(tmp_path: Path) -> None:
    calls = _run(tmp_path, "down")
    assert any(call.startswith("podman rm -f") and "leftover-id" in call for call in calls)
    assert not any(call.startswith("compose") for call in calls)


def test_up_waits_for_the_analyzers_network(tmp_path: Path) -> None:
    """At boot the analyzer may still be creating `aca-gx10_application`. A
    coordinator that fails at once there stays down until someone notices."""
    calls = _run(tmp_path, "up", network_after=3)
    asked = [c for c in calls if c.startswith("podman network exists aca-gx10_application")]
    assert len(asked) == 4
    assert _index(calls, "compose -p aca-gx10-coord") > _index(calls, "podman network exists")


def test_up_gives_up_on_a_network_that_never_appears(tmp_path: Path) -> None:
    calls = _run(tmp_path, "up", network_after=10**9, check=False)
    assert not any(call.startswith("compose") for call in calls)
