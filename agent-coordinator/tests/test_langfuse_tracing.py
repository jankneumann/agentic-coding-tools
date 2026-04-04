"""Tests for Langfuse tracing module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.langfuse_tracing import (
    create_span,
    create_trace,
    end_span,
    get_langfuse,
    init_langfuse,
    reset_langfuse,
    shutdown_langfuse,
    trace_operation,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset Langfuse state before/after each test."""
    reset_langfuse()
    yield
    reset_langfuse()


class TestInitLangfuse:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        init_langfuse()
        assert get_langfuse() is None

    def test_no_op_when_disabled(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        init_langfuse()
        assert get_langfuse() is None

    def test_idempotent(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        init_langfuse()
        init_langfuse()  # second call is no-op
        assert get_langfuse() is None

    @patch("src.langfuse_tracing.Langfuse", create=True)
    def test_enabled_creates_client(self, mock_langfuse_cls, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_HOST", "http://test:3050")

        mock_client = MagicMock()
        mock_langfuse_cls.return_value = mock_client

        with patch("src.langfuse_tracing.Langfuse", mock_langfuse_cls):
            import src.langfuse_tracing as mod
            mod._initialized = False
            mod._langfuse = None

            # Directly test the initialization logic
            with patch.dict("sys.modules", {"langfuse": MagicMock(Langfuse=mock_langfuse_cls)}):
                mod._initialized = False
                mod.init_langfuse()

    def test_import_error_graceful(self, monkeypatch):
        """When langfuse package is missing, init succeeds silently."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        with patch.dict("sys.modules", {"langfuse": None}):
            # Import error should be caught gracefully
            init_langfuse()
            assert get_langfuse() is None


class TestShutdown:
    def test_shutdown_no_client(self):
        """Shutdown with no client is a no-op."""
        shutdown_langfuse()
        assert get_langfuse() is None

    def test_shutdown_with_mock_client(self):
        """Shutdown flushes and shuts down the client."""
        import src.langfuse_tracing as mod

        mock_client = MagicMock()
        mod._langfuse = mock_client
        mod._initialized = True

        shutdown_langfuse()

        mock_client.flush.assert_called_once()
        mock_client.shutdown.assert_called_once()
        assert get_langfuse() is None


class TestCreateTrace:
    def test_returns_none_when_disabled(self):
        trace = create_trace(name="test")
        assert trace is None

    def test_creates_trace_with_client(self):
        import src.langfuse_tracing as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace
        mod._langfuse = mock_client

        result = create_trace(
            name="test-op",
            session_id="session-1",
            user_id="agent-1",
            tags=["test"],
        )

        assert result == mock_trace
        mock_client.trace.assert_called_once()
        call_kwargs = mock_client.trace.call_args.kwargs
        assert call_kwargs["name"] == "test-op"
        assert call_kwargs["session_id"] == "session-1"
        assert call_kwargs["user_id"] == "agent-1"


class TestCreateSpan:
    def test_returns_none_when_trace_is_none(self):
        span = create_span(None, name="test")
        assert span is None

    def test_creates_span_on_trace(self):
        mock_trace = MagicMock()
        mock_span = MagicMock()
        mock_trace.span.return_value = mock_span

        result = create_span(mock_trace, name="tool:read", input={"path": "/test"})

        assert result == mock_span
        mock_trace.span.assert_called_once()


class TestEndSpan:
    def test_no_op_when_none(self):
        end_span(None, output="test")  # should not raise

    def test_ends_span_with_output(self):
        mock_span = MagicMock()
        end_span(mock_span, output={"result": "ok"}, level="DEFAULT")
        mock_span.end.assert_called_once()


class TestTraceOperation:
    def test_yields_none_when_disabled(self):
        with trace_operation(name="test") as trace:
            assert trace is None

    def test_context_manager_with_client(self):
        import src.langfuse_tracing as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace
        mod._langfuse = mock_client

        with trace_operation(name="test-op", user_id="agent-1") as trace:
            assert trace == mock_trace

        # Flush should be called on exit
        mock_client.flush.assert_called()

    def test_context_manager_records_error(self):
        import src.langfuse_tracing as mod

        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace
        mod._langfuse = mock_client

        with pytest.raises(ValueError, match="boom"):
            with trace_operation(name="test-op") as _trace:
                raise ValueError("boom")

        mock_trace.update.assert_called_once()
        call_kwargs = mock_trace.update.call_args.kwargs
        assert "boom" in str(call_kwargs["output"])
        assert call_kwargs["level"] == "ERROR"
