"""login-coordinator-approle.sh against an OpenBao that is briefly unavailable.

On 2026-11-08 an analyzer restart restarted OpenBao too. The secrets unit tried
to log in during that window, got one 503, and failed. The coordinator requires
that unit, so it failed with result 'dependency' and stayed down for a day
after OpenBao was healthy again. A unit-level Restart= cannot fix this: the
dependent job has already failed by the time the restart succeeds. The wait
has to happen inside the login.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "gx10" / "openbao" / "login-coordinator-approle.sh"
UNIT = ROOT / "deploy" / "gx10" / "systemd" / "aca-gx10-coordinator-secrets.service"

# The script calls both by absolute path, as the unit's sandbox expects.
pytestmark = pytest.mark.skipif(
    not (Path("/usr/bin/jq").exists() and Path("/usr/bin/curl").exists()),
    reason="needs /usr/bin/jq and /usr/bin/curl",
)


class ScriptedBao:
    """Answers AppRole logins from a script of HTTP statuses, then succeeds."""

    def __init__(self, statuses: list[int]) -> None:
        self.statuses = list(statuses)
        self.logins = 0

    def answer(self) -> tuple[int, dict]:
        self.logins += 1
        if self.statuses:
            return self.statuses.pop(0), {"errors": ["unavailable"]}
        return 200, {"auth": {"client_token": "s.token-from-bao"}}


def _start(fake: ScriptedBao, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — http.server's naming
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            status, body = fake.answer()
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _serve(fake: ScriptedBao) -> Iterator[str]:
    server = _start(fake)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()


@pytest.fixture
def login(tmp_path: Path):
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / "coord-role-id").write_text("role-123")
    (creds / "coord-secret-id").write_text("secret-456")
    runtime = tmp_path / "run"

    def _login(addr: str, wait_seconds: int = 30) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "CREDENTIALS_DIRECTORY": str(creds),
            "GX10_RUNTIME_DIR": str(runtime),
            "GX10_BAO_ADDR": addr,
            "GX10_BAO_WAIT_SECONDS": str(wait_seconds),
            "GX10_BAO_RETRY_INTERVAL": "0",
        }
        return subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
        )

    _login.token_file = runtime / "coordinator-openbao-token"  # type: ignore[attr-defined]
    return _login


@pytest.mark.parametrize("statuses", [[503], [503, 503, 502]])
def test_a_sealed_or_restarting_bao_is_waited_out(login, statuses: list[int]) -> None:
    fake = ScriptedBao(statuses)
    addr = next(gen := _serve(fake))
    try:
        result = login(addr)
    finally:
        gen.close()

    assert result.returncode == 0, result.stderr
    assert fake.logins == len(statuses) + 1
    assert login.token_file.read_text() == "s.token-from-bao"


def test_a_refused_connection_is_waited_out(login) -> None:
    # Nothing listens yet, as while the OpenBao container restarts; the server
    # comes up while the script is retrying.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    late: list[ThreadingHTTPServer] = []
    timer = threading.Timer(1.0, lambda: late.append(_start(ScriptedBao([]), port)))
    timer.start()
    try:
        result = login(f"http://127.0.0.1:{port}/v1")
    finally:
        timer.join()
        for server in late:
            server.shutdown()

    assert result.returncode == 0, result.stderr
    assert login.token_file.read_text() == "s.token-from-bao"


@pytest.mark.parametrize("status", [400, 403])
def test_a_rejected_credential_fails_at_once(login, status: int) -> None:
    fake = ScriptedBao([status])
    addr = next(gen := _serve(fake))
    try:
        result = login(addr)
    finally:
        gen.close()

    assert result.returncode != 0
    assert fake.logins == 1
    assert f"HTTP {status}" in result.stderr
    assert not login.token_file.exists()


def test_the_wait_is_bounded(login) -> None:
    fake = ScriptedBao([503] * 1000)
    addr = next(gen := _serve(fake))
    try:
        result = login(addr, wait_seconds=1)
    finally:
        gen.close()

    assert result.returncode != 0
    assert "HTTP 503" in result.stderr
    assert not login.token_file.exists()


def test_no_credential_or_token_reaches_the_output(login) -> None:
    fake = ScriptedBao([503])
    addr = next(gen := _serve(fake))
    try:
        result = login(addr)
    finally:
        gen.close()

    for value in ("role-123", "secret-456", "s.token-from-bao"):
        assert value not in result.stdout + result.stderr


def test_the_unit_gives_the_login_time_to_wait() -> None:
    # A oneshot's start timeout is infinite unless set; an explicit one must
    # outlast the script's default wait, or systemd kills a login that would
    # have succeeded.
    unit = UNIT.read_text()
    timeout = re.search(r"^TimeoutStartSec=(\d+)s?$", unit, re.MULTILINE)
    default_wait = re.search(r'GX10_BAO_WAIT_SECONDS:-(\d+)', SCRIPT.read_text())
    assert timeout and default_wait
    assert int(timeout.group(1)) > int(default_wait.group(1))
