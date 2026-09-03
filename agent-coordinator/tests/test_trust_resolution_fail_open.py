"""Two fail-open paths in trust resolution (#408 defects 2 and 3).

Both were reported against #408, verified against `main` at `51f1dad`, and both
fail in the *permissive* direction — which is why neither ever surfaced as an
incident. Nothing breaks when authorization is too generous; it just is.

They are grouped here because they are the same mistake in two places: a value
that authorization depends on gets replaced by a more convenient one along the
way, and the substitution is invisible at the point where the decision is made.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from src.profiles import ProfilesService
from src.trust_resolution import TrustResolutionError
from src.work_queue import WorkQueueService

# ---------------------------------------------------------------------------
# Defect 2: the profile cache erased provenance, un-suspending trust-0 agents
# ---------------------------------------------------------------------------

SUSPENDED_ASSIGNMENT_ROW: dict[str, Any] = {
    "success": True,
    "source": "assignment",
    "profile": {
        "name": "suspended_profile",
        "agent_type": "claude_code",
        "trust_level": 0,
        "enabled": True,
        "allowed_operations": [],
        "blocked_operations": [],
        "max_files_per_operation": 1,
        "requires_approval_for": [],
    },
}


class _CountingDB:
    """Returns one fixed profile row and counts how often it was asked."""

    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.rpc_calls = 0

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        self.rpc_calls += 1
        return self.row


class TestCacheHitsPreserveProvenance:
    """A cached read must report the provenance of the read that filled it."""

    async def test_cache_hit_reports_original_source_not_cache(self) -> None:
        db = _CountingDB(SUSPENDED_ASSIGNMENT_ROW)
        service = ProfilesService(db=db)

        first = await service.get_profile(agent_id="a1", agent_type="claude_code")
        second = await service.get_profile(agent_id="a1", agent_type="claude_code")

        assert db.rpc_calls == 1, "second read should have been served from cache"
        assert first.source == "assignment"
        assert second.source == "assignment", (
            "the cache hit reported a different provenance than the read that "
            "populated it — callers gate on this value"
        )

    async def test_suspended_non_registry_principal_stays_suspended(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The escalation this defect actually produced.

        ``resolve_trust_level`` credits a principal the registry does not name
        only when ``source == 'assignment'``. With the cache reporting
        ``'cache'`` the gate could not match, so control fell through to
        ``default_trust_level`` — demoting a high-trust profile (harmless) but
        **promoting a suspended one from 0 to the default**, renewed on every
        read for the length of the cache TTL.

        Suspension is precisely what that branch exists to protect, so the one
        direction that mattered was the one that failed open.
        """
        from src import agents_config, profiles
        from src.trust_resolution import resolve_trust_level

        agent_id = "retired-agent-not-in-registry"
        assert agents_config.get_agent_config(agent_id) is None, (
            "fixture must be a principal the registry does not name"
        )

        service = ProfilesService(db=_CountingDB(SUSPENDED_ASSIGNMENT_ROW))
        monkeypatch.setattr(profiles, "_profiles_service", service)

        first = await resolve_trust_level(agent_id, "claude_code")
        second = await resolve_trust_level(agent_id, "claude_code")
        third = await resolve_trust_level(agent_id, "claude_code")

        assert first == 0
        assert (second, third) == (0, 0), (
            f"a suspended principal was credited trust {second} on a cache hit"
        )

    async def test_expired_entry_is_refetched(self) -> None:
        """The TTL must still work — this fix must not make the cache eternal."""
        db = _CountingDB(SUSPENDED_ASSIGNMENT_ROW)
        service = ProfilesService(db=db)

        await service.get_profile(agent_id="a1", agent_type="claude_code")
        # Age the entry past any plausible TTL.
        key, (profile, source, _) = next(iter(service._cache.items()))
        service._cache[key] = (profile, source, time.monotonic() - 10_000)

        await service.get_profile(agent_id="a1", agent_type="claude_code")
        assert db.rpc_calls == 2


# ---------------------------------------------------------------------------
# Defect 3: a trust-resolution failure skipped the guardrail scan entirely
# ---------------------------------------------------------------------------


class _FakeGuardrails:
    """Records whether the destructive-pattern scan actually ran."""

    def __init__(self) -> None:
        self.called = False

    async def check_operation(self, **kwargs: Any) -> Any:
        self.called = True
        raise AssertionError("unreachable when trust resolution fails")


class _SubmitDB:
    def __init__(self) -> None:
        self.submitted = False

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        if function_name == "submit_task":
            self.submitted = True
            return {"success": True, "task_id": "00000000-0000-4000-8000-000000000123"}
        return {}

    async def query(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def insert(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"id": "x"}


class TestTrustFailureNeverSkipsGuardrails:
    """``_resolve_trust_level`` documents that TrustResolutionError propagates.

    Its call sites sat inside ``try: ... except Exception: logger.error(...)``,
    so the blanket handler caught it and execution continued *past* the
    guardrail scan. The docstring stated the intent; the surrounding code
    defeated it.
    """

    @pytest.fixture(autouse=True)
    def _allow_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src import policy_engine
        from src.policy_engine import PolicyDecision

        class _Allow:
            async def check_operation(self, **kwargs: Any) -> PolicyDecision:
                return PolicyDecision.allow(reason="test")

        monkeypatch.setattr(policy_engine, "get_policy_engine", lambda: _Allow())

    async def test_submit_propagates_instead_of_writing_unscanned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src import guardrails, trust_resolution

        async def _boom(agent_id: str, agent_type: str, *a: Any, **k: Any) -> int:
            raise TrustResolutionError(agent_id, agent_type, "projection broken")

        monkeypatch.setattr(trust_resolution, "resolve_trust_level", _boom)
        scanner = _FakeGuardrails()
        monkeypatch.setattr(guardrails, "get_guardrails_service", lambda: scanner)

        db = _SubmitDB()
        service = WorkQueueService(db=db)

        with pytest.raises(TrustResolutionError):
            await service.submit(
                task_type="test",
                description="rm -rf / --no-preserve-root",
            )

        assert not scanner.called
        assert not db.submitted, (
            "a destructive task was written while the guardrail scan was skipped"
        )

    async def test_every_guardrail_handler_re_raises_trust_failures(self) -> None:
        """All three call sites, not just the one exercised above.

        ``claim`` and ``complete`` need live queue state to drive end-to-end, so
        this asserts the structural property directly: no blanket handler around
        a guardrail scan may sit without a ``TrustResolutionError`` re-raise
        ahead of it.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parent.parent / "src" / "work_queue.py"
        ).read_text()

        for phase in ("claim", "complete", "submit"):
            marker = f'"Guardrails check failed during {phase}"'
            assert marker in source, f"guardrail handler for {phase} not found"
            preceding = source[: source.index(marker)]
            tail = preceding[-600:]
            assert "except TrustResolutionError:" in tail, (
                f"the guardrail handler in {phase}() can still swallow a "
                f"TrustResolutionError and skip the scan"
            )
