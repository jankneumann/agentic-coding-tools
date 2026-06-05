"""Tests for the adapter base class contract.

Covers:
- Abstract methods must be implemented
- Fail-soft warning helpers
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestAdapterBase:
    """Test the abstract base class contract."""

    def test_cannot_instantiate_directly(self) -> None:
        from adapters.base import AdapterBase

        with pytest.raises(TypeError):
            AdapterBase()  # type: ignore[abstract]

    def test_subclass_must_implement_discover(self) -> None:
        from adapters.base import AdapterBase
        from normalize import NormalizedEvent, SessionSummary

        class IncompleteAdapter(AdapterBase):
            HARNESS_ID = "test"

            def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
                return []

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore[abstract]

    def test_subclass_must_implement_normalize(self) -> None:
        from adapters.base import AdapterBase
        from normalize import SessionSummary

        class IncompleteAdapter(AdapterBase):
            HARNESS_ID = "test"

            def discover_sessions(self) -> list[SessionSummary]:
                return []

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore[abstract]

    def test_complete_subclass_instantiates(self) -> None:
        from adapters.base import AdapterBase
        from normalize import NormalizedEvent, SessionSummary

        class CompleteAdapter(AdapterBase):
            HARNESS_ID = "test"

            def discover_sessions(self) -> list[SessionSummary]:
                return []

            def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
                return []

        adapter = CompleteAdapter()
        assert adapter.HARNESS_ID == "test"
        assert adapter.discover_sessions() == []
        assert adapter.normalize_session("any") == []

    def test_warn_unavailable_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        from adapters.base import AdapterBase
        from normalize import NormalizedEvent, SessionSummary

        class TestAdapter(AdapterBase):
            HARNESS_ID = "test_harness"

            def discover_sessions(self) -> list[SessionSummary]:
                return []

            def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
                return []

        adapter = TestAdapter()
        with caplog.at_level(logging.WARNING):
            adapter._warn_unavailable("path not found")

        assert "test_harness" in caplog.text
        assert "unavailable" in caplog.text

    def test_warn_parse_error_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        from adapters.base import AdapterBase
        from normalize import NormalizedEvent, SessionSummary

        class TestAdapter(AdapterBase):
            HARNESS_ID = "test_harness"

            def discover_sessions(self) -> list[SessionSummary]:
                return []

            def normalize_session(self, session_id: str) -> list[NormalizedEvent]:
                return []

        adapter = TestAdapter()
        with caplog.at_level(logging.WARNING):
            adapter._warn_parse_error("sess-123", "invalid JSON")

        assert "test_harness" in caplog.text
        assert "sess-123" in caplog.text
        assert "invalid JSON" in caplog.text
