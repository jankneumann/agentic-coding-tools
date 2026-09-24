"""Tests for the network access policy service."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import Response

from src.network_policies import (
    AccessDecision,
    NetworkPolicyExportError,
    NetworkPolicyService,
)


class TestNetworkPolicyService:
    """Tests for NetworkPolicyService."""

    @pytest.mark.asyncio
    async def test_check_domain_allowed(self, mock_supabase, db_client):
        """Test that allowed domains pass."""
        policy_id = str(uuid4())
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(
                200,
                json={
                    "allowed": True,
                    "domain": "github.com",
                    "reason": "global_allow",
                    "policy_id": policy_id,
                },
            )
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("github.com")

        assert result.allowed is True
        assert result.domain == "github.com"
        assert result.policy_id == policy_id

    @pytest.mark.asyncio
    async def test_check_domain_denied(self, mock_supabase, db_client):
        """Test that denied domains are rejected."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(
                200,
                json={
                    "allowed": False,
                    "domain": "evil.com",
                    "reason": "no_matching_policy",
                },
            )
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("evil.com")

        assert result.allowed is False
        assert result.domain == "evil.com"
        assert result.reason == "no_matching_policy"

    @pytest.mark.asyncio
    async def test_check_domain_with_agent_id(self, mock_supabase, db_client):
        """Test checking domain with explicit agent_id."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(
                200,
                json={
                    "allowed": True,
                    "domain": "pypi.org",
                    "reason": "profile_allow",
                },
            )
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("pypi.org", agent_id="custom-agent")

        assert result.allowed is True
        assert result.domain == "pypi.org"

    @pytest.mark.asyncio
    async def test_check_domain_error_falls_back_to_default_deny(
        self, mock_supabase, db_client
    ):
        """Test that errors fall back to default deny policy."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(500, json={"error": "internal error"})
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("example.com")

        assert result.allowed is False
        assert result.domain == "example.com"
        assert "default_policy" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_check_domain_error_falls_back_to_default_allow(
        self, mock_supabase, db_client, monkeypatch
    ):
        """Test fallback to allow when default policy is 'allow'."""
        monkeypatch.setenv("NETWORK_DEFAULT_POLICY", "allow")
        from src.config import reset_config

        reset_config()

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/is_domain_allowed"
        ).mock(
            return_value=Response(500, json={"error": "internal error"})
        )

        service = NetworkPolicyService(db_client)
        result = await service.check_domain("example.com")

        assert result.allowed is True
        assert "default_policy:allow" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_export_exact_agent_preserves_atomic_order_and_digest(self):
        db = type("DB", (), {})()
        rows = {
            "schema_version": 1,
            "agent_id": "codex-local",
            "default_action": "deny",
            "rules": [
                {
                    "destination_kind": "dns",
                    "destination_pattern": "*.github.com",
                    "port": 443,
                    "action": "deny",
                    "priority": 1,
                    "scope": "agent_profile",
                    "policy_id": "00000000-0000-0000-0000-000000000002",
                },
                {
                    "destination_kind": "dns",
                    "destination_pattern": "github.com",
                    "port": 443,
                    "action": "allow",
                    "priority": 1,
                    "scope": "global",
                    "policy_id": "00000000-0000-0000-0000-000000000001",
                },
            ],
            "policy_revision": "v1:2026-09-24T12:00:00.000000Z:2",
        }

        async def rpc(name, params):
            assert name == "export_network_policy"
            assert params == {"p_agent_id": "codex-local"}
            return rows

        db.rpc = rpc
        result = await NetworkPolicyService(db).export_for_agent("codex-local")

        expected = hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert result["policy_digest"] == expected
        assert result["rules"] == rows["rules"]

    @pytest.mark.asyncio
    async def test_export_empty_policy_uses_stable_revision_sentinel(self):
        db = type("DB", (), {})()

        async def rpc(_name, _params):
            return {
                "schema_version": 1,
                "agent_id": "codex-local",
                "default_action": "deny",
                "rules": [],
                "policy_revision": "v1:none:0",
            }

        db.rpc = rpc
        result = await NetworkPolicyService(db).export_for_agent("codex-local")
        assert result["policy_revision"] == "v1:none:0"
        assert len(result["policy_digest"]) == 64

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("reason", "status"),
        [("agent_not_found", 404), ("profile_disabled", 409), ("agent_unassigned", 409)],
    )
    async def test_export_rejects_non_exportable_exact_agent(self, reason, status):
        db = type("DB", (), {})()

        async def rpc(_name, _params):
            return {"success": False, "reason": reason}

        db.rpc = rpc
        with pytest.raises(NetworkPolicyExportError) as exc:
            await NetworkPolicyService(db).export_for_agent("missing")
        assert exc.value.status_code == status

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "rule",
        [
            {"destination_kind": "dns", "destination_pattern": "*.*.example.com"},
            {"destination_kind": "dns", "destination_pattern": "*.com"},
            {"destination_kind": "ipv4", "destination_pattern": "999.1.2.3"},
            {"destination_kind": "ipv6", "destination_pattern": "::1"},
            {"destination_kind": "dns", "destination_pattern": "ok.example", "port": 0},
        ],
    )
    async def test_export_rejects_malformed_typed_destination(self, rule):
        db = type("DB", (), {})()
        complete = {
            "port": None,
            "action": "allow",
            "priority": 1,
            "scope": "global",
            "policy_id": "rule-1",
            **rule,
        }

        async def rpc(_name, _params):
            return {
                "schema_version": 1,
                "agent_id": "codex-local",
                "default_action": "deny",
                "rules": [complete],
                "policy_revision": "v1:now:1",
            }

        db.rpc = rpc
        with pytest.raises(NetworkPolicyExportError, match="invalid policy export"):
            await NetworkPolicyService(db).export_for_agent("codex-local")

    @pytest.mark.asyncio
    async def test_export_accepts_multi_label_wildcard_suffix(self):
        db = type("DB", (), {})()

        async def rpc(_name, _params):
            return {
                "schema_version": 1,
                "agent_id": "codex-local",
                "default_action": "deny",
                "rules": [
                    {
                        "destination_kind": "dns",
                        "destination_pattern": "*.api.example.com",
                        "port": 443,
                        "action": "allow",
                        "priority": 1,
                        "scope": "global",
                        "policy_id": "rule-1",
                    }
                ],
                "policy_revision": "v1:now:1",
            }

        db.rpc = rpc
        result = await NetworkPolicyService(db).export_for_agent("codex-local")
        assert result["rules"][0]["destination_pattern"] == "*.api.example.com"


class TestAccessDecisionDataClass:
    """Tests for AccessDecision dataclass."""

    def test_from_dict_full(self):
        """Test creating AccessDecision from full dict."""
        decision = AccessDecision.from_dict(
            {
                "allowed": True,
                "domain": "github.com",
                "reason": "global_allow",
                "policy_id": "abc-123",
            }
        )

        assert decision.allowed is True
        assert decision.domain == "github.com"
        assert decision.reason == "global_allow"
        assert decision.policy_id == "abc-123"

    def test_from_dict_minimal(self):
        """Test creating AccessDecision from minimal dict."""
        decision = AccessDecision.from_dict({"allowed": False, "domain": "test.com"})

        assert decision.allowed is False
        assert decision.domain == "test.com"
        assert decision.reason is None
        assert decision.policy_id is None

    def test_from_dict_defaults(self):
        """Test AccessDecision defaults for missing fields."""
        decision = AccessDecision.from_dict({})

        assert decision.allowed is False
        assert decision.domain == ""


def test_migration_044_freezes_atomic_export_and_idempotent_audit_contract():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "044_dispatch_sandbox.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION export_network_policy" in migration
    assert "CASE WHEN profile_id IS NULL THEN 1 ELSE 0 END" in migration
    assert "priority ASC" in migration
    assert "CASE WHEN action = 'deny' THEN 0 ELSE 1 END" in migration
    assert "id ASC" in migration
    assert "WHERE enabled" in migration
    assert "'v1:none:0'" in migration
    assert "network_policies_updated_at" in migration
    assert "event_id UUID NOT NULL UNIQUE" in migration
    assert "ON CONFLICT (event_id) DO NOTHING" in migration
