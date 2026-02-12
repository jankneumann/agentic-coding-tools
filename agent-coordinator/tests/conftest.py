"""Pytest fixtures for Agent Coordinator tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import respx

from src.config import AgentConfig, Config, LockConfig, SupabaseConfig, reset_config
from src.db import SupabaseClient

# =============================================================================
# Environment Setup
# =============================================================================


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("AGENT_ID", "test-agent-1")
    monkeypatch.setenv("AGENT_TYPE", "test_agent")
    monkeypatch.setenv("SESSION_ID", "test-session-1")
    monkeypatch.setenv("LOCK_TTL_MINUTES", "30")

    # Reset global config after each test
    yield
    reset_config()


@pytest.fixture
def config():
    """Get test configuration."""
    return Config(
        supabase=SupabaseConfig(
            url="https://test.supabase.co",
            service_key="test-service-key",
        ),
        agent=AgentConfig(
            agent_id="test-agent-1",
            agent_type="test_agent",
            session_id="test-session-1",
        ),
        lock=LockConfig(
            default_ttl_minutes=30,
        ),
    )


@pytest.fixture
def db_client(config):
    """Get a Supabase client configured for testing."""
    return SupabaseClient(config.supabase)


# =============================================================================
# Mock Supabase Responses
# =============================================================================


@pytest.fixture
def mock_supabase():
    """Mock Supabase API responses."""
    with respx.mock(assert_all_called=False) as respx_mock:
        yield respx_mock


@pytest.fixture
def lock_acquired_response():
    """Response for successful lock acquisition."""
    expires = datetime.now(UTC) + timedelta(minutes=30)
    return {
        "success": True,
        "action": "acquired",
        "file_path": "src/main.py",
        "expires_at": expires.isoformat(),
    }


@pytest.fixture
def lock_conflict_response():
    """Response when lock is held by another agent."""
    locked_at = datetime.now(UTC) - timedelta(minutes=5)
    expires = locked_at + timedelta(minutes=30)
    return {
        "success": False,
        "reason": "locked_by_other",
        "locked_by": "other-agent",
        "agent_type": "claude_code",
        "locked_at": locked_at.isoformat(),
        "expires_at": expires.isoformat(),
        "lock_reason": "working on feature X",
    }


@pytest.fixture
def lock_released_response():
    """Response for successful lock release."""
    return {
        "success": True,
        "action": "released",
        "file_path": "src/main.py",
    }


@pytest.fixture
def active_locks_response():
    """Response for checking active locks."""
    now = datetime.now(UTC)
    return [
        {
            "file_path": "src/main.py",
            "locked_by": "agent-1",
            "agent_type": "claude_code",
            "session_id": "session-1",
            "locked_at": (now - timedelta(minutes=10)).isoformat(),
            "expires_at": (now + timedelta(minutes=20)).isoformat(),
            "reason": "refactoring",
            "metadata": {},
        },
        {
            "file_path": "src/utils.py",
            "locked_by": "agent-2",
            "agent_type": "codex",
            "session_id": "session-2",
            "locked_at": (now - timedelta(minutes=5)).isoformat(),
            "expires_at": (now + timedelta(minutes=25)).isoformat(),
            "reason": "adding tests",
            "metadata": {},
        },
    ]


@pytest.fixture
def task_claimed_response():
    """Response for successful task claim."""
    return {
        "success": True,
        "task_id": str(uuid4()),
        "task_type": "refactor",
        "description": "Refactor authentication module",
        "input_data": {"files": ["src/auth.py"]},
        "priority": 3,
        "deadline": None,
    }


@pytest.fixture
def no_tasks_response():
    """Response when no tasks are available."""
    return {
        "success": False,
        "reason": "no_tasks_available",
    }


@pytest.fixture
def task_completed_response():
    """Response for successful task completion."""
    return {
        "success": True,
        "status": "completed",
        "task_id": str(uuid4()),
    }


@pytest.fixture
def task_submitted_response():
    """Response for successful task submission."""
    return {
        "success": True,
        "task_id": str(uuid4()),
    }


@pytest.fixture
def pending_tasks_response():
    """Response for listing pending tasks."""
    now = datetime.now(UTC)
    return [
        {
            "id": str(uuid4()),
            "task_type": "test",
            "description": "Write unit tests for cache module",
            "status": "pending",
            "priority": 2,
            "input_data": {"files": ["src/cache.py"]},
            "claimed_by": None,
            "claimed_at": None,
            "result": None,
            "error_message": None,
            "depends_on": None,
            "deadline": None,
            "created_at": now.isoformat(),
            "completed_at": None,
        },
        {
            "id": str(uuid4()),
            "task_type": "refactor",
            "description": "Simplify error handling",
            "status": "pending",
            "priority": 5,
            "input_data": None,
            "claimed_by": None,
            "claimed_at": None,
            "result": None,
            "error_message": None,
            "depends_on": None,
            "deadline": (now + timedelta(days=1)).isoformat(),
            "created_at": now.isoformat(),
            "completed_at": None,
        },
    ]
