"""Tests for the port allocator service."""

from __future__ import annotations

import hashlib
import time

import pytest

from src.config import PortAllocatorConfig
from src.port_allocator import (
    PortAllocatorService,
    get_port_allocator,
    reset_port_allocator,
)

# ================================================================== #
# Helpers
# ================================================================== #


def _make_config(
    *,
    base_port: int = 10000,
    range_per_session: int = 100,
    ttl_minutes: int = 120,
    max_sessions: int = 20,
) -> PortAllocatorConfig:
    return PortAllocatorConfig(
        base_port=base_port,
        range_per_session=range_per_session,
        ttl_minutes=ttl_minutes,
        max_sessions=max_sessions,
    )


# ================================================================== #
# 1. Successful allocation
# ================================================================== #


class TestSuccessfulAllocation:
    """Verify correct port offsets on a fresh allocation."""

    def test_first_allocation_offsets(self) -> None:
        svc = PortAllocatorService(_make_config(base_port=10000))
        alloc = svc.allocate("session-a")

        assert alloc is not None
        assert alloc.session_id == "session-a"
        assert alloc.db_port == 10000
        assert alloc.rest_port == 10001
        assert alloc.realtime_port == 10002
        assert alloc.api_port == 10003

    def test_second_allocation_uses_next_slot(self) -> None:
        svc = PortAllocatorService(_make_config(base_port=10000, range_per_session=100))
        svc.allocate("session-a")
        alloc = svc.allocate("session-b")

        assert alloc is not None
        assert alloc.db_port == 10100
        assert alloc.rest_port == 10101
        assert alloc.realtime_port == 10102
        assert alloc.api_port == 10103

    def test_allocation_has_valid_timestamps(self) -> None:
        cfg = _make_config(ttl_minutes=60)
        svc = PortAllocatorService(cfg)
        before = time.time()
        alloc = svc.allocate("session-x")
        after = time.time()

        assert alloc is not None
        assert before <= alloc.allocated_at <= after
        assert alloc.expires_at == pytest.approx(alloc.allocated_at + 3600, abs=2)


# ================================================================== #
# 2. Duplicate session — returns existing with refreshed TTL
# ================================================================== #


class TestDuplicateSession:
    """Re-allocating an existing session refreshes TTL and keeps ports."""

    def test_duplicate_returns_same_ports(self) -> None:
        svc = PortAllocatorService(_make_config())
        first = svc.allocate("dup")
        second = svc.allocate("dup")

        assert first is not None
        assert second is not None
        assert first.db_port == second.db_port
        assert first.rest_port == second.rest_port

    def test_duplicate_refreshes_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_now = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: fake_now)

        svc = PortAllocatorService(_make_config(ttl_minutes=60))
        first = svc.allocate("dup")
        assert first is not None
        original_expires = first.expires_at

        fake_now = 1_000_000.0 + 1800
        monkeypatch.setattr(time, "time", lambda: fake_now)

        second = svc.allocate("dup")
        assert second is not None
        assert second.expires_at > original_expires

    def test_duplicate_preserves_allocated_at(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_now = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: fake_now)

        svc = PortAllocatorService(_make_config())
        first = svc.allocate("dup")

        fake_now = 1_000_000.0 + 600
        monkeypatch.setattr(time, "time", lambda: fake_now)

        second = svc.allocate("dup")
        assert first is not None
        assert second is not None
        assert second.allocated_at == first.allocated_at


# ================================================================== #
# 3. Release — ports become available
# ================================================================== #


class TestRelease:
    """Releasing an allocation frees the slot for re-use."""

    def test_release_returns_true(self) -> None:
        svc = PortAllocatorService(_make_config())
        svc.allocate("sess")
        assert svc.release("sess") is True

    def test_released_slot_is_reused(self) -> None:
        svc = PortAllocatorService(_make_config(base_port=10000, max_sessions=2))
        first = svc.allocate("a")
        svc.allocate("b")
        assert first is not None

        svc.release("a")
        reused = svc.allocate("c")
        assert reused is not None
        assert reused.db_port == first.db_port

    def test_status_empty_after_release(self) -> None:
        svc = PortAllocatorService(_make_config())
        svc.allocate("sess")
        svc.release("sess")
        assert svc.status() == []


# ================================================================== #
# 4. Idempotent release of unknown session
# ================================================================== #


class TestIdempotentRelease:
    """Releasing an unknown or already-released session is a no-op."""

    def test_release_unknown_session(self) -> None:
        svc = PortAllocatorService(_make_config())
        assert svc.release("never-allocated") is True

    def test_double_release(self) -> None:
        svc = PortAllocatorService(_make_config())
        svc.allocate("sess")
        assert svc.release("sess") is True
        assert svc.release("sess") is True


# ================================================================== #
# 5. TTL expiry — expired blocks are reclaimed
# ================================================================== #


class TestTtlExpiry:
    """Expired allocations are cleaned up and their slots reclaimed."""

    def test_expired_allocation_not_in_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_now = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: fake_now)

        svc = PortAllocatorService(_make_config(ttl_minutes=1))
        svc.allocate("expire-me")

        fake_now = 1_000_000.0 + 120
        monkeypatch.setattr(time, "time", lambda: fake_now)

        assert svc.status() == []

    def test_expired_slot_is_reclaimed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_now = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: fake_now)

        cfg = _make_config(ttl_minutes=1, max_sessions=1)
        svc = PortAllocatorService(cfg)
        old = svc.allocate("old-sess")
        assert old is not None

        assert svc.allocate("blocked") is None

        fake_now = 1_000_000.0 + 120
        monkeypatch.setattr(time, "time", lambda: fake_now)

        new = svc.allocate("new-sess")
        assert new is not None
        assert new.db_port == old.db_port


# ================================================================== #
# 6. Port range exhaustion
# ================================================================== #


class TestPortRangeExhaustion:
    """Allocating more than max_sessions returns None."""

    def test_exhaustion_returns_none(self) -> None:
        cfg = _make_config(max_sessions=3)
        svc = PortAllocatorService(cfg)

        for i in range(3):
            result = svc.allocate(f"sess-{i}")
            assert result is not None

        assert svc.allocate("one-too-many") is None

    def test_release_then_allocate_after_exhaustion(self) -> None:
        cfg = _make_config(max_sessions=2)
        svc = PortAllocatorService(cfg)
        svc.allocate("a")
        svc.allocate("b")
        assert svc.allocate("c") is None

        svc.release("a")
        result = svc.allocate("c")
        assert result is not None


# ================================================================== #
# 7. env_snippet format
# ================================================================== #


class TestEnvSnippet:
    """Verify the shell-sourceable env snippet."""

    def test_env_snippet_contains_all_variables(self) -> None:
        svc = PortAllocatorService(_make_config(base_port=15000))
        alloc = svc.allocate("env-test")
        assert alloc is not None

        snippet = alloc.env_snippet
        lines = snippet.strip().split("\n")
        assert len(lines) == 6

        assert lines[0] == "export AGENT_COORDINATOR_DB_PORT=15000"
        assert lines[1] == "export AGENT_COORDINATOR_REST_PORT=15001"
        assert lines[2] == "export AGENT_COORDINATOR_REALTIME_PORT=15002"
        assert lines[3] == "export API_PORT=15003"
        assert lines[4] == f"export COMPOSE_PROJECT_NAME={alloc.compose_project_name}"
        assert lines[5] == "export SUPABASE_URL=http://localhost:15001"

    def test_env_snippet_export_format(self) -> None:
        svc = PortAllocatorService(_make_config())
        alloc = svc.allocate("fmt-test")
        assert alloc is not None

        for line in alloc.env_snippet.strip().split("\n"):
            assert line.startswith("export ")
            assert "=" in line


# ================================================================== #
# 8. compose_project_name uniqueness
# ================================================================== #


class TestComposeProjectName:
    """Different sessions produce different project names in ac-<hex> format."""

    def test_different_sessions_different_names(self) -> None:
        svc = PortAllocatorService(_make_config())
        a = svc.allocate("session-alpha")
        b = svc.allocate("session-beta")
        assert a is not None
        assert b is not None
        assert a.compose_project_name != b.compose_project_name

    def test_project_name_format(self) -> None:
        svc = PortAllocatorService(_make_config())
        alloc = svc.allocate("some-session")
        assert alloc is not None
        name = alloc.compose_project_name
        assert name.startswith("ac-")
        hex_part = name[3:]
        assert len(hex_part) == 8
        int(hex_part, 16)

    def test_project_name_deterministic(self) -> None:
        expected = f"ac-{hashlib.sha256(b'deterministic').hexdigest()[:8]}"
        svc = PortAllocatorService(_make_config())
        alloc = svc.allocate("deterministic")
        assert alloc is not None
        assert alloc.compose_project_name == expected


# ================================================================== #
# 9. Standalone operation without DB config
# ================================================================== #


class TestStandaloneOperation:
    """Port allocator works without any SUPABASE_URL set."""

    def test_works_without_supabase_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

        cfg = PortAllocatorConfig()
        svc = PortAllocatorService(cfg)
        alloc = svc.allocate("standalone")
        assert alloc is not None
        assert alloc.db_port == cfg.base_port

    def test_default_config_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

        cfg = PortAllocatorConfig()
        assert cfg.base_port == 10000
        assert cfg.range_per_session == 100
        assert cfg.ttl_minutes == 120
        assert cfg.max_sessions == 20


# ================================================================== #
# 10. Config validation errors
# ================================================================== #


class TestConfigValidation:
    """Constructor rejects invalid configuration."""

    def test_base_port_below_1024_raises(self) -> None:
        with pytest.raises(ValueError, match="base_port must be >= 1024"):
            PortAllocatorService(_make_config(base_port=1023))

    def test_base_port_exactly_1024_ok(self) -> None:
        svc = PortAllocatorService(_make_config(base_port=1024))
        alloc = svc.allocate("low-port")
        assert alloc is not None
        assert alloc.db_port == 1024

    def test_range_per_session_below_4_raises(self) -> None:
        with pytest.raises(ValueError, match="range_per_session must be >= 4"):
            PortAllocatorService(_make_config(range_per_session=3))

    def test_range_per_session_exactly_4_ok(self) -> None:
        svc = PortAllocatorService(_make_config(range_per_session=4))
        alloc = svc.allocate("tight-range")
        assert alloc is not None


# ================================================================== #
# 11. Singleton: get_port_allocator / reset_port_allocator
# ================================================================== #


class TestSingleton:
    """get_port_allocator returns the same instance; reset clears it."""

    def setup_method(self) -> None:
        reset_port_allocator()

    def teardown_method(self) -> None:
        reset_port_allocator()

    def test_get_returns_singleton(self) -> None:
        cfg = _make_config()
        a = get_port_allocator(cfg)
        b = get_port_allocator(cfg)
        assert a is b

    def test_reset_clears_singleton(self) -> None:
        cfg = _make_config()
        first = get_port_allocator(cfg)
        reset_port_allocator()
        second = get_port_allocator(cfg)
        assert first is not second

    def test_get_without_config_uses_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PORT_ALLOC_BASE", "20000")
        monkeypatch.setenv("PORT_ALLOC_RANGE", "50")
        monkeypatch.setenv("PORT_ALLOC_TTL_MINUTES", "30")
        monkeypatch.setenv("PORT_ALLOC_MAX_SESSIONS", "5")

        svc = get_port_allocator()
        alloc = svc.allocate("env-test")
        assert alloc is not None
        assert alloc.db_port == 20000

    def test_singleton_preserves_state(self) -> None:
        cfg = _make_config()
        svc = get_port_allocator(cfg)
        svc.allocate("persistent")

        same_svc = get_port_allocator()
        allocations = same_svc.status()
        assert len(allocations) == 1
        assert allocations[0].session_id == "persistent"
