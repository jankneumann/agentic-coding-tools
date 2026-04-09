"""Tests for the help service — progressive discovery for coordinator capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.help_service import get_help_overview, get_help_topic, list_topic_names

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# =============================================================================
# Unit tests for help_service
# =============================================================================


class TestHelpOverview:
    """Tests for the overview (no-topic) mode."""

    def test_returns_version(self) -> None:
        result = get_help_overview()
        assert "version" in result
        assert result["version"] == "0.2.0"

    def test_returns_usage_hint(self) -> None:
        result = get_help_overview()
        assert "usage" in result
        assert "topic" in result["usage"].lower()

    def test_returns_all_topics(self) -> None:
        result = get_help_overview()
        topic_names = [t["topic"] for t in result["topics"]]
        # Core topics that must always exist
        assert "locks" in topic_names
        assert "work-queue" in topic_names
        assert "memory" in topic_names
        assert "handoffs" in topic_names
        assert "guardrails" in topic_names

    def test_each_topic_has_summary_and_count(self) -> None:
        result = get_help_overview()
        for topic in result["topics"]:
            assert "topic" in topic
            assert "summary" in topic
            assert "tools_count" in topic
            assert isinstance(topic["tools_count"], int)
            assert topic["tools_count"] > 0

    def test_overview_is_compact(self) -> None:
        """Overview should be concise — under ~300 tokens estimated."""
        import json

        result = get_help_overview()
        serialized = json.dumps(result)
        # Rough token estimate: ~4 chars per token
        estimated_tokens = len(serialized) / 4
        assert estimated_tokens < 500, (
            f"Overview is ~{estimated_tokens:.0f} tokens — should be compact"
        )


class TestHelpTopic:
    """Tests for the detailed topic mode."""

    def test_known_topic_returns_detail(self) -> None:
        result = get_help_topic("locks")
        assert result is not None
        assert result["topic"] == "locks"

    def test_unknown_topic_returns_none(self) -> None:
        result = get_help_topic("nonexistent-topic")
        assert result is None

    def test_detail_has_required_fields(self) -> None:
        result = get_help_topic("locks")
        assert result is not None
        required_fields = [
            "topic", "summary", "description", "tools",
            "workflow", "best_practices", "examples", "related_topics",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_tools_list_is_nonempty(self) -> None:
        result = get_help_topic("locks")
        assert result is not None
        assert len(result["tools"]) > 0
        assert "acquire_lock" in result["tools"]

    def test_workflow_has_ordered_steps(self) -> None:
        result = get_help_topic("locks")
        assert result is not None
        assert len(result["workflow"]) >= 2
        # Steps should be numbered
        assert result["workflow"][0].startswith("1.")

    def test_examples_have_description_and_code(self) -> None:
        result = get_help_topic("locks")
        assert result is not None
        assert len(result["examples"]) > 0
        for ex in result["examples"]:
            assert "description" in ex
            assert "code" in ex

    def test_all_registered_topics_are_valid(self) -> None:
        """Every registered topic should return valid detail."""
        for name in list_topic_names():
            detail = get_help_topic(name)
            assert detail is not None, f"Topic {name!r} registered but returns None"
            assert detail["topic"] == name
            assert len(detail["tools"]) > 0

    def test_related_topics_exist(self) -> None:
        """Related topics should reference real topics."""
        all_names = set(list_topic_names())
        for name in all_names:
            detail = get_help_topic(name)
            assert detail is not None
            for related in detail["related_topics"]:
                assert related in all_names, (
                    f"Topic {name!r} references nonexistent related topic {related!r}"
                )


class TestListTopicNames:
    """Tests for the topic listing function."""

    def test_returns_list(self) -> None:
        names = list_topic_names()
        assert isinstance(names, list)
        assert len(names) > 0

    def test_all_names_are_strings(self) -> None:
        for name in list_topic_names():
            assert isinstance(name, str)


# =============================================================================
# CLI tests
# =============================================================================


class TestHelpCli:
    """Tests for the help CLI subcommand."""

    def test_help_overview_exit_code(self) -> None:
        from src.coordination_cli import main

        result = main(["help"])
        assert result == 0

    def test_help_topic_exit_code(self) -> None:
        from src.coordination_cli import main

        result = main(["help", "locks"])
        assert result == 0

    def test_help_unknown_topic_exit_code(self) -> None:
        from src.coordination_cli import main

        result = main(["help", "nonexistent"])
        assert result == 1

    def test_help_json_overview(self) -> None:
        import io
        import json
        import sys

        from src.coordination_cli import main

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            result = main(["--json", "help"])
        finally:
            sys.stdout = old_stdout

        assert result == 0
        data = json.loads(captured.getvalue())
        assert "topics" in data

    def test_help_json_topic(self) -> None:
        import io
        import json
        import sys

        from src.coordination_cli import main

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            result = main(["--json", "help", "locks"])
        finally:
            sys.stdout = old_stdout

        assert result == 0
        data = json.loads(captured.getvalue())
        assert data["topic"] == "locks"
        assert "tools" in data


# =============================================================================
# HTTP API tests
# =============================================================================


_TEST_KEY = "test-key-001"


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch config so the API starts."""
    from src.config import reset_config

    reset_config()

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")

    reset_config()

    yield  # type: ignore[misc]

    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    from fastapi.testclient import TestClient as _TestClient

    from src.coordination_api import create_coordination_api

    app = create_coordination_api()
    return _TestClient(app)


class TestHelpApi:
    """Tests for the HTTP API help endpoints."""

    def test_get_help_overview(self, client: TestClient) -> None:
        """GET /help returns overview without auth."""
        resp = client.get("/help")
        assert resp.status_code == 200
        data = resp.json()
        assert "topics" in data
        assert "version" in data

    def test_get_help_topic(self, client: TestClient) -> None:
        """GET /help/locks returns detailed help."""
        resp = client.get("/help/locks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic"] == "locks"
        assert "workflow" in data
        assert "best_practices" in data

    def test_get_help_unknown_topic(self, client: TestClient) -> None:
        """GET /help/nonexistent returns 404 with suggestions."""
        resp = client.get("/help/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert "available_topics" in data

    def test_no_auth_required(self, client: TestClient) -> None:
        """Help endpoints should not require API key."""
        resp = client.get("/help")
        assert resp.status_code == 200  # Not 401
