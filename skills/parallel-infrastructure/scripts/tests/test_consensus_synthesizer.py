"""Tests for consensus_synthesizer — multi-vendor finding matching and synthesis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from consensus_synthesizer import (
    ConsensusSynthesizer,
    Finding,
    VendorResult,
    _jaccard,
    _tokenize,
    match_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(
    id: int = 1,
    type: str = "security",
    criticality: str = "high",
    description: str = "test finding",
    disposition: str = "fix",
    vendor: str = "codex",
    file_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> Finding:
    return Finding(
        id=id, type=type, criticality=criticality,
        description=description, disposition=disposition,
        vendor=vendor, file_path=file_path,
        line_start=line_start, line_end=line_end,
    )


# ---------------------------------------------------------------------------
# Tokenization + similarity
# ---------------------------------------------------------------------------

class TestTokenization:
    def test_tokenize_basic(self) -> None:
        tokens = _tokenize("Missing input validation on user endpoint")
        assert "missing" in tokens
        assert "input" in tokens
        assert "on" not in tokens  # too short

    def test_jaccard_identical(self) -> None:
        a = {"foo", "bar", "baz"}
        assert _jaccard(a, a) == 1.0

    def test_jaccard_disjoint(self) -> None:
        assert _jaccard({"foo"}, {"bar"}) == 0.0

    def test_jaccard_partial(self) -> None:
        assert 0.0 < _jaccard({"foo", "bar"}, {"bar", "baz"}) < 1.0

    def test_jaccard_empty(self) -> None:
        assert _jaccard(set(), {"foo"}) == 0.0


# ---------------------------------------------------------------------------
# Match scoring
# ---------------------------------------------------------------------------

class TestMatchScore:
    def test_different_types_no_match(self) -> None:
        a = _finding(type="security")
        b = _finding(type="performance")
        score, _ = match_score(a, b)
        assert score == 0.0

    def test_exact_location_match(self) -> None:
        a = _finding(file_path="src/api.py", line_start=42, line_end=45)
        b = _finding(file_path="src/api.py", line_start=43, line_end=50, vendor="gemini")
        score, basis = match_score(a, b)
        assert score >= 0.9
        assert basis == "location+type"

    def test_same_file_similar_description(self) -> None:
        a = _finding(
            file_path="src/api.py",
            description="Missing input validation on user creation endpoint",
        )
        b = _finding(
            file_path="src/api.py",
            description="Input validation missing for user creation API endpoint",
            vendor="gemini",
        )
        score, basis = match_score(a, b)
        assert score >= 0.5
        assert "file" in basis

    def test_no_file_similar_description(self) -> None:
        a = _finding(description="SQL injection risk in query builder module")
        b = _finding(
            description="SQL injection vulnerability in the query builder",
            vendor="gemini",
        )
        score, basis = match_score(a, b)
        assert score >= 0.3
        assert "description" in basis

    def test_no_match_different_descriptions(self) -> None:
        a = _finding(description="Missing rate limiting")
        b = _finding(description="CSS alignment issue in header", vendor="gemini")
        score, _ = match_score(a, b)
        assert score < 0.3


# ---------------------------------------------------------------------------
# Consensus synthesis
# ---------------------------------------------------------------------------

class TestConsensusSynthesizer:
    def test_confirmed_finding(self) -> None:
        """Two vendors agree on same finding with same disposition."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(id=1, file_path="src/api.py", line_start=42, line_end=45, description="Missing auth check on user endpoint", disposition="fix"),
                ]),
                VendorResult(vendor="gemini", findings=[
                    _finding(id=1, file_path="src/api.py", line_start=42, line_end=50, description="Auth check missing on user endpoint", disposition="fix", vendor="gemini"),
                ]),
            ],
        )
        assert result.confirmed_count == 1
        assert result.consensus_findings[0].status == "confirmed"
        assert result.consensus_findings[0].recommended_disposition == "fix"

    def test_unconfirmed_finding(self) -> None:
        """Finding from one vendor only."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(id=1, description="Unique codex-only finding about frobnication"),
                ]),
                VendorResult(vendor="gemini", findings=[
                    _finding(id=1, description="Completely different concern about widgets", vendor="gemini"),
                ]),
            ],
        )
        assert result.unconfirmed_count == 2
        assert all(cf.status == "unconfirmed" for cf in result.consensus_findings)

    def test_disagreement_finding(self) -> None:
        """Two vendors match but disagree on disposition."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(id=1, file_path="src/handler.py", line_start=10, description="Missing error handling for edge case", disposition="fix"),
                ]),
                VendorResult(vendor="gemini", findings=[
                    _finding(id=1, file_path="src/handler.py", line_start=10, description="Error handling missing for edge case scenario", disposition="accept", vendor="gemini"),
                ]),
            ],
        )
        assert result.disagreement_count == 1
        cf = result.consensus_findings[0]
        assert cf.status == "disagreement"
        assert cf.recommended_disposition == "escalate"
        assert cf.vendor_dispositions == {"codex": "fix", "gemini": "accept"}

    def test_quorum_met(self) -> None:
        """Quorum met when enough vendors respond."""
        synth = ConsensusSynthesizer(quorum=2)
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[]),
                VendorResult(vendor="gemini", findings=[]),
            ],
        )
        assert result.quorum_met is True
        assert result.quorum_received == 2

    def test_quorum_not_met(self) -> None:
        """Quorum not met when vendor fails."""
        synth = ConsensusSynthesizer(quorum=2)
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[]),
                VendorResult(vendor="gemini", findings=[], success=False, error="429 capacity"),
            ],
        )
        assert result.quorum_met is False
        assert result.quorum_received == 1

    def test_empty_findings(self) -> None:
        """No findings from any vendor."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[]),
                VendorResult(vendor="gemini", findings=[]),
            ],
        )
        assert result.total_unique == 0
        assert result.blocking_count == 0

    def test_criticality_takes_highest(self) -> None:
        """Confirmed finding uses highest criticality from matched vendors."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(id=1, criticality="medium", description="Input validation missing for API", file_path="src/api.py", line_start=10),
                ]),
                VendorResult(vendor="gemini", findings=[
                    _finding(id=1, criticality="high", description="Missing input validation for API endpoint", vendor="gemini", file_path="src/api.py", line_start=10),
                ]),
            ],
        )
        confirmed = [cf for cf in result.consensus_findings if cf.status == "confirmed"]
        assert len(confirmed) == 1
        assert confirmed[0].agreed_criticality == "high"

    def test_blocking_count(self) -> None:
        """Blocking count includes confirmed fix + all disagreements."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(id=1, description="Security issue with authentication", disposition="fix", file_path="src/auth.py", line_start=5),
                    _finding(id=2, description="Performance concern with database query", disposition="fix", type="performance", file_path="src/db.py", line_start=20),
                ]),
                VendorResult(vendor="gemini", findings=[
                    _finding(id=1, description="Authentication security vulnerability", disposition="fix", vendor="gemini", file_path="src/auth.py", line_start=5),
                    _finding(id=2, description="Database query performance issue", disposition="accept", vendor="gemini", type="performance", file_path="src/db.py", line_start=20),
                ]),
            ],
        )
        # Finding 1: confirmed fix (blocking)
        # Finding 2: disagreement (blocking)
        assert result.blocking_count == 2

    def test_to_dict_schema_conformance(self) -> None:
        """to_dict output has required schema fields."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(id=1, description="Test finding about missing validation"),
                ]),
            ],
        )
        d = synth.to_dict(result)
        assert d["schema_version"] == 1
        assert d["review_type"] == "plan"
        assert d["target"] == "test-feature"
        assert "reviewers" in d
        assert "consensus_findings" in d
        assert "summary" in d
        assert d["summary"]["total_unique_findings"] == 1

    def test_write_report(self, tmp_path: Path) -> None:
        """write_report produces valid JSON file."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[]),
            ],
        )
        output = tmp_path / "reviews" / "consensus.json"
        synth.write_report(result, output)
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["schema_version"] == 1

    def test_finding_from_dict(self) -> None:
        """Finding.from_dict parses review-findings format."""
        data = {
            "id": 3,
            "type": "security",
            "criticality": "high",
            "description": "XSS vulnerability",
            "disposition": "fix",
            "resolution": "Sanitize input",
            "file_path": "src/views.py",
            "line_range": {"start": 10, "end": 20},
        }
        f = Finding.from_dict(data, vendor="codex")
        assert f.id == 3
        assert f.vendor == "codex"
        assert f.file_path == "src/views.py"
        assert f.line_start == 10
        assert f.line_end == 20
