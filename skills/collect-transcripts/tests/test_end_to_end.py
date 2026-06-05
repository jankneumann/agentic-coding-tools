"""End-to-end test: fixture transcript -> triage -> deep-analyze -> findings.

Verifies the full pipeline: ingest fixture -> sanitize -> triage -> flag ->
deep-analyze -> produce findings with source:transcript-mined tags.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "claude_code_cli"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestEndToEndPipeline:
    """Full pipeline: ingest -> sanitize -> triage -> deep-analyze."""

    def test_claude_cli_fixture_through_full_pipeline(
        self, tmp_path: Path
    ) -> None:
        """Feed a fixture through the entire transcript mining pipeline."""
        from adapters.claude_code_cli import ClaudeCodeCLIAdapter
        from deep_analyze import analyze_session_heuristic
        from sanitize_events import sanitize_event_stream
        from triage import triage_session

        # Step 1: Ingest from fixture
        proj_dir = tmp_path / ".claude" / "projects" / "-Users-me-proj"
        proj_dir.mkdir(parents=True)
        fixture = FIXTURES_DIR / "session-abc123.jsonl"
        (proj_dir / "session-abc123.jsonl").write_text(fixture.read_text())

        adapter = ClaudeCodeCLIAdapter(
            base_dir=str(tmp_path / ".claude" / "projects")
        )

        # Discover
        sessions = adapter.discover_sessions()
        assert len(sessions) >= 1

        # Normalize
        events = adapter.normalize_session("abc123")
        assert len(events) > 0

        # Step 2: Sanitize
        sanitized_events, redactions = sanitize_event_stream(events)
        assert len(sanitized_events) == len(events)

        # Step 3: Triage
        score = triage_session(sanitized_events, session_id="abc123", threshold=0.1)
        # The fixture is a clean session, so it may or may not flag
        assert score.session_id == "abc123"
        assert score.event_count == len(sanitized_events)

        # Step 4: Deep analyze (even if not flagged, test the analysis)
        findings = analyze_session_heuristic(sanitized_events, score)

        # Step 5: Verify findings schema
        for finding in findings:
            tags = finding.to_memory_tags()
            assert any(t.startswith("source:") for t in tags)
            assert any(t.startswith("failure_type:") for t in tags)
            assert finding.source == "transcript-mined"

    def test_struggling_session_produces_findings(self, tmp_path: Path) -> None:
        """A synthetic struggling session should produce findings."""
        from deep_analyze import analyze_session_heuristic
        from normalize import ContentBlock, ContentType, EventRole, NormalizedEvent
        from sanitize_events import sanitize_event_stream
        from triage import triage_session

        # Build a synthetic struggling session
        events = [
            NormalizedEvent(
                event_id="e0",
                session_id="struggle-sess",
                role=EventRole.USER,
                content=[
                    ContentBlock(
                        type=ContentType.TEXT,
                        text="Fix the failing test",
                    )
                ],
                harness="claude_code_cli",
                sequence_number=0,
            ),
        ]
        # Add retry storm: 5 consecutive Read calls
        for i in range(1, 6):
            events.append(
                NormalizedEvent(
                    event_id=f"e{i}",
                    session_id="struggle-sess",
                    role=EventRole.ASSISTANT,
                    content=[
                        ContentBlock(
                            type=ContentType.TOOL_USE,
                            tool_name="Read",
                            tool_use_id=f"tu-{i}",
                        )
                    ],
                    harness="claude_code_cli",
                    sequence_number=i,
                )
            )
        # Add tool errors
        for i in range(6, 9):
            events.append(
                NormalizedEvent(
                    event_id=f"e{i}",
                    session_id="struggle-sess",
                    role=EventRole.TOOL,
                    content=[
                        ContentBlock(
                            type=ContentType.TOOL_RESULT,
                            text="Error: file not found",
                            tool_use_id=f"tu-{i}",
                            is_error=True,
                        )
                    ],
                    harness="claude_code_cli",
                    sequence_number=i,
                )
            )
        # Add user correction
        events.append(
            NormalizedEvent(
                event_id="e9",
                session_id="struggle-sess",
                role=EventRole.USER,
                content=[
                    ContentBlock(
                        type=ContentType.TEXT,
                        text="That file doesn't exist, try another approach",
                    )
                ],
                harness="claude_code_cli",
                sequence_number=9,
            )
        )

        # Sanitize
        sanitized, _ = sanitize_event_stream(events)

        # Triage
        score = triage_session(sanitized, session_id="struggle-sess", threshold=5.0)
        assert score.flagged_for_deep_analysis
        assert score.retry_count >= 4
        assert score.tool_error_count >= 3

        # Deep analyze
        findings = analyze_session_heuristic(sanitized, score)
        assert len(findings) >= 1

        # Verify retry storm finding
        retry_findings = [f for f in findings if f.failure_type == "retry_storm"]
        assert len(retry_findings) >= 1
        assert retry_findings[0].source == "transcript-mined"

        # Verify tool error finding
        error_findings = [f for f in findings if f.failure_type == "tool_error"]
        assert len(error_findings) >= 1

        # Verify all findings have correct tags
        for finding in findings:
            tags = finding.to_memory_tags()
            assert "source:transcript-mined" in tags

    def test_findings_round_trip_through_jsonl(self) -> None:
        """Verify findings survive JSON serialization (for episodic memory)."""
        from deep_analyze import TranscriptFinding

        finding = TranscriptFinding(
            session_id="s1",
            failure_type="retry_storm",
            capability_gap="Agent retried Read 5 times",
            affected_skill="implement-feature",
            severity="high",
            source="transcript-mined",
            description="Retry storm detected",
            evidence=["retry_count=5"],
        )
        serialized = json.dumps(finding.to_dict())
        restored = TranscriptFinding.from_dict(json.loads(serialized))
        assert restored.failure_type == "retry_storm"
        assert restored.source == "transcript-mined"
        assert restored.to_memory_tags() == finding.to_memory_tags()
