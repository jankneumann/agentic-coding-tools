"""Adversarial tests for the shared trust resolver (src/trust_resolution.py).

The change ``derive-agent-identity-from-registry`` claims that an agent's
effective trust level is the one ``agents.yaml`` declares for it, and that a
broken projection fails loud rather than substituting something plausible. A
security review found the runtime gate did not deliver that claim in two ways,
both reproduced here as attacks rather than as unit assertions:

* **Decommissioning promoted.** Removing an agent from the registry disables
  its profile and deletes its assignment row, after which
  ``get_agent_profile()``'s ``agent_type`` fallback handed the principal a
  *sibling* profile — often a higher-trust one.
* **The gate checked "a profile resolved", not "the declared profile
  resolved."** ``registry_entry.profile`` was loaded and never compared to the
  resolved ``profile.name``, so a registry agent landing on a different,
  higher-trust profile was accepted silently.

The roster names below are the real ones, because the escalation only exists
for real pairs: ``codex-remote``/``codex_remote`` (trust 2) shares the
``codex`` agent type with ``codex-local``/``codex_local`` (trust 3), and
``claude-remote``/``claude_code_remote`` (trust 2) shares ``claude_code``
with ``claude-local``/``claude_code_local`` (trust 3).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.config import reset_config
from src.trust_levels import MIN_ADMIN_TRUST

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(
    name: str,
    *,
    profile: str,
    agent_type: str,
    trust_level: int,
) -> Any:
    from src.agents_config import AgentEntry

    return AgentEntry(
        name=name,
        type=agent_type,
        profile=profile,
        trust_level=trust_level,
        transport="mcp",
        capabilities=["lock"],
        description="roster entry under test",
    )


def _resolved(
    *,
    name: str,
    agent_type: str,
    trust_level: int,
    source: str,
    enabled: bool = True,
) -> Any:
    """A successful ``get_profile()`` result for profile *name*."""
    from src.profiles import AgentProfile, ProfileResult

    return ProfileResult(
        success=True,
        profile=AgentProfile(
            id=f"profile-{name}",
            name=name,
            agent_type=agent_type,
            trust_level=trust_level,
            enabled=enabled,
        ),
        source=source,
    )


@pytest.fixture()
def _default_trust_2(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("PROFILES_DEFAULT_TRUST", "2")
    reset_config()
    yield
    reset_config()


def _patch_registry(monkeypatch: pytest.MonkeyPatch, entry: Any) -> None:
    monkeypatch.setattr("src.agents_config.get_agent_config", lambda _agent_id: entry)


def _patch_profiles(monkeypatch: pytest.MonkeyPatch, result: Any) -> AsyncMock:
    service = AsyncMock()
    service.get_profile.return_value = result
    monkeypatch.setattr("src.profiles._profiles_service", service)
    return service


# ---------------------------------------------------------------------------
# F1 — retiring an agent must revoke it, never escalate it
# ---------------------------------------------------------------------------


class TestDecommissionDoesNotPromote:
    """The post-decommission state, replayed exactly.

    ``codex-remote`` is deleted from ``agents.yaml``. Startup sync then
    disables profile ``codex_remote`` and DELETEs the agent's assignment row.
    A request still arriving as ``agent_id=codex-remote, agent_type=codex``
    finds no assignment, falls through to the ``agent_type`` fallback, and
    lands on the only remaining enabled ``codex`` profile — ``codex_local``,
    trust 3, which is at or above ``MIN_ADMIN_TRUST``-adjacent territory and
    strictly above what the retired agent ever held.
    """

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_default_trust_2")
    async def test_retired_codex_agent_does_not_inherit_sibling_trust(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from src.trust_resolution import resolve_trust_level

        # No registry entry: the agent was removed from agents.yaml.
        _patch_registry(monkeypatch, None)
        # No assignment row either, so resolution came from the type fallback
        # and landed on the surviving sibling profile.
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="codex_local",
                agent_type="codex",
                trust_level=3,
                source="default",
            ),
        )

        trust = await resolve_trust_level("codex-remote", "codex")

        assert trust == 2, "decommissioned agent inherited codex_local's trust"
        assert trust < 3

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_default_trust_2")
    async def test_retired_claude_agent_stays_below_admin(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Same attack on the claude_code pair, pinned against admin trust.

        A sibling profile projected at ``MIN_ADMIN_TRUST`` would unlock
        force_push / delete_branch / cleanup_agents / rollback_policy for an
        identity the registry no longer knows about.
        """
        from src.trust_resolution import resolve_trust_level

        _patch_registry(monkeypatch, None)
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="claude_code_local",
                agent_type="claude_code",
                trust_level=MIN_ADMIN_TRUST,
                source="default",
            ),
        )

        trust = await resolve_trust_level("claude-remote", "claude_code")

        assert trust == 2
        assert trust < MIN_ADMIN_TRUST

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_default_trust_2")
    async def test_explicit_assignment_still_credited(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The guard denies the *fallback*, not deliberate bindings.

        A principal outside the registry that somebody explicitly bound to a
        profile keeps that profile's trust level — otherwise the fix would
        break every hand-assigned external identity.
        """
        from src.trust_resolution import resolve_trust_level

        _patch_registry(monkeypatch, None)
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="external_worker",
                agent_type="codex",
                trust_level=3,
                source="assignment",
            ),
        )

        assert await resolve_trust_level("external-worker", "codex") == 3

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_default_trust_2")
    async def test_disabled_assignment_target_gets_default(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A disabled profile is not authorization, however it was reached."""
        from src.trust_resolution import resolve_trust_level

        _patch_registry(monkeypatch, None)
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="external_worker",
                agent_type="codex",
                trust_level=4,
                source="assignment",
                enabled=False,
            ),
        )

        assert await resolve_trust_level("external-worker", "codex") == 2


# ---------------------------------------------------------------------------
# F2 — the gate must check that the *declared* profile resolved
# ---------------------------------------------------------------------------


class TestDeclaredProfileIsEnforced:
    @pytest.mark.asyncio
    async def test_registry_agent_landing_on_another_profile_fails_loud(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Resolving to a *different* profile is a projection failure.

        ``codex-remote`` is still declared, but its assignment row is missing,
        so the type fallback serves ``codex_local`` at trust 3. Accepting that
        is the exact "a profile resolved" weakness the CI invariant checker was
        rewritten to stop asserting (design D11); the runtime gate must not
        keep asserting it.
        """
        from src.trust_resolution import TrustResolutionError, resolve_trust_level

        _patch_registry(
            monkeypatch,
            _entry(
                "codex-remote",
                profile="codex_remote",
                agent_type="codex",
                trust_level=2,
            ),
        )
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="codex_local",
                agent_type="codex",
                trust_level=3,
                source="default",
            ),
        )
        audit = AsyncMock()
        monkeypatch.setattr("src.audit._audit_service", audit)

        with pytest.raises(TrustResolutionError) as excinfo:
            await resolve_trust_level("codex-remote", "codex")

        assert excinfo.value.status_code == 500
        detail = str(excinfo.value.detail)
        assert "codex_local" in detail
        assert "codex_remote" in detail
        audit.log_operation.assert_awaited_once()
        assert (
            audit.log_operation.await_args.kwargs["operation"]
            == "trust_resolution_failed"
        )
        assert audit.log_operation.await_args.kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_registry_agent_landing_on_admin_profile_fails_loud(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The mismatch must not be waved through just because trust is higher."""
        from src.trust_resolution import TrustResolutionError, resolve_trust_level

        _patch_registry(
            monkeypatch,
            _entry(
                "claude-remote",
                profile="claude_code_remote",
                agent_type="claude_code",
                trust_level=2,
            ),
        )
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="claude_code_local",
                agent_type="claude_code",
                trust_level=MIN_ADMIN_TRUST,
                source="default",
            ),
        )
        monkeypatch.setattr("src.audit._audit_service", AsyncMock())

        with pytest.raises(TrustResolutionError, match="is not the registry-declared"):
            await resolve_trust_level("claude-remote", "claude_code")

    @pytest.mark.asyncio
    async def test_name_match_via_type_fallback_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``source == 'assignment'`` is deliberately NOT required here.

        With ``PROFILE_SYNC_ENABLED=false``, or before the first sync has run,
        there are no assignment rows at all. A name match reached through the
        type fallback is still the declared profile, and must resolve.
        """
        from src.trust_resolution import resolve_trust_level

        _patch_registry(
            monkeypatch,
            _entry(
                "codex-local",
                profile="codex_local",
                agent_type="codex",
                trust_level=3,
            ),
        )
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="codex_local",
                agent_type="codex",
                trust_level=3,
                source="default",
            ),
        )

        assert await resolve_trust_level("codex-local", "codex") == 3

    @pytest.mark.asyncio
    async def test_name_match_via_assignment_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from src.trust_resolution import resolve_trust_level

        _patch_registry(
            monkeypatch,
            _entry(
                "codex-local",
                profile="codex_local",
                agent_type="codex",
                trust_level=3,
            ),
        )
        _patch_profiles(
            monkeypatch,
            _resolved(
                name="codex_local",
                agent_type="codex",
                trust_level=3,
                source="assignment",
            ),
        )

        assert await resolve_trust_level("codex-local", "codex") == 3


# ---------------------------------------------------------------------------
# F6 — one implementation, re-exported where callers expect it
# ---------------------------------------------------------------------------


class TestSingleImplementation:
    def test_coordination_api_reexports_the_shared_resolver(self) -> None:
        """The HTTP path must not carry a second copy."""
        import src.coordination_api as api
        import src.trust_resolution as shared

        assert api.resolve_trust_level is shared.resolve_trust_level
        assert api.TrustResolutionError is shared.TrustResolutionError


@pytest.mark.asyncio
class TestCacheHitsDoNotEscalate:
    """The profile cache must not launder provenance into an escalation.

    Every other test in this file replaces ``get_profile`` with an
    ``AsyncMock``, so none of them execute the real cache — which is exactly
    how this escaped. ``ProfilesService`` memoizes a lookup for
    ``cache_ttl_seconds`` (default 300); an earlier version cached the profile
    *without* its provenance and reported ``source="cache"`` on every hit.

    Because :func:`resolve_trust_level` credits a principal the registry does
    not name only when provenance is ``'assignment'``, that marker made every
    hit inside the TTL discard the assigned profile and fall back to
    ``default_trust_level``. Where the assigned level is *lower* than the
    default, that is an escalation — and at trust 0 it un-suspends a suspended
    principal, which is the precise failure a previous commit claimed to fix.

    So this test drives the real service and asserts the *trust level*, not the
    source label: the label is an implementation detail, the privilege is not.
    """

    @staticmethod
    def _service_over_fake_db(profile: dict[str, Any], source: str) -> Any:
        from src.profiles import ProfilesService

        class _FakeDb:
            def __init__(self) -> None:
                self.rpc_calls = 0

            async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
                assert function_name == "get_agent_profile"
                self.rpc_calls += 1
                return {"success": True, "profile": profile, "source": source}

        db = _FakeDb()
        return ProfilesService(db), db

    @pytest.mark.usefixtures("_default_trust_2")
    async def test_suspended_principal_stays_suspended_on_cache_hits(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """trust 0 assigned, default 2: the cached call must not return 2."""
        from src.trust_resolution import resolve_trust_level

        service, db = self._service_over_fake_db(
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "quarantined_worker",
                "agent_type": "codex",
                "trust_level": 0,
                "enabled": True,
            },
            source="assignment",
        )
        _patch_registry(monkeypatch, None)
        monkeypatch.setattr("src.profiles._profiles_service", service)

        cold = await resolve_trust_level("quarantined-worker", "codex")
        warm = await resolve_trust_level("quarantined-worker", "codex")
        warmer = await resolve_trust_level("quarantined-worker", "codex")

        assert db.rpc_calls == 1, "second lookup must be served from the cache"
        assert cold == 0
        assert warm == 0, (
            "cache hit escalated a suspended principal to the default trust level"
        )
        assert warmer == 0

    @pytest.mark.usefixtures("_default_trust_2")
    async def test_fallback_derived_profile_is_still_denied_on_cache_hits(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The converse: caching must not *promote* a fallback result either.

        A profile reached through the ``agent_type`` fallback is not credited
        to a non-registry principal. Accepting ``"cache"`` as an assignment-like
        source would have reopened that hole, since a fallback result caches
        identically — hence the fix preserves the original source rather than
        widening the accepted set.
        """
        from src.trust_resolution import resolve_trust_level

        service, db = self._service_over_fake_db(
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "name": "codex_local",
                "agent_type": "codex",
                "trust_level": 3,
                "enabled": True,
            },
            source="default",
        )
        _patch_registry(monkeypatch, None)
        monkeypatch.setattr("src.profiles._profiles_service", service)

        cold = await resolve_trust_level("retired-codex", "codex")
        warm = await resolve_trust_level("retired-codex", "codex")

        assert db.rpc_calls == 1
        assert cold == 2, "fallback result must not be credited"
        assert warm == 2, "cache hit must not credit it either"
