"""Tests for bao-seed.py — OpenBao bootstrap seeding script."""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add scripts directory to path for import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bao_seed import (
    _CHANGE_ID, _default_config_path, _schema_dir, _validate_schema,
    apply_reconciliation, plan_reconciliation,
    seed_approles, seed_db_engine, seed_secrets,
)


def test_portable_config_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTS_YAML", raising=False)
    assert _default_config_path("AGENTS_YAML", "agents.yaml") == tmp_path / "agents.yaml"
    configured = tmp_path / "config" / "agents.yaml"
    monkeypatch.setenv("AGENTS_YAML", str(configured))
    assert _default_config_path("AGENTS_YAML", "agents.yaml") == configured


def test_schema_lookup_survives_change_archival(tmp_path: Path) -> None:
    changes = tmp_path / "openspec" / "changes"
    archived = changes / "archive" / f"2026-09-25-{_CHANGE_ID}" / "contracts"
    archived.mkdir(parents=True)
    assert _schema_dir(tmp_path) == archived
    active = changes / _CHANGE_ID / "contracts"
    active.mkdir(parents=True)
    assert _schema_dir(tmp_path) == active


def test_schema_error_does_not_echo_secret_value() -> None:
    with pytest.raises(ValueError) as error:
        _validate_schema({"version": 1, "agents": {}, "vendors": {},
                          "retained_internal": "private-secret-value"}, "migration-map.schema.json")
    assert "private-secret-value" not in str(error.value)


def test_bao_dev_rejects_missing_inputs_before_container_start() -> None:
    coordinator = Path(__file__).resolve().parents[4] / "agent-coordinator"
    result = subprocess.run(
        ["make", "-C", str(coordinator), "bao-dev", "BAO_MIGRATION_MAP=", "BAO_BOOTSTRAP_DIR="],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "BAO_MIGRATION_MAP is required" in result.stderr
    assert "compose" not in result.stdout.lower()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _migration_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    agents = tmp_path / "agents.yaml"
    secrets = tmp_path / ".secrets.yaml"
    mapping = tmp_path / "migration.yaml"
    bootstrap = tmp_path / "bootstrap"
    _write(agents, """credential_vendors: [anthropic]
agents:
  claude-web:
    api_key: ${CLAUDE_WEB_KEY}
    vendor_credentials: [anthropic]
  endpoint:
    vendor_credentials: []
""")
    _write(secrets, "CLAUDE_WEB_KEY: agent-secret\nANTHROPIC_KEY: vendor-secret\nDB_PASSWORD: internal-secret\n")
    _write(mapping, """version: 1
agents: {claude-web: CLAUDE_WEB_KEY}
vendors: {anthropic: ANTHROPIC_KEY}
retained_internal: [DB_PASSWORD]
""")
    return agents, secrets, mapping, bootstrap


class TestMigrationReconciliation:
    def test_preflight_requires_exact_placeholder_and_source_coverage(self, tmp_path: Path) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        assert {p.role_name for p in plan.topology.principals} == {
            "agent-claude-web", "service-identity-reader", "service-egress-gateway"
        }
        assert "agent-secret" not in plan.preview()
        assert not bootstrap.exists()

        _write(mapping, "version: 1\nagents: {claude-web: ANTHROPIC_KEY}\nvendors: {anthropic: ANTHROPIC_KEY}\nretained_internal: [DB_PASSWORD]\n")
        with pytest.raises(ValueError, match="source key|placeholder|duplicate"):
            plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        _write(mapping, "version: 1\nagents: {claude-web: CLAUDE_WEB_KEY}\nvendors: {anthropic: ANTHROPIC_KEY}\nretained_internal: []\n")
        with pytest.raises(ValueError, match="unaccounted"):
            plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")

    def test_cli_dry_run_requires_explicit_map_and_bootstrap(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        from bao_seed import main

        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        monkeypatch.setattr(sys, "argv", ["bao_seed.py", "--dry-run", "--agents-path", str(agents),
                                             "--secrets-path", str(secrets), "--migration-map", str(mapping),
                                             "--bootstrap-dir", str(bootstrap)])
        monkeypatch.setattr("bao_seed._get_client", lambda: pytest.fail("dry-run must not connect to OpenBao"))
        main()
        output = capsys.readouterr().out
        assert "agent-claude-web" in output
        assert "agent-secret" not in output
        assert not bootstrap.exists()

    def test_rejects_unsafe_directory_and_fallback_expression(self, tmp_path: Path) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        bootstrap.mkdir(mode=0o755)
        with pytest.raises(ValueError, match="0700"):
            plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        bootstrap.chmod(0o700)
        _write(agents, "credential_vendors: [anthropic]\nagents: {claude-web: {api_key: '${CLAUDE_WEB_KEY:-fallback}', vendor_credentials: [anthropic]}}\n")
        with pytest.raises(ValueError, match="placeholder"):
            plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")

    def test_apply_exact_policies_wrapped_bundles_and_audit(self, tmp_path: Path) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"data": {"secret/": {"type": "kv", "options": {"version": "2"}}}}
        client.sys.list_auth_methods.return_value = {"approle/": {}}
        client.auth.approle.read_role_id.side_effect = lambda role_name: {"data": {"role_id": f"role-{role_name}"}}
        client.auth.approle.generate_secret_id.return_value = {"wrap_info": {"token": "wrapped-token", "creation_path": "auth/approle/role/agent-claude-web/secret-id", "creation_time": "2026-01-01T00:00:00Z", "ttl": 300}}
        def wrap_secret_id(**kwargs):
            role_name = kwargs["role_name"]
            return {"wrap_info": {"token": f"wrapped-{role_name}", "creation_path": f"auth/approle/role/{role_name}/secret-id", "creation_time": "2026-01-01T00:00:00Z", "ttl": 300}}
        client.auth.approle.generate_secret_id.side_effect = wrap_secret_id
        events: list[dict] = []
        apply_reconciliation(client, plan, audit=events.append)
        assert bootstrap.stat().st_mode & 0o777 == 0o700
        for principal in plan.topology.principals:
            bundle = bootstrap / f"{principal.role_name}.bundle.json"
            assert bundle.stat().st_mode & 0o777 == 0o600
            assert "wrapped-" in bundle.read_text()
        assert client.sys.create_or_update_policy.call_count == 3
        assert all(call.kwargs["secret_id_ttl"] == "600s" for call in client.auth.approle.create_or_update_approle.call_args_list)
        policies = {call.kwargs["name"]: call.kwargs["policy"] for call in client.sys.create_or_update_policy.call_args_list}
        assert policies["agent-claude-web"] == 'path "secret/data/agents/claude-web" {\n  capabilities = ["read"]\n}\npath "secret/data/vendors/anthropic" {\n  capabilities = ["read"]\n}\n'
        assert "secret/data/vendors" not in policies["service-identity-reader"]
        assert "secret/data/agents" not in policies["service-egress-gateway"]
        assert client.secrets.kv.v2.create_or_update_secret.call_count == 2
        assert all("agent-secret" not in str(e) and "wrapped-" not in str(e) for e in events)

    def test_cutover_requires_owned_state_and_preserves_coordinator_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"secret/": {"type": "kv", "options": {"version": "2"}}}
        client.sys.list_auth_methods.return_value = {"approle/": {}}
        client.auth.approle.read_role_id.side_effect = lambda role_name: {"data": {"role_id": role_name}}
        client.auth.approle.generate_secret_id.side_effect = lambda role_name, **kw: {"wrap_info": {"token": role_name, "creation_path": f"auth/approle/role/{role_name}/secret-id", "creation_time": "2026-01-01T00:00:00Z", "ttl": 300}}
        apply_reconciliation(client, plan)
        _write(agents, "credential_vendors: [anthropic]\nagents: {}\n")
        _write(mapping, "version: 1\nagents: {}\nvendors: {anthropic: ANTHROPIC_KEY}\nlegacy_role_aliases: {claude-web: claude-web}\nretained_internal: [DB_PASSWORD, CLAUDE_WEB_KEY]\n")
        retired = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        assert "agent-claude-web" in retired.preview()
        apply_reconciliation(client, retired)
        client.auth.approle.delete_role.assert_not_called()
        with pytest.raises(ValueError, match="internal AppRole"):
            plan_reconciliation(agents, secrets, mapping, bootstrap, "secret", confirm_cutover=True)
        client.auth.approle.read_role.return_value = {"data": {"token_policies": ["coordinator-read"], "secret_id_num_uses": 0}}
        client.auth.approle.read_role_id.side_effect = None
        client.auth.approle.read_role_id.return_value = {"data": {"role_id": "internal-role-id"}}
        client.auth.approle.list_roles.return_value = {"data": {"keys": ["coordinator-internal", "agent-claude-web"]}}
        client.auth.approle.login.return_value = {"auth": {"client_token": "internal-token", "policies": ["default", "coordinator-internal-read"]}}
        monkeypatch.setenv("BAO_INTERNAL_ROLE_ID", "internal-role-id")
        monkeypatch.setenv("BAO_INTERNAL_SECRET_ID", "internal-secret-id")
        monkeypatch.setenv("BAO_SECRET_PATH", "internal/config")
        handoffs: list[tuple] = []
        monkeypatch.setattr("bao_seed._verify_internal_handoff", lambda *args: handoffs.append(args))
        apply_reconciliation(client, retired, confirm_cutover=True, internal_role_name="coordinator-internal")
        assert [call.kwargs["role_name"] for call in client.auth.approle.delete_role.call_args_list] == ["agent-claude-web", "claude-web"]
        assert handoffs[0][-1] == "internal/config"
        internal_policy = next(call.kwargs["policy"] for call in client.sys.create_or_update_policy.call_args_list if call.kwargs["name"] == "coordinator-internal-read")
        assert 'secret/data/internal/config' in internal_policy
        policy_create = next(i for i, call in enumerate(client.mock_calls) if call[0] == "sys.create_or_update_policy" and call.kwargs.get("name") == "coordinator-internal-read")
        legacy_delete = next(i for i, call in enumerate(client.mock_calls) if call[0] == "sys.delete_policy" and call.kwargs.get("name") == "coordinator-read")
        assert policy_create < legacy_delete
        assert all(call.kwargs.get("path") != "coordinator" for call in client.secrets.kv.v2.delete_metadata_and_all_versions.call_args_list)

    def test_cutover_rejects_unknown_shared_policy_user_before_mutation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"secret/": {"type": "kv", "options": {"version": "2"}}}
        client.auth.approle.read_role.return_value = {"data": {"token_policies": ["coordinator-read"], "secret_id_num_uses": 0}}
        client.auth.approle.read_role_id.return_value = {"data": {"role_id": "internal-role-id"}}
        client.auth.approle.list_roles.return_value = {"data": {"keys": ["coordinator-internal", "unrelated"]}}
        monkeypatch.setenv("BAO_INTERNAL_ROLE_ID", "internal-role-id")
        monkeypatch.setenv("BAO_INTERNAL_SECRET_ID", "internal-secret-id")
        with pytest.raises(ValueError, match="unexpected AppRole"):
            apply_reconciliation(client, plan, confirm_cutover=True, internal_role_name="coordinator-internal")
        client.sys.create_or_update_policy.assert_not_called()

    def test_cutover_rejects_single_use_internal_secret_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"secret/": {"type": "kv", "options": {"version": "2"}}}
        client.auth.approle.read_role.return_value = {"data": {"token_policies": ["coordinator-read"], "secret_id_num_uses": 1}}
        monkeypatch.setenv("BAO_INTERNAL_ROLE_ID", "internal-role-id")
        monkeypatch.setenv("BAO_INTERNAL_SECRET_ID", "internal-secret-id")
        with pytest.raises(ValueError, match="reusable SecretIDs"):
            apply_reconciliation(client, plan, confirm_cutover=True, internal_role_name="coordinator-internal")
        client.auth.approle.login.assert_not_called()
        client.sys.create_or_update_policy.assert_not_called()

    def test_retained_internal_may_be_empty(self, tmp_path: Path) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        _write(secrets, "CLAUDE_WEB_KEY: agent-secret\nANTHROPIC_KEY: vendor-secret\nDB_PASSWORD: ''\n")
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        assert plan.retained_internal == ("DB_PASSWORD",)

    def test_null_mount_options_fail_cleanly(self, tmp_path: Path) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"secret/": {"type": "kv", "options": None}}
        with pytest.raises(ValueError, match="not KV-v2"):
            apply_reconciliation(client, plan)
        client.sys.create_or_update_policy.assert_not_called()

    def test_wrapped_auth_methods_are_recognized(self, tmp_path: Path) -> None:
        agents, secrets, mapping, bootstrap = _migration_inputs(tmp_path)
        plan = plan_reconciliation(agents, secrets, mapping, bootstrap, "secret")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"secret/": {"type": "kv", "options": {"version": "2"}}}
        client.sys.list_auth_methods.return_value = {"data": {"approle/": {}}}
        client.auth.approle.read_role_id.side_effect = lambda role_name: {"data": {"role_id": role_name}}
        client.auth.approle.generate_secret_id.side_effect = lambda role_name, **kw: {"wrap_info": {"token": role_name, "creation_path": f"auth/approle/role/{role_name}/secret-id", "creation_time": "2026-01-01T00:00:00Z", "ttl": 300}}
        apply_reconciliation(client, plan, audit=lambda e: None)
        client.sys.enable_auth_method.assert_not_called()

    def test_internal_handoff_reads_with_fresh_token_then_revokes_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from bao_seed import _verify_internal_handoff
        import hvac

        admin = MagicMock()
        admin.url = "http://127.0.0.1:8200"
        admin.auth.approle.login.return_value = {"auth": {"client_token": "short-lived-token", "policies": ["default", "coordinator-internal-read"]}}
        reader = MagicMock()
        reader.secrets.kv.v2.read_secret_version.return_value = {"data": {"data": {"DB_PASSWORD": "unused"}}}
        constructor = MagicMock(return_value=reader)
        monkeypatch.setattr(hvac, "Client", constructor)

        _verify_internal_handoff(admin, "secret", "role-id", "secret-id", "internal/config")

        constructor.assert_called_once_with(url=admin.url, token="short-lived-token")
        reader.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="internal/config", mount_point="secret", raise_on_deleted_version=True,
        )
        reader.auth.token.revoke_self.assert_called_once_with()
        admin.auth.approle.login.assert_called_once_with(role_id="role-id", secret_id="secret-id", use_token=False)


# ---------------------------------------------------------------------------
# seed_secrets
# ---------------------------------------------------------------------------


class TestSeedSecrets:
    def test_writes_secrets_to_kv(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "DB_PASSWORD: mypass\nAPI_KEY: key123\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator")

        client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
            path="coordinator",
            secret={"DB_PASSWORD": "mypass", "API_KEY": "key123"},
            mount_point="secret",
        )

    def test_filters_non_string_values(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "GOOD: value\nBAD: 42\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator")

        call_args = client.secrets.kv.v2.create_or_update_secret.call_args
        assert call_args.kwargs["secret"] == {"GOOD": "value"}

    def test_missing_file_exits(self, tmp_path: Path) -> None:
        client = MagicMock()
        with pytest.raises(SystemExit):
            seed_secrets(client, tmp_path / "missing.yaml", "secret", "coordinator")

    def test_invalid_yaml_exits(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "just a string\n")
        client = MagicMock()
        with pytest.raises(SystemExit):
            seed_secrets(client, secrets, "secret", "coordinator")

    def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "DB_PASSWORD: mypass\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator", dry_run=True)

        client.secrets.kv.v2.create_or_update_secret.assert_not_called()

    def test_idempotent_rerun(self, tmp_path: Path) -> None:
        """Running twice with same data calls create_or_update (not create)."""
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "KEY: value\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator")
        seed_secrets(client, secrets, "secret", "coordinator")

        assert client.secrets.kv.v2.create_or_update_secret.call_count == 2


# ---------------------------------------------------------------------------
# seed_approles
# ---------------------------------------------------------------------------


class TestSeedApproles:
    AGENTS_YAML = """\
agents:
  claude-web:
    type: claude_code
    profile: p
    trust_level: 2
    transport: http
    api_key: "${KEY}"
    openbao_role_id: claude-web
    capabilities: [lock]
    description: Web agent
  local-agent:
    type: claude_code
    profile: p
    trust_level: 3
    transport: mcp
    capabilities: [lock]
    description: Local agent
"""

    def test_creates_approles_for_keyed_agents(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents.yaml"
        _write(agents, self.AGENTS_YAML)
        client = MagicMock()
        client.sys.list_auth_methods.return_value = {"approle/": {}}

        seed_approles(client, agents, "secret", "coordinator", 3600)

        client.sys.create_or_update_policy.assert_called_once()
        client.auth.approle.create_or_update_approle.assert_called_once_with(
            role_name="claude-web",
            token_policies=["coordinator-read"],
            token_ttl="3600s",
            token_max_ttl="86400s",
        )

    def test_enables_approle_auth_if_missing(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents.yaml"
        _write(agents, self.AGENTS_YAML)
        client = MagicMock()
        client.sys.list_auth_methods.return_value = {}

        seed_approles(client, agents, "secret", "coordinator", 3600)

        client.sys.enable_auth_method.assert_called_once_with("approle")

    def test_skips_agents_without_a_key(self, tmp_path: Path) -> None:
        agents_yaml = """\
agents:
  local-only:
    type: claude_code
    profile: p
    trust_level: 3
    transport: mcp
    capabilities: [lock]
    description: MCP only
"""
        agents = tmp_path / "agents.yaml"
        _write(agents, agents_yaml)
        client = MagicMock()

        seed_approles(client, agents, "secret", "coordinator", 3600)

        client.auth.approle.create_or_update_approle.assert_not_called()

    def test_creates_approle_for_keyed_mcp_agent(self, tmp_path: Path) -> None:
        """An `mcp` agent that declares a key must get an AppRole.

        This is the case the old `transport == "http"` selector dropped.
        `get_api_key_identities()` already grants such an agent an identity row
        regardless of transport (design D5), so seeding only HTTP agents left
        the AppRole set narrower than the identity map it backs — the agent
        held a key OpenBao was never told to serve.
        """
        agents_yaml = """\
agents:
  grok-local:
    type: grok
    profile: p
    trust_level: 3
    transport: mcp
    api_key: "${GROK_LOCAL_API_KEY}"
    openbao_role_id: grok-local
    capabilities: [lock]
    description: Local grok harness
"""
        agents = tmp_path / "agents.yaml"
        _write(agents, agents_yaml)
        client = MagicMock()
        client.sys.list_auth_methods.return_value = {"approle/": {}}

        seed_approles(client, agents, "secret", "coordinator", 3600)

        client.auth.approle.create_or_update_approle.assert_called_once_with(
            role_name="grok-local",
            token_policies=["coordinator-read"],
            token_ttl="3600s",
            token_max_ttl="86400s",
        )

    def test_missing_agents_file_warns(self, tmp_path: Path) -> None:
        client = MagicMock()
        seed_approles(client, tmp_path / "missing.yaml", "secret", "coordinator", 3600)
        client.auth.approle.create_or_update_approle.assert_not_called()

    def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents.yaml"
        _write(agents, self.AGENTS_YAML)
        client = MagicMock()

        seed_approles(client, agents, "secret", "coordinator", 3600, dry_run=True)

        client.sys.create_or_update_policy.assert_not_called()
        client.auth.approle.create_or_update_approle.assert_not_called()


# ---------------------------------------------------------------------------
# seed_db_engine
# ---------------------------------------------------------------------------


class TestSeedDbEngine:
    def test_enables_and_configures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@host:5432/db")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {}

        seed_db_engine(client)

        client.sys.enable_secrets_engine.assert_called_once_with("database")
        client.secrets.database.configure.assert_called_once()
        # Verify the connection URL is built correctly from the DSN
        configure_call = client.secrets.database.configure.call_args
        assert configure_call.kwargs["connection_url"] == "postgresql://{{username}}:{{password}}@host:5432/db"
        assert configure_call.kwargs["username"] == "user"
        assert configure_call.kwargs["password"] == "pass"
        client.secrets.database.create_role.assert_called_once()
        role_call = client.secrets.database.create_role.call_args
        assert role_call.kwargs["name"] == "coordinator-agent"
        assert role_call.kwargs["default_ttl"] == "1h"
        assert role_call.kwargs["max_ttl"] == "24h"

    def test_skips_enable_if_already_mounted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@host:5432/db")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"database/": {}}

        seed_db_engine(client)

        client.sys.enable_secrets_engine.assert_not_called()

    def test_dry_run_no_writes(self) -> None:
        client = MagicMock()

        seed_db_engine(client, dry_run=True)

        client.sys.enable_secrets_engine.assert_not_called()
        client.secrets.database.configure.assert_not_called()
        client.secrets.database.create_role.assert_not_called()
