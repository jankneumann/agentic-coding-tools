"""D2/D3 adapter contract: exact paths, wrapped bootstrap, and cache reuse."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jsonschema import Draft202012Validator
from openspec_paths import change_dir, repo_root_from
from openbao_credentials import (
    BaoCredentialError,
    ErrorCode,
    OpenBaoClient,
    PrincipalOpenBaoConfig,
    bootstrap_paths,
)

CONTRACTS = change_dir(repo_root_from(__file__, 3), "restructure-openbao-per-agent-secrets") / "contracts"
PID = "spiffe://coordinator.rotkohl.ai/agent/codex-local"
ROLE = "agent-codex-local"


def protected_dir(tmp_path: Path) -> Path:
    root = tmp_path / "bootstrap"
    root.mkdir(mode=0o700)
    return root


def bundle(root: Path, *, token: str = "wrap-sensitive", claimed_path: str | None = None) -> None:
    payload = {
        "version": 1,
        "principal_id": PID,
        "role_name": ROLE,
        "role_id": "role-id-sensitive",
        "wrapped_secret_id": {
            "token": token,
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
    client.auth.token.lookup_self.return_value = {
        "data": {"ttl": 3600, "renewable": True}
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
    client.sys.unwrap.assert_called_once_with()
    client.auth.token.lookup_self.assert_called_once_with()
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
        "bootstrap_token_sha256": hashlib.sha256(b"wrap-sensitive").hexdigest(),
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
    assert "key-sensitive" not in repr(typed.read_vendor_secret("openai"))
    client.secrets.kv.v2.read_secret_version.assert_called_with(
        path="vendors/openai", mount_point="secret", raise_on_deleted_version=True
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


def test_mount_preflight_requires_kv_v2(tmp_path: Path) -> None:
    client = fake_client()
    typed = adapter(protected_dir(tmp_path), client)
    client.sys.list_mounted_secrets_engines.return_value = {
        "data": {"secret/": {"type": "kv", "options": {"version": "1"}}}
    }
    with pytest.raises(BaoCredentialError) as failure:
        typed.verify_kv_v2_mount()
    assert failure.value.code == ErrorCode.CONFIGURATION_INVALID
    client.sys.list_mounted_secrets_engines.return_value["data"]["secret/"]["options"]["version"] = "2"
    typed.verify_kv_v2_mount()


def test_error_codes_distinguish_policy_and_missing_secret(tmp_path: Path) -> None:
    import hvac
    import requests.exceptions

    client = fake_client()
    typed = adapter(protected_dir(tmp_path), client)
    for exception, expected in (
        (hvac.exceptions.Forbidden(), ErrorCode.AUTHORIZATION_DENIED),
        (hvac.exceptions.InvalidPath(), ErrorCode.SECRET_NOT_FOUND),
        (TimeoutError(), ErrorCode.TIMEOUT),
        (requests.exceptions.Timeout("backend detail sensitive"), ErrorCode.TIMEOUT),
    ):
        client.secrets.kv.v2.read_secret_version.side_effect = exception
        with pytest.raises(BaoCredentialError) as failure:
            typed.read_vendor_key("openai")
        assert failure.value.code == expected
        assert "backend detail sensitive" not in str(failure.value)


def test_session_renews_under_lock(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    cache = bootstrap_paths(root, ROLE).session
    cache.write_text(json.dumps({
        "version": 1, "principal_id": PID, "client_token": "old-sensitive",
        "renewable": True, "period_seconds": 3600,
        "lease_expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        "bootstrap_token_sha256": hashlib.sha256(b"old-wrap").hexdigest(),
    }))
    cache.chmod(0o600)
    client = fake_client()
    client.auth.token.renew_self.return_value = {
        "auth": {"client_token": "renewed-sensitive", "renewable": True, "lease_duration": 3600}
    }
    client.auth.token.lookup_self.return_value = {"data": {"ttl": 30, "renewable": True}}
    session = adapter(root, client).ensure_session(PID, ROLE)
    assert session.client_token == "renewed-sensitive"
    assert json.loads(cache.read_text())["client_token"] == "renewed-sensitive"
    client.sys.unwrap.assert_not_called()


def test_from_env_rejects_malformed_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://127.0.0.1:8200")
    monkeypatch.setenv("BAO_BOOTSTRAP_DIR", str(tmp_path))
    monkeypatch.setenv("BAO_TIMEOUT", "not-a-number")
    with pytest.raises(BaoCredentialError) as failure:
        PrincipalOpenBaoConfig.from_env()
    assert failure.value.code == ErrorCode.CONFIGURATION_INVALID


def test_expired_cache_recovers_only_from_fresh_bundle(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    typed = adapter(root, client)
    first = typed.ensure_session(PID, ROLE)
    cache = bootstrap_paths(root, ROLE).session
    expired = first.to_dict()
    expired["lease_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    cache.write_text(json.dumps(expired))
    cache.chmod(0o600)
    bundle(root, token="new-wrap-sensitive")
    client.sys.unwrap.return_value = {"data": {"secret_id": "new-secret-id"}}
    client.auth.approle.login.return_value = {
        "auth": {"client_token": "new-client-sensitive", "renewable": True, "lease_duration": 3600}
    }
    client.adapter.post.return_value = {
        "data": {"creation_path": f"auth/approle/role/{ROLE}/secret-id"}
    }
    recovered = typed.ensure_session(PID, ROLE)
    assert recovered.client_token == "new-client-sensitive"
    assert recovered.bootstrap_token_sha256 != first.bootstrap_token_sha256
    assert client.sys.unwrap.call_count == 2
    assert json.loads(cache.read_text())["bootstrap_token_sha256"] == recovered.bootstrap_token_sha256


def test_consumed_bundle_is_rejected_before_unwrap(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    typed = adapter(root, client)
    first = typed.ensure_session(PID, ROLE)
    cache = bootstrap_paths(root, ROLE).session
    expired = first.to_dict()
    expired["lease_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    cache.write_text(json.dumps(expired))
    with pytest.raises(BaoCredentialError) as failure:
        typed.ensure_session(PID, ROLE)
    assert failure.value.code == ErrorCode.TOKEN_EXPIRED
    assert client.sys.unwrap.call_count == 1


def test_revoked_but_locally_valid_token_requires_fresh_bundle(tmp_path: Path) -> None:
    import hvac

    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    typed = adapter(root, client)
    typed.ensure_session(PID, ROLE)
    bundle(root, token="replacement-wrap")
    client.auth.token.lookup_self.side_effect = hvac.exceptions.Unauthorized()
    client.auth.approle.login.return_value = {
        "auth": {"client_token": "replacement-client", "renewable": True, "lease_duration": 3600}
    }
    recovered = typed.ensure_session(PID, ROLE)
    assert recovered.client_token == "replacement-client"
    assert client.sys.unwrap.call_count == 2


def test_recovery_clears_revoked_client_token_before_wrapping_calls(tmp_path: Path) -> None:
    import hvac

    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    typed = adapter(root, client)
    typed.ensure_session(PID, ROLE)
    bundle(root, token="replacement-wrap")
    client.auth.token.lookup_self.side_effect = hvac.exceptions.Unauthorized()

    def lookup(*args, **kwargs):
        assert client.token is None
        assert kwargs == {"json": {"token": "replacement-wrap"}}
        return {"data": {"creation_path": f"auth/approle/role/{ROLE}/secret-id"}}

    def unwrap(*args, **kwargs):
        assert client.token == "replacement-wrap"
        assert args == () and kwargs == {}
        return {"data": {"secret_id": "replacement-secret-id"}}

    client.adapter.post.side_effect = lookup
    client.sys.unwrap.side_effect = unwrap
    recovered = typed.ensure_session(PID, ROLE)
    assert recovered.client_token == "client-sensitive"
    assert client.token == "client-sensitive"


def test_transport_failure_does_not_consume_new_bundle(tmp_path: Path) -> None:
    import requests.exceptions

    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    typed = adapter(root, client)
    typed.ensure_session(PID, ROLE)
    bundle(root, token="replacement-wrap")
    client.auth.token.lookup_self.side_effect = requests.exceptions.Timeout("raw sensitive")
    with pytest.raises(BaoCredentialError) as failure:
        typed.ensure_session(PID, ROLE)
    assert failure.value.code == ErrorCode.TIMEOUT
    assert "raw sensitive" not in str(failure.value)
    assert client.sys.unwrap.call_count == 1


def test_renewal_timeout_preserves_new_bundle(tmp_path: Path) -> None:
    import requests.exceptions

    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    typed = adapter(root, client)
    first = typed.ensure_session(PID, ROLE)
    cache = bootstrap_paths(root, ROLE).session
    near_expiry = first.to_dict()
    near_expiry["lease_expires_at"] = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    cache.write_text(json.dumps(near_expiry))
    bundle(root, token="replacement-wrap")
    client.auth.token.renew_self.side_effect = requests.exceptions.Timeout()
    client.auth.token.lookup_self.return_value = {"data": {"ttl": 30, "renewable": True}}
    with pytest.raises(BaoCredentialError) as failure:
        typed.ensure_session(PID, ROLE)
    assert failure.value.code == ErrorCode.TIMEOUT
    assert client.sys.unwrap.call_count == 1


def test_server_ttl_renews_at_half_period_on_ten_minute_cadence(tmp_path: Path) -> None:
    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    typed = adapter(root, client)
    typed.ensure_session(PID, ROLE)
    client.auth.token.renew_self.return_value = {
        "auth": {"client_token": "client-sensitive", "renewable": True, "lease_duration": 3600}
    }
    for ttl in (3000, 2400, 1800):
        client.auth.token.lookup_self.return_value = {
            "data": {"ttl": ttl, "renewable": True}
        }
        typed.ensure_session(PID, ROLE)
    client.auth.token.renew_self.assert_called_once_with()
    client.sys.unwrap.assert_called_once_with()


@pytest.mark.parametrize("stage, expected", [
    ("lookup", ErrorCode.BOOTSTRAP_INVALID),
    ("unwrap", ErrorCode.BOOTSTRAP_INVALID),
    ("login", ErrorCode.AUTHENTICATION_FAILED),
])
def test_invalid_request_is_classified_by_bootstrap_stage(
    tmp_path: Path, stage: str, expected: ErrorCode
) -> None:
    import hvac

    root = protected_dir(tmp_path)
    bundle(root)
    client = fake_client()
    error = hvac.exceptions.InvalidRequest("raw backend detail")
    if stage == "lookup":
        client.adapter.post.side_effect = error
    elif stage == "unwrap":
        client.sys.unwrap.side_effect = error
    else:
        client.auth.approle.login.side_effect = error
    with pytest.raises(BaoCredentialError) as failure:
        adapter(root, client).ensure_session(PID, ROLE)
    assert failure.value.code == expected
    assert "raw backend detail" not in str(failure.value)
