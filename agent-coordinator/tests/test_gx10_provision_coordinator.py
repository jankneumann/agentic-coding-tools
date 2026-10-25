"""provision-coordinator.sh against a fake OpenBao.

The script runs once against the real OpenBao on GX-10, by hand, with an admin
token. Each assertion here is a way that run could leave the host worse off
than before: a dropped secret, a regenerated database password, a secret id
that expires, or a key with no identity.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "gx10" / "openbao" / "provision-coordinator.sh"
RENDERER = ROOT / "deploy" / "gx10" / "openbao" / "render-coordinator-secrets.sh"

pytestmark = pytest.mark.skipif(
    not (shutil.which("jq") and shutil.which("curl")), reason="needs jq and curl"
)

TEAM = "https://rotkohl.cloudflareaccess.com"
AUD = "a" * 64


class FakeBao:
    """Just enough of OpenBao's HTTP API: KV v2 at secret/, ACL policies, one AppRole."""

    def __init__(self) -> None:
        self.kv: dict[str, dict] = {}
        self.policies: dict[str, str] = {}
        self.roles: dict[str, dict] = {}
        self.secret_ids: list[str] = []
        self.destroyed: list[str] = []
        self.minted = 0

    def handle(self, method: str, path: str, body: dict) -> tuple[int, dict]:
        path = path.removeprefix("/v1")
        if path.startswith("/sys/health"):
            return 200, {"initialized": True, "sealed": False}
        if path.startswith("/secret/data/"):
            key = path.removeprefix("/secret/data/")
            if method == "GET":
                return (200, {"data": {"data": self.kv[key]}}) if key in self.kv else (404, {})
            self.kv[key] = body["data"]
            return 200, {}
        if path.startswith("/sys/policies/acl/"):
            self.policies[path.rsplit("/", 1)[1]] = body["policy"]
            return 204, {}
        if path.endswith("/role-id"):
            return 200, {"data": {"role_id": "role-123"}}
        if path.endswith("/secret-id/destroy"):
            self.destroyed.append(body["secret_id"])
            return 204, {}
        if path.endswith("/secret-id"):
            self.minted += 1
            self.secret_ids.append(f"secret-{self.minted}")
            return 200, {"data": {"secret_id": self.secret_ids[-1]}}
        if path.startswith("/auth/approle/role/"):
            self.roles[path.rsplit("/", 1)[1]] = body
            return 204, {}
        return 404, {}


@pytest.fixture
def bao() -> Iterator[tuple[FakeBao, str]]:
    fake = FakeBao()

    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            status, payload = fake.handle(self.command, self.path, json.loads(raw or b"{}"))
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's naming
            self._serve()

        def do_POST(self) -> None:  # noqa: N802
            self._serve()

        def do_PUT(self) -> None:  # noqa: N802
            self._serve()

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield fake, f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


@pytest.fixture
def run(bao: tuple[FakeBao, str], tmp_path: Path):
    _, addr = bao
    token = tmp_path / "bootstrap-token"
    token.write_text("admin-token")

    def _run(answers: list[str], *args: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "GX10_BAO_ADDR": addr,
            "GX10_BAO_TOKEN_FILE": str(token),
            "GX10_COORD_CRED_DIR": str(tmp_path / "creds"),
            "NO_PROXY": "127.0.0.1",
            "no_proxy": "127.0.0.1",
        }
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            input="\n".join(answers) + "\n",
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    return _run


def _import_file(tmp_path: Path, identities: dict[str, dict]) -> Path:
    path = tmp_path / "railway-keys.json"
    path.write_text(json.dumps({
        "coordination_api_keys": ",".join(identities),
        "coordination_api_key_identities": json.dumps(identities),
    }))
    return path


RAILWAY = {
    "key-a": {"agent_id": "claude-local", "agent_type": "claude_code"},
    "key-b": {"agent_id": "codex-remote", "agent_type": "codex"},
}
FULL_ANSWERS = [TEAM, AUD, "pk-lf-public", "sk-lf-secret"]


def test_a_first_run_stores_every_field_the_renderer_needs(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    result = run(FULL_ANSWERS, "--import-keys", str(_import_file(tmp_path, RAILWAY)))

    assert result.returncode == 0, result.stderr
    stored = fake.kv["coordinator/gx10/runtime"]
    for field in ("postgres_password", "coordination_api_keys", "coordination_api_key_identities",
                  "coordination_api_key", "sse_signing_key", "cf_access_team_domain",
                  "cf_access_aud", "langfuse_public_key", "langfuse_secret_key"):
        assert stored.get(field), field
        assert field in RENDERER.read_text(), field
    assert "complete." in result.stdout


def test_imported_keys_keep_their_identities_and_gain_a_kanban_one(
    run, bao, tmp_path: Path
) -> None:
    fake, _ = bao
    run(FULL_ANSWERS, "--import-keys", str(_import_file(tmp_path, RAILWAY)))

    stored = fake.kv["coordinator/gx10/runtime"]
    keys = stored["coordination_api_keys"].split(",")
    identities = json.loads(stored["coordination_api_key_identities"])
    assert keys[:2] == ["key-a", "key-b"]
    assert sorted(keys) == sorted(identities)
    assert [i["agent_id"] for i in identities.values()].count("gx10-kanban") == 1


def test_the_outbound_key_is_not_an_accepted_key(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    run(FULL_ANSWERS, "--import-keys", str(_import_file(tmp_path, RAILWAY)))
    stored = fake.kv["coordinator/gx10/runtime"]
    assert stored["coordination_api_key"] not in stored["coordination_api_keys"].split(",")


def test_a_rerun_with_blank_answers_changes_nothing(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    run(FULL_ANSWERS, "--import-keys", str(_import_file(tmp_path, RAILWAY)))
    first = dict(fake.kv["coordinator/gx10/runtime"])

    result = run(["", "", "", ""])

    assert result.returncode == 0, result.stderr
    assert fake.kv["coordinator/gx10/runtime"] == first  # incl. postgres_password, kanban key


def test_a_key_without_an_identity_is_refused(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "coordination_api_keys": "key-a,key-orphan",
        "coordination_api_key_identities": json.dumps({"key-a": RAILWAY["key-a"]}),
    }))
    result = run(FULL_ANSWERS, "--import-keys", str(bad))
    assert result.returncode != 0
    assert "every key needs exactly one identity" in result.stderr
    assert "coordinator/gx10/runtime" not in fake.kv


def test_a_malformed_answer_is_asked_again(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    result = run(["https://rotkohl.example.com", TEAM, AUD, "pk-lf-public", "sk-lf-secret"])
    assert result.returncode == 0, result.stderr
    assert fake.kv["coordinator/gx10/runtime"]["cf_access_team_domain"] == TEAM


@pytest.mark.parametrize(
    "pasted",
    [
        "rotkohl.cloudflareaccess.com",  # how the dashboard shows it
        "https://rotkohl.cloudflareaccess.com/",
        "  https://Rotkohl.cloudflareaccess.com\r",  # a paste with a carriage return
    ],
)
def test_the_team_domain_is_accepted_as_pasted_and_stored_in_full(run, bao, pasted: str) -> None:
    fake, _ = bao
    result = run([pasted, AUD, "pk-lf-public", "sk-lf-secret"])
    assert result.returncode == 0, result.stderr
    assert fake.kv["coordinator/gx10/runtime"]["cf_access_team_domain"] == TEAM


def test_a_rejected_answer_says_what_was_expected(run, bao) -> None:
    result = run(["https://rotkohl.example.com", TEAM, AUD, "pk-lf-public", "sk-lf-secret"])
    assert result.returncode == 0, result.stderr
    assert "expected <team>.cloudflareaccess.com" in result.stderr


def test_missing_fields_are_reported_not_invented(run, bao) -> None:
    fake, _ = bao
    result = run(["", "", "", ""])
    assert result.returncode == 0, result.stderr
    assert "still missing:" in result.stdout
    assert "langfuse_secret_key" in result.stdout
    assert "cf_access_aud" not in fake.kv["coordinator/gx10/runtime"]


def test_the_approle_is_scoped_and_its_secret_id_never_expires(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    run(FULL_ANSWERS)

    role = fake.roles["aca-gx10-coordinator"]
    assert role["token_policies"] == ["aca-gx10-coordinator"]
    assert role["secret_id_ttl"] == "0"
    policy = fake.policies["aca-gx10-coordinator"]
    assert "secret/data/coordinator/gx10/runtime" in policy
    assert "newsletter" not in policy
    creds = tmp_path / "creds"
    assert (creds / "coordinator-role-id").read_text() == "role-123\n"
    assert (creds / "coordinator-secret-id").read_text() == "secret-1\n"
    for name in ("coordinator-role-id", "coordinator-secret-id"):
        assert (creds / name).stat().st_mode & 0o777 == 0o600


def test_the_secret_id_is_minted_once_and_rotated_only_on_request(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    run(FULL_ANSWERS)
    run(["", "", "", ""])
    assert fake.minted == 1

    run(["", "", "", ""], "--rotate-secret-id")

    assert fake.minted == 2
    assert fake.destroyed == ["secret-1"]
    assert (tmp_path / "creds" / "coordinator-secret-id").read_text() == "secret-2\n"


def test_no_secret_value_reaches_the_output(run, bao, tmp_path: Path) -> None:
    fake, _ = bao
    result = run(FULL_ANSWERS, "--import-keys", str(_import_file(tmp_path, RAILWAY)))
    stored = fake.kv["coordinator/gx10/runtime"]
    secret_fields = (
        "postgres_password", "sse_signing_key", "coordination_api_key", "langfuse_secret_key"
    )
    for field in secret_fields:
        assert stored[field] not in result.stdout + result.stderr, field
    for key in stored["coordination_api_keys"].split(","):
        assert key not in result.stdout + result.stderr
