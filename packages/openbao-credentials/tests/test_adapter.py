"""D2/D3 adapter contract: exact paths, wrapped bootstrap, and cache reuse."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jsonschema import Draft202012Validator

from openbao_credentials import (
    BaoCredentialError,
    ErrorCode,
    OpenBaoClient,
    PrincipalOpenBaoConfig,
    bootstrap_paths,
)


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "openspec/changes/restructure-openbao-per-agent-secrets/contracts"
PID = "spiffe://coordinator.rotkohl.ai/agent/codex-local"
ROLE = "agent-codex-local"


def protected_dir(tmp_path: Path) -> Path:
    root = tmp_path / "bootstrap"
    root.mkdir(mode=0o700)
    return root


def bundle(root: Path, *, claimed_path: str | None = None) -> None:
    payload = {
        "version": 1,
        "principal_id": PID,
        "role_name": ROLE,
        "role_id": "role-id-sensitive",
        "wrapped_secret_id": {
            "token": "wrap-sensitive",
            "creation_path": claimed_path or f"auth/approle/role/{ROLE}/secret-id",
            "creation_time": datetime.now(UTC).isoformat(),
            "ttl_seconds": 120,
        },
    }
    Draft202012Validator(json.loads((CONTRACTS / "bootstrap-bundle.schema.json").read_text())).validate(payload)
    path = bootstrap_paths(root, ROLE).bundle
    path.write_text(json.dumps(payload))
    path.chmod(0o600)


def fake_client() -> MagicMock:
    client = MagicMock()
    client.adapter.post.return_value = {
        "data": {"creation_path": f"auth/approle/role/{ROLE}/secret-id", "creation_ttl": 120}
    }
    client.sys.unwrap.return_value = {"data": {"secret_id": "secret-id-sensitive"}}
    client.auth.approle.login.return_value = {
        "auth": {"client_token": "client-sensitive", "renewable": True, "lease_duration": 3600}
    }
    return client


def adapter(root: Path, client: MagicMock) -> OpenBaoClient:
    return OpenBaoClient(PrincipalOpenBaoConfig(
        addr="http://127.0.0.1:8200", mount="secret", bootstrap_dir=root
    ), client=client)


def test_bootstrap_validates_server_lookup_before_unwrap(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    client.adapter.post.return_value = {
        "data": {"creation_path": "auth/approle/role/agent-other/secret-id"}
    }
    with pytest.raises(BaoCredentialError) as failure:
        adapter(root, client).ensure_session(PID, ROLE)
    assert failure.value.code == ErrorCode.BOOTSTRAP_INVALID
    assert "wrap-sensitive" not in str(failure.value)
    client.sys.unwrap.assert_not_called()


def test_bootstrap_reuses_protected_session_without_second_unwrap(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    first = adapter(root, client).ensure_session(PID, ROLE)
    second = adapter(root, client).ensure_session(PID, ROLE)
    assert first.client_token == second.client_token == "client-sensitive"
    client.sys.unwrap.assert_called_once_with(token="wrap-sensitive")
    cache = bootstrap_paths(root, ROLE).session
    assert cache.stat().st_mode & 0o777 == 0o600
    assert bootstrap_paths(root, ROLE).lock.stat().st_mode & 0o777 == 0o600
    Draft202012Validator(json.loads((CONTRACTS / "session-cache.schema.json").read_text())).validate(
        json.loads(cache.read_text())
    )


def test_invalid_bundle_and_file_modes_fail_closed(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    bundle(root)
    path = bootstrap_paths(root, ROLE).bundle
    path.chmod(0o644)
    with pytest.raises(BaoCredentialError) as failure:
        adapter(root, fake_client()).ensure_session(PID, ROLE)
    assert failure.value.code == ErrorCode.CONFIGURATION_INVALID


def test_expired_cache_requires_rebootstrap_not_consumed_bundle(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    bundle(root)
    cache = bootstrap_paths(root, ROLE).session
    cache.write_text(json.dumps({
        "version": 1, "principal_id": PID, "client_token": "old",
        "renewable": True, "period_seconds": 3600,
        "lease_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }))
    cache.chmod(0o600)
    client = fake_client()
    with pytest.raises(BaoCredentialError) as failure:
        adapter(root, client).ensure_session(PID, ROLE)
    assert failure.value.code == ErrorCode.TOKEN_EXPIRED
    client.sys.unwrap.assert_not_called()


def test_kv_v2_reads_only_single_api_key_payload(tmp_path: Path) -> None:
    client = fake_client()
    client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"api_key": "key-sensitive"}}
    }
    typed = adapter(protected_dir(tmp_path), client)
    assert typed.read_api_key("vendors/openai") == "key-sensitive"
    client.secrets.kv.v2.read_secret_version.assert_called_once_with(
        path="vendors/openai", mount_point="secret"
    )
    client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"api_key": "key-sensitive", "extra": "bad"}}
    }
    with pytest.raises(BaoCredentialError) as failure:
        typed.read_api_key("vendors/openai")
    assert failure.value.code == ErrorCode.SECRET_MALFORMED
    assert "key-sensitive" not in str(failure.value)


def test_path_traversal_and_symlink_rejected(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    with pytest.raises(BaoCredentialError):
        bootstrap_paths(root, "../agent-other")
    path = bootstrap_paths(root, ROLE).bundle
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(BaoCredentialError):
        adapter(root, fake_client()).ensure_session(PID, ROLE)


def test_config_requires_protected_root(tmp_path: Path) -> None:
    root = tmp_path / "world-readable"
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    with pytest.raises(BaoCredentialError) as failure:
        adapter(root, fake_client()).ensure_session(PID, ROLE)
    assert failure.value.code == ErrorCode.CONFIGURATION_INVALID
