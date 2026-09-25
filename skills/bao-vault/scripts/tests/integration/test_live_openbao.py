"""Real OpenBao policy, wrapping, and coordinator identity conformance."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import hvac
import pytest
import yaml
from openbao_credentials import BaoCredentialError, ErrorCode, OpenBaoClient, PrincipalOpenBaoConfig, bootstrap_paths

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "skills/bao-vault/scripts"))
sys.path.insert(0, str(ROOT / "agent-coordinator"))

from bao_seed import apply_reconciliation, plan_reconciliation  # noqa: E402
from src.agents_config import AgentEntry  # noqa: E402
from src.openbao_identity import IdentityRuntime  # noqa: E402


def _agent(name: str) -> AgentEntry:
    return AgentEntry(name=name, type="codex", profile=name, trust_level=1,
                      transport="http", capabilities=[], description="", api_key="${KEY}")


@pytest.fixture
def live(tmp_path_factory: pytest.TempPathFactory):
    addr = os.environ["BAO_ADDR"]
    root = hvac.Client(url=addr, token=os.environ["BAO_TOKEN"])
    assert root.is_authenticated(), "live runner must provide authenticated OpenBao"
    directory = tmp_path_factory.mktemp("bao-private")
    directory.chmod(0o700)
    registry = {
        "credential_vendors": ["anthropic", "openai"],
        "agents": {
            "alice": {"api_key": "${ALICE_KEY}", "vendor_credentials": ["anthropic"]},
            "bob": {"api_key": "${BOB_KEY}", "vendor_credentials": ["openai"]},
        },
    }
    migration = {"version": 1, "agents": {"alice": "ALICE_KEY", "bob": "BOB_KEY"},
                 "vendors": {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"},
                 "retained_internal": []}
    values = {"ALICE_KEY": "alice-secret", "BOB_KEY": "bob-secret",
              "ANTHROPIC_API_KEY": "anthropic-secret", "OPENAI_API_KEY": "openai-secret"}
    paths = []
    for name, value in (("agents", registry), ("migration", migration), ("secrets", values)):
        path = directory / f"{name}.yaml"
        path.write_text(yaml.safe_dump(value), encoding="utf-8")
        path.chmod(0o600)
        paths.append(path)
    plan = plan_reconciliation(paths[0], paths[2], paths[1], directory)
    events = []
    apply_reconciliation(root, plan, audit=events.append)
    assert events and all(record["outcome"] == "success" for record in events)
    return root, directory, plan


def _reader(live, role_name: str) -> OpenBaoClient:
    root, directory, _ = live
    return OpenBaoClient(PrincipalOpenBaoConfig(addr=root.url, bootstrap_dir=directory))


def _principal(live, role_name: str):
    return next(p for p in live[2].topology.principals if p.role_name == role_name)


def _login(live, role_name: str) -> OpenBaoClient:
    principal = _principal(live, role_name)
    reader = _reader(live, role_name)
    reader.ensure_session(principal.principal_id, principal.role_name)
    return reader


def _fresh_bundle(live, role_name: str) -> None:
    root, directory, _ = live
    principal = _principal(live, role_name)
    response = root.auth.approle.generate_secret_id(role_name=role_name, wrap_ttl="300s")
    wrapped = response["wrap_info"]
    bundle = {"version": 1, "principal_id": principal.principal_id,
              "role_name": role_name,
              "role_id": root.auth.approle.read_role_id(role_name=role_name)["data"]["role_id"],
              "wrapped_secret_id": {"token": wrapped["token"],
                                    "creation_path": wrapped["creation_path"],
                                    "creation_time": wrapped["creation_time"],
                                    "ttl_seconds": wrapped["ttl"]}}
    path = bootstrap_paths(directory, role_name).bundle
    path.write_text(json.dumps(bundle), encoding="utf-8")
    path.chmod(0o600)


def test_exact_agent_and_service_policy_isolation(live) -> None:
    alice = _login(live, "agent-alice")
    bob = _login(live, "agent-bob")
    identity = _login(live, "service-identity-reader")
    gateway = _login(live, "service-egress-gateway")
    assert alice.read_agent_key("alice") == "alice-secret"
    assert alice.read_vendor_key("anthropic") == "anthropic-secret"
    assert bob.read_agent_key("bob") == "bob-secret"
    assert bob.read_vendor_key("openai") == "openai-secret"
    assert identity.read_agent_key("alice") == "alice-secret"
    assert identity.read_agent_key("bob") == "bob-secret"
    assert gateway.read_vendor_key("anthropic") == "anthropic-secret"
    assert gateway.read_vendor_key("openai") == "openai-secret"
    for client, path in ((alice, "agents/bob"), (alice, "vendors/openai"),
                         (bob, "agents/alice"), (bob, "vendors/anthropic"),
                         (identity, "vendors/anthropic"), (gateway, "agents/alice")):
        with pytest.raises(BaoCredentialError) as error:
            client.read_api_key(path)
        assert error.value.code == ErrorCode.AUTHORIZATION_DENIED
    for client in (alice, bob, identity, gateway):
        with pytest.raises(hvac.exceptions.Forbidden):
            client.client.secrets.kv.v2.create_or_update_secret(
                path="agents/alice", secret={"api_key": "overwrite"}, mount_point="secret")
        with pytest.raises(hvac.exceptions.Forbidden):
            client.client.secrets.kv.v2.list_secrets(path="", mount_point="secret")


def test_wrap_lookup_replay_and_fresh_recovery(live) -> None:
    root, directory, _ = live
    principal = _principal(live, "agent-alice")
    paths = bootstrap_paths(directory, principal.role_name)
    reader = _login(live, principal.role_name)
    first = reader.ensure_session(principal.principal_id, principal.role_name)
    assert first.client_token
    assert paths.session.stat().st_mode & 0o777 == 0o600
    assert paths.bundle.stat().st_mode & 0o777 == 0o600
    root.auth.token.revoke(token=first.client_token)
    with pytest.raises(BaoCredentialError) as error:
        _reader(live, principal.role_name).ensure_session(principal.principal_id, principal.role_name)
    assert error.value.code == ErrorCode.TOKEN_EXPIRED
    _fresh_bundle(live, principal.role_name)
    recovered = _reader(live, principal.role_name).ensure_session(principal.principal_id, principal.role_name)
    assert recovered.client_token != first.client_token
    assert recovered.bootstrap_token_sha256 != first.bootstrap_token_sha256
    assert _reader(live, principal.role_name).ensure_session(principal.principal_id, principal.role_name).client_token == recovered.client_token
    root.auth.token.revoke(token=recovered.client_token)
    with pytest.raises(BaoCredentialError) as error:
        _reader(live, principal.role_name).ensure_session(principal.principal_id, principal.role_name)
    assert error.value.code == ErrorCode.TOKEN_EXPIRED


def test_wrap_forgery_rejected_before_unwrap(live) -> None:
    root, directory, _ = live
    role_name = "agent-bob"
    principal = _principal(live, role_name)
    paths = bootstrap_paths(directory, role_name)
    _login(live, role_name)
    old_session = paths.session.read_bytes()
    paths.session.unlink()
    try:
        _fresh_bundle(live, role_name)
        bundle = json.loads(paths.bundle.read_text(encoding="utf-8"))
        real_token = bundle["wrapped_secret_id"]["token"]
        bundle["wrapped_secret_id"]["creation_path"] = "auth/approle/role/agent-alice/secret-id"
        paths.bundle.write_text(json.dumps(bundle), encoding="utf-8")
        with pytest.raises(BaoCredentialError) as error:
            _reader(live, role_name).ensure_session(principal.principal_id, role_name)
        assert error.value.code == ErrorCode.BOOTSTRAP_INVALID
        # The server still knows the token: local creation-path check preceded unwrap.
        assert root.adapter.post("/v1/sys/wrapping/lookup", json={"token": real_token})["data"]["creation_path"] == f"auth/approle/role/{role_name}/secret-id"
        bundle["wrapped_secret_id"]["creation_path"] = f"auth/approle/role/{role_name}/secret-id"
        paths.bundle.write_text(json.dumps(bundle), encoding="utf-8")
        assert _reader(live, role_name).ensure_session(principal.principal_id, role_name).client_token
    finally:
        paths.session.write_bytes(old_session)
        paths.session.chmod(0o600)


def test_server_side_wrap_creation_path_rejected(live) -> None:
    root, directory, _ = live
    role_name = "service-egress-gateway"
    principal = _principal(live, role_name)
    paths = bootstrap_paths(directory, role_name)
    _login(live, role_name)
    prior_session = paths.session.read_bytes()
    prior_bundle = paths.bundle.read_bytes()
    paths.session.unlink()
    try:
        forged = root.sys.wrap(payload={"secret_id": "forged"}, ttl=300)["wrap_info"]
        bundle = json.loads(prior_bundle)
        bundle["wrapped_secret_id"] = {
            "token": forged["token"],
            "creation_path": f"auth/approle/role/{role_name}/secret-id",
            "creation_time": forged["creation_time"], "ttl_seconds": forged["ttl"],
        }
        paths.bundle.write_text(json.dumps(bundle), encoding="utf-8")
        paths.bundle.chmod(0o600)
        with pytest.raises(BaoCredentialError) as error:
            _reader(live, role_name).ensure_session(principal.principal_id, role_name)
        assert error.value.code == ErrorCode.BOOTSTRAP_INVALID
        assert root.adapter.post("/v1/sys/wrapping/lookup", json={"token": forged["token"]})["data"]["creation_path"] == "sys/wrapping/wrap"
    finally:
        paths.session.write_bytes(prior_session)
        paths.session.chmod(0o600)
        paths.bundle.write_bytes(prior_bundle)
        paths.bundle.chmod(0o600)


def test_langfuse_internal_role_only_reads_coordinator(live) -> None:
    root, _, _ = live
    root.secrets.kv.v2.create_or_update_secret(path="coordinator", mount_point="secret",
        secret={"LANGFUSE_PUBLIC_KEY": "public-live", "LANGFUSE_SECRET_KEY": "secret-live",
                "LANGFUSE_HOST": "https://langfuse.test"})
    root.sys.create_or_update_policy(name="coordinator-internal-read",
        policy='path "secret/data/coordinator" { capabilities = ["read"] }')
    root.auth.approle.create_or_update_approle(role_name="coordinator-internal",
        token_policies=["coordinator-internal-read"])
    role_id = root.auth.approle.read_role_id(role_name="coordinator-internal")["data"]["role_id"]
    secret_id = root.auth.approle.generate_secret_id(role_name="coordinator-internal")["data"]["secret_id"]
    auth = root.auth.approle.login(role_id=role_id, secret_id=secret_id, use_token=False)["auth"]
    internal = hvac.Client(url=root.url, token=auth["client_token"])
    assert internal.secrets.kv.v2.read_secret_version(path="coordinator", mount_point="secret", raise_on_deleted_version=True)["data"]["data"]["LANGFUSE_PUBLIC_KEY"] == "public-live"
    with pytest.raises(hvac.exceptions.Forbidden):
        internal.secrets.kv.v2.read_secret_version(path="agents/alice", mount_point="secret", raise_on_deleted_version=True)
    helper = ROOT / "skills/bao-vault/scripts/langfuse_env.sh"
    env = {**os.environ, "BAO_ADDR": root.url, "BAO_INTERNAL_ROLE_ID": role_id,
           "BAO_INTERNAL_SECRET_ID": secret_id, "BAO_TOKEN": "", "BAO_ROLE_ID": "legacy-wrong",
           "BAO_SECRET_ID": "legacy-wrong", "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "",
           "LANGFUSE_HOST": ""}
    result = subprocess.run(["bash", str(helper)], env=env, capture_output=True, text=True, check=True)
    assert "LANGFUSE_PUBLIC_KEY=public-live" in result.stdout
    assert "LANGFUSE_SECRET_KEY=secret-live" in result.stdout
    assert "legacy-wrong" not in result.stdout + result.stderr


def test_coordinator_live_snapshot_rotation_and_readiness(live) -> None:
    root, directory, _ = live
    # The identity reader has already bootstrapped; each reload is a real Bao read.
    runtime = IdentityRuntime(
        lambda: OpenBaoClient(PrincipalOpenBaoConfig(addr=root.url, bootstrap_dir=directory)),
        lambda: [_agent("alice"), _agent("bob")],
    )
    assert runtime.reload()
    assert runtime.readiness() == ("ready", True)
    assert runtime.lookup("alice-secret") == {"agent_id": "alice", "agent_type": "codex"}
    root.secrets.kv.v2.create_or_update_secret(path="agents/alice", secret={"api_key": "alice-rotated"}, mount_point="secret")
    try:
        assert runtime.reload()
        assert runtime.lookup("alice-secret") is None
        assert runtime.lookup("alice-rotated") is not None
        root.secrets.kv.v2.create_or_update_secret(path="agents/bob", secret={"api_key": "alice-rotated"}, mount_point="secret")
        assert not runtime.reload()
        assert runtime.readiness() == ("degraded", True)
        assert runtime.lookup("alice-rotated") is not None
    finally:
        root.secrets.kv.v2.create_or_update_secret(path="agents/alice", secret={"api_key": "alice-secret"}, mount_point="secret")
        root.secrets.kv.v2.create_or_update_secret(path="agents/bob", secret={"api_key": "bob-secret"}, mount_point="secret")


def test_periodic_token_renews_past_auth_mount_max_ttl(live) -> None:
    root, directory, _ = live
    role_name = "agent-renewal"
    principal_id = "spiffe://coordinator.rotkohl.ai/agent/renewal"
    prior_max_ttl = root.sys.read_auth_method_tuning(path="approle")["data"]["max_lease_ttl"]
    root.sys.tune_auth_method(path="approle", max_lease_ttl="5s")
    try:
        root.auth.approle.create_or_update_approle(
            role_name=role_name, token_policies=["agent-alice"],
            token_period="4s", token_max_ttl="0s", secret_id_num_uses=1,
        )
        role_id = root.auth.approle.read_role_id(role_name=role_name)["data"]["role_id"]
        wrap = root.auth.approle.generate_secret_id(role_name=role_name, wrap_ttl="300s")["wrap_info"]
        bundle = {"version": 1, "principal_id": principal_id, "role_name": role_name,
                  "role_id": role_id, "wrapped_secret_id": {
                      "token": wrap["token"], "creation_path": wrap["creation_path"],
                      "creation_time": wrap["creation_time"], "ttl_seconds": wrap["ttl"]}}
        path = bootstrap_paths(directory, role_name).bundle
        path.write_text(json.dumps(bundle), encoding="utf-8")
        path.chmod(0o600)
        reader = _reader(live, role_name)
        initial = reader.ensure_session(principal_id, role_name)
        assert initial.period_seconds == 4
        for _ in range(3):
            time.sleep(2.0)
            renewed = _reader(live, role_name).ensure_session(principal_id, role_name)
            assert renewed.client_token == initial.client_token
            assert renewed.lease_expires_at > initial.lease_expires_at
        after_mount_max = _reader(live, role_name)
        after_mount_max.ensure_session(principal_id, role_name)
        assert after_mount_max.read_agent_key("alice") == "alice-secret"
    finally:
        root.sys.tune_auth_method(path="approle", max_lease_ttl=f"{prior_max_ttl}s")
