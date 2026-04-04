"""Tests for Langfuse FastAPI tracing middleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.langfuse_middleware import LangfuseTracingMiddleware


@pytest.fixture
def mock_langfuse():
    """Set up a mock Langfuse client in the tracing module."""
    import src.langfuse_tracing as mod

    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_span = MagicMock()
    mock_client.trace.return_value = mock_trace
    mock_trace.span.return_value = mock_span

    original = mod._langfuse
    mod._langfuse = mock_client
    yield mock_client, mock_trace, mock_span
    mod._langfuse = original


@pytest.fixture
def app_with_middleware(mock_langfuse):
    """Create a minimal FastAPI app with the middleware."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(LangfuseTracingMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/locks/acquire")
    async def acquire():
        return {"acquired": True}

    @app.get("/test-endpoint")
    async def test_endpoint():
        return {"result": "ok"}

    return app


class TestMiddlewareSkipPaths:
    def test_skips_health_check(self, app_with_middleware, mock_langfuse):
        client = TestClient(app_with_middleware)
        mock_client, _, _ = mock_langfuse

        response = client.get("/health")
        assert response.status_code == 200

        # Health check should NOT create a trace
        mock_client.trace.assert_not_called()


class TestMiddlewareTracing:
    def test_traces_api_request(self, app_with_middleware, mock_langfuse):
        client = TestClient(app_with_middleware)
        mock_client, mock_trace, mock_span = mock_langfuse

        response = client.get("/test-endpoint")
        assert response.status_code == 200

        # Should create a trace and span
        mock_client.trace.assert_called_once()
        call_kwargs = mock_client.trace.call_args.kwargs
        assert call_kwargs["name"] == "api:test-endpoint"
        assert "coordinator" in call_kwargs["tags"]

        mock_trace.span.assert_called_once()

    def test_traces_post_request(self, app_with_middleware, mock_langfuse):
        client = TestClient(app_with_middleware)
        mock_client, mock_trace, _ = mock_langfuse

        response = client.post("/locks/acquire")
        assert response.status_code == 200

        call_kwargs = mock_client.trace.call_args.kwargs
        assert call_kwargs["name"] == "api:locks/acquire"
        assert "post" in call_kwargs["tags"]


class TestMiddlewareDisabled:
    def test_passes_through_when_disabled(self):
        """When Langfuse is None, middleware is a pass-through."""
        import src.langfuse_tracing as mod

        original = mod._langfuse
        mod._langfuse = None

        try:
            from fastapi import FastAPI

            app = FastAPI()
            app.add_middleware(LangfuseTracingMiddleware)

            @app.get("/test")
            async def test():
                return {"ok": True}

            client = TestClient(app)
            response = client.get("/test")
            assert response.status_code == 200
            assert response.json() == {"ok": True}
        finally:
            mod._langfuse = original


class TestResolveAgentId:
    def test_anonymous_without_key(self):
        from src.langfuse_middleware import _resolve_agent_id

        mock_request = MagicMock()
        mock_request.headers = {}
        assert _resolve_agent_id(mock_request) == "anonymous"

    def test_with_api_key(self):
        from src.langfuse_middleware import _resolve_agent_id

        mock_request = MagicMock()
        mock_request.headers = {"x-api-key": "test-key"}

        with patch("src.config.get_config") as mock_config:
            mock_config.return_value.api.api_key_identities = {
                "test-key": {"agent_id": "codex-1", "agent_type": "codex"}
            }
            assert _resolve_agent_id(mock_request) == "codex-1"
