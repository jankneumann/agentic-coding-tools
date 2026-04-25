"""3-step persistence pipeline tests for PhaseRecord.write_both().

Covers all four spec scenarios for the persistence pipeline:
- All three steps succeed
- Coordinator unavailable triggers local-file fallback
- Sanitizer failure does not block coordinator write
- Markdown append failure does not block coordinator write
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))

from phase_record import (  # noqa: E402
    Decision,
    FileRef,
    PhaseRecord,
    PhaseWriteResult,
)


def _record() -> PhaseRecord:
    return PhaseRecord(
        change_id="my-change",
        phase_name="Plan",
        agent_type="claude_code",
        summary="A representative phase summary.",
        decisions=[Decision(title="T", rationale="R", capability="cap")],
        relevant_files=[FileRef(path="src/foo.py", description="entrypoint")],
    )


class _StubWriter:
    """Captures calls to a stand-in coordinator writer."""

    def __init__(self, *, response: dict[str, Any] | None = None,
                 raise_exc: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response
        self._raise = raise_exc

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raise is not None:
            raise self._raise
        return self._response or {}


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fresh tmp working directory and chdir into it.

    All paths in PhaseRecord.write_both default to relative paths
    (`openspec/changes/<id>/...`), so changing CWD isolates each test.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestStep1Success:
    def test_writes_session_log_md(self, workdir: Path) -> None:
        rec = _record()
        result = rec.write_both(coordinator_writer=_StubWriter(response={"handoff_id": "h-1"}))
        assert result.markdown_path is not None
        assert result.markdown_path.exists()
        body = result.markdown_path.read_text(encoding="utf-8")
        assert "## Phase: Plan" in body
        assert "**Agent**: claude_code" in body
        assert "`architectural: cap`" in body

    def test_appends_to_existing_session_log(self, workdir: Path) -> None:
        log_path = workdir / "openspec/changes/my-change/session-log.md"
        log_path.parent.mkdir(parents=True)
        log_path.write_text(
            "# Session Log: my-change\n\n## Phase: Earlier (2026-04-20)\n\n### Context\nfirst.\n",
            encoding="utf-8",
        )
        rec = _record()
        rec.write_both(coordinator_writer=_StubWriter(response={"handoff_id": "h-1"}))
        body = log_path.read_text(encoding="utf-8")
        # Both phases present
        assert "Phase: Earlier" in body
        assert "Phase: Plan" in body


class TestStep2SanitizationHappy:
    def test_sanitization_runs_in_place(self, workdir: Path) -> None:
        rec = _record()
        result = rec.write_both(coordinator_writer=_StubWriter(response={"handoff_id": "h-1"}))
        # Sanitizer succeeded — no warnings about step 2
        assert result.sanitized is True
        assert not any("step_2_sanitize" in w for w in result.warnings)


class TestStep3CoordinatorSuccess:
    """Spec scenario: All three steps succeed."""

    def test_handoff_id_returned(self, workdir: Path) -> None:
        writer = _StubWriter(response={"handoff_id": "abc-123"})
        rec = _record()
        result = rec.write_both(coordinator_writer=writer)
        assert result.handoff_id == "abc-123"
        assert result.handoff_local_path is None

    def test_writer_called_with_payload(self, workdir: Path) -> None:
        writer = _StubWriter(response={"handoff_id": "h"})
        rec = _record()
        rec.write_both(coordinator_writer=writer)
        assert len(writer.calls) == 1
        call = writer.calls[0]
        assert call["agent_id"] == "claude_code"
        assert call["summary"] == rec.summary
        assert call["content"]["agent_name"] == "claude_code"
        assert call["content"]["decisions"][0]["capability"] == "cap"

    def test_no_warnings_on_full_success(self, workdir: Path) -> None:
        writer = _StubWriter(response={"handoff_id": "h"})
        rec = _record()
        result = rec.write_both(coordinator_writer=writer)
        assert result.warnings == []

    def test_bridge_wrapper_response_shape_extracts_id(self, workdir: Path) -> None:
        """The coordination_bridge wraps responses as {available, result, ...}."""
        writer = _StubWriter(
            response={"available": True, "result": {"handoff_id": "wrapped-id"}}
        )
        rec = _record()
        result = rec.write_both(coordinator_writer=writer)
        assert result.handoff_id == "wrapped-id"


class TestStep3CoordinatorUnavailableFallback:
    """Spec scenario: Coordinator unavailable triggers local-file fallback."""

    def test_coordinator_returns_no_id_writes_local_file(self, workdir: Path) -> None:
        writer = _StubWriter(response={"available": False, "error": "unreachable"})
        rec = _record()
        result = rec.write_both(coordinator_writer=writer)
        assert result.handoff_id is None
        assert result.handoff_local_path is not None
        assert result.handoff_local_path.exists()
        envelope = json.loads(result.handoff_local_path.read_text(encoding="utf-8"))
        assert envelope["schema_version"] == 1
        assert envelope["coordinator_error"]["error_type"] == "rpc_failed"
        assert envelope["payload"]["agent_name"] == "claude_code"
        assert envelope["payload"]["decisions"][0]["capability"] == "cap"

    def test_coordinator_raises_writes_local_file(self, workdir: Path) -> None:
        writer = _StubWriter(raise_exc=ConnectionError("network down"))
        rec = _record()
        result = rec.write_both(coordinator_writer=writer)
        assert result.handoff_id is None
        assert result.handoff_local_path is not None
        envelope = json.loads(result.handoff_local_path.read_text(encoding="utf-8"))
        assert envelope["coordinator_error"]["error_type"] == "unreachable"
        assert "network down" in envelope["coordinator_error"]["message"]

    def test_local_file_path_uses_phase_slug(self, workdir: Path) -> None:
        rec = PhaseRecord(
            change_id="my-change",
            phase_name="Implementation Iteration 2",
            agent_type="x",
            summary="s",
        )
        writer = _StubWriter(response={"available": False, "error": "down"})
        result = rec.write_both(coordinator_writer=writer)
        assert result.handoff_local_path is not None
        assert result.handoff_local_path.name.startswith("implementation-iteration-2-")
        assert result.handoff_local_path.name.endswith(".json")

    def test_local_file_index_increments(self, workdir: Path) -> None:
        rec = _record()
        writer = _StubWriter(response={"available": False, "error": "down"})
        first = rec.write_both(coordinator_writer=writer)
        second = rec.write_both(coordinator_writer=writer)
        assert first.handoff_local_path is not None
        assert second.handoff_local_path is not None
        assert first.handoff_local_path != second.handoff_local_path
        assert "plan-1.json" in str(first.handoff_local_path)
        assert "plan-2.json" in str(second.handoff_local_path)

    def test_warning_recorded_on_fallback(self, workdir: Path) -> None:
        writer = _StubWriter(response={"available": False, "error": "down"})
        rec = _record()
        result = rec.write_both(coordinator_writer=writer)
        assert any("step_3_coordinator" in w for w in result.warnings)


class TestStep2SanitizerFailureDoesNotBlock:
    """Spec scenario: Sanitizer failure does not block coordinator write."""

    def test_missing_sanitizer_logs_warning_but_writes_handoff(
        self, workdir: Path
    ) -> None:
        writer = _StubWriter(response={"handoff_id": "h-after-sanitize-fail"})
        rec = _record()
        result = rec.write_both(
            coordinator_writer=writer,
            sanitizer_script=workdir / "no-such-sanitizer.py",  # forces failure
        )
        # Markdown still written, handoff still written, but sanitized=False
        assert result.markdown_path is not None
        assert result.markdown_path.exists()
        assert result.handoff_id == "h-after-sanitize-fail"
        assert result.sanitized is False
        assert any("step_2_sanitize" in w for w in result.warnings)

    def test_sanitizer_nonzero_exit_logs_warning(
        self, workdir: Path
    ) -> None:
        # Create a sanitizer script that always exits non-zero
        bad_sanitizer = workdir / "bad_sanitizer.py"
        bad_sanitizer.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
        writer = _StubWriter(response={"handoff_id": "h"})
        rec = _record()
        result = rec.write_both(
            coordinator_writer=writer, sanitizer_script=bad_sanitizer
        )
        assert result.sanitized is False
        assert result.handoff_id == "h"
        assert any("step_2_sanitize" in w for w in result.warnings)


class TestStep1AppendFailureDoesNotBlock:
    """Spec scenario: Markdown append failure does not block coordinator write.

    We simulate failure by pointing the session-log path at a directory that
    cannot be created (a path component that's a regular file).
    """

    def test_append_failure_still_writes_coordinator(
        self, workdir: Path
    ) -> None:
        # Create a regular file where the directory should be
        blocker = workdir / "openspec"
        blocker.write_text("not a directory", encoding="utf-8")

        writer = _StubWriter(response={"handoff_id": "h-after-append-fail"})
        rec = _record()
        result = rec.write_both(coordinator_writer=writer)
        assert result.markdown_path is None
        assert result.handoff_id == "h-after-append-fail"
        assert any("step_1_markdown" in w for w in result.warnings)


class TestNoWriterAvailable:
    def test_no_writer_falls_back_to_local_file(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Patch _default_coordinator_writer to return None
        from phase_record import PhaseRecord as PR

        monkeypatch.setattr(PR, "_default_coordinator_writer", lambda self: None)
        rec = _record()
        result = rec.write_both(coordinator_writer=None)
        assert result.handoff_id is None
        assert result.handoff_local_path is not None
        envelope = json.loads(result.handoff_local_path.read_text(encoding="utf-8"))
        assert envelope["coordinator_error"]["error_type"] == "unknown"


class TestResultShape:
    def test_returns_phase_write_result_dataclass(self, workdir: Path) -> None:
        rec = _record()
        result = rec.write_both(coordinator_writer=_StubWriter(response={"handoff_id": "h"}))
        assert isinstance(result, PhaseWriteResult)
