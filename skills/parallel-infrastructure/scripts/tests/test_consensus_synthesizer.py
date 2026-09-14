"""Tests for consensus_synthesizer — multi-vendor finding matching and synthesis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from consensus_synthesizer import (
    ConsensusSynthesizer,
    Finding,
    VendorResult,
    _coverage_quorum_threshold,
    _eligible_vendor_count,
    _jaccard,
    _paths_match,
    _reviewed_files_from_coverage,
    _tokenize,
    _types_compatible,
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
    existing_code: str | None = None,
    axis: str = "correctness",
) -> Finding:
    return Finding(
        id=id, type=type, criticality=criticality,
        description=description, disposition=disposition,
        vendor=vendor, file_path=file_path,
        line_start=line_start, line_end=line_end,
        existing_code=existing_code, axis=axis,
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
        b = _finding(file_path="src/api.py", line_start=43, line_end=50, vendor="grok")
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
            vendor="grok",
        )
        score, basis = match_score(a, b)
        assert score >= 0.5
        assert "file" in basis

    def test_no_file_similar_description(self) -> None:
        a = _finding(description="SQL injection risk in query builder module")
        b = _finding(
            description="SQL injection vulnerability in the query builder",
            vendor="grok",
        )
        score, basis = match_score(a, b)
        assert score >= 0.3
        assert "description" in basis

    def test_no_match_different_descriptions(self) -> None:
        a = _finding(description="Missing rate limiting")
        b = _finding(description="CSS alignment issue in header", vendor="grok")
        score, _ = match_score(a, b)
        assert score < 0.3


class TestMatchScoreSnippet:
    """add-deterministic-review-preprocessing: a shared existing_code
    snippet outranks vendor line arithmetic — see design D3."""

    def test_equal_snippets_match_despite_drifted_lines(self) -> None:
        a = _finding(
            file_path="src/foo.py", line_start=10, line_end=10,
            existing_code="used_variable = compute()",
        )
        b = _finding(
            file_path="src/foo.py", line_start=42, line_end=42, vendor="grok",
            existing_code="used_variable = compute()",
        )
        score, basis = match_score(a, b)
        assert score >= 0.9
        assert basis == "snippet"

    def test_equal_snippets_match_with_no_line_numbers_at_all(self) -> None:
        a = _finding(file_path="src/foo.py", existing_code="x = 1\ny = 2")
        b = _finding(file_path="src/foo.py", vendor="grok", existing_code="x = 1\ny = 2")
        score, basis = match_score(a, b)
        assert score >= 0.9
        assert basis == "snippet"

    def test_snippet_normalizes_whitespace_and_diff_markers(self) -> None:
        a = _finding(file_path="src/foo.py", existing_code="  +used_variable = compute()  ")
        b = _finding(
            file_path="src/foo.py", vendor="grok",
            existing_code="used_variable = compute()",
        )
        score, basis = match_score(a, b)
        assert score >= 0.9
        assert basis == "snippet"

    def test_overlapping_lines_still_wins_over_snippet_band(self) -> None:
        """location+type (0.95) stays the top band when it applies; the
        snippet band (0.9) only fires when location does not match."""
        a = _finding(
            file_path="src/foo.py", line_start=10, line_end=10,
            existing_code="used_variable = compute()",
        )
        b = _finding(
            file_path="src/foo.py", line_start=10, line_end=10, vendor="grok",
            existing_code="used_variable = compute()",
        )
        score, basis = match_score(a, b)
        assert score == 0.95
        assert basis == "location+type"

    def test_different_files_do_not_match_on_snippet_alone(self) -> None:
        a = _finding(file_path="src/foo.py", existing_code="shared_boilerplate = True")
        b = _finding(
            file_path="src/bar.py", vendor="grok",
            existing_code="shared_boilerplate = True",
        )
        score, basis = match_score(a, b)
        assert basis != "snippet"

    def test_missing_snippet_on_one_side_falls_through(self) -> None:
        a = _finding(file_path="src/foo.py", existing_code="x = 1")
        b = _finding(file_path="src/foo.py", vendor="grok", existing_code=None)
        score, basis = match_score(a, b)
        assert basis != "snippet"

    def test_axis_gate_still_applies_to_snippet_matches(self) -> None:
        a = _finding(
            file_path="src/foo.py", existing_code="x = 1", axis="correctness",
        )
        b = _finding(
            file_path="src/foo.py", vendor="grok", existing_code="x = 1",
            axis="security",
        )
        score, _ = match_score(a, b)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Cross-vendor format skew (regression: 2026-08-04 merge session)
#
# Four consensus runs over 43 findings produced confirmed_count=0 /
# match_score=0.0 even though codex and grok plainly agreed. Root causes:
# byte-equality on file_path (vendors emit relative / absolute / a-prefixed
# paths), a hard equality gate on free-form type labels, and a
# type+description score band that required Jaccard 1.0 to clear the 0.6
# threshold. These tests pin the repaired behavior.
# ---------------------------------------------------------------------------

class TestPathsMatch:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("skills/foo/bar.py", "skills/foo/bar.py"),
            ("./skills/foo/bar.py", "skills/foo/bar.py"),
            ("a/skills/foo/bar.py", "b/skills/foo/bar.py"),
            ("/Users/dev/repo/skills/foo/bar.py", "skills/foo/bar.py"),
            ("foo/bar.py", "repo/skills/foo/bar.py"),
        ],
    )
    def test_equivalent_formats_match(self, a: str, b: str) -> None:
        assert _paths_match(a, b)
        assert _paths_match(b, a)

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("skills/foo/bar.py", "skills/foo/baz.py"),
            ("skills/foo/bar.py", "other/foobar.py"),
            (None, "skills/foo/bar.py"),
            ("skills/foo/bar.py", None),
            (None, None),
        ],
    )
    def test_different_files_do_not_match(self, a: str | None, b: str | None) -> None:
        assert not _paths_match(a, b)

    def test_suffix_requires_component_boundary(self) -> None:
        # "bar.py" must not match "foobar.py"
        assert not _paths_match("bar.py", "skills/foobar.py")


class TestTypeCompatibility:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("correctness", "bug"),
            ("Correctness", "correctness"),
            ("security", "vulnerability"),
            ("performance", "perf"),
            ("architecture", "design"),
        ],
    )
    def test_aliases_compatible(self, a: str, b: str) -> None:
        assert _types_compatible(a, b)

    def test_distinct_types_incompatible(self) -> None:
        assert not _types_compatible("security", "performance")


class TestCrossVendorFormatSkew:
    def test_absolute_vs_relative_path_location_match(self) -> None:
        a = _finding(
            type="correctness",
            file_path="skills/implement-feature/SKILL.md",
            line_start=268, line_end=272,
            description="Dispatch grant appears after the primary dispatch sites",
        )
        b = _finding(
            type="bug", vendor="grok",
            file_path="/Users/dev/repo/skills/implement-feature/SKILL.md",
            line_start=268,
            description="Authorization grant placed below the dispatch call it must cover",
        )
        score, basis = match_score(a, b)
        assert score >= 0.6
        assert "location" in basis

    def test_diff_prefixed_path_matches(self) -> None:
        a = _finding(
            file_path="a/skills/roadmap-runtime/scripts/checkpoint.py",
            line_start=40, line_end=44,
        )
        b = _finding(
            vendor="grok",
            file_path="skills/roadmap-runtime/scripts/checkpoint.py",
            line_start=42,
        )
        score, _ = match_score(a, b)
        assert score >= 0.9

    def test_same_location_different_type_labels_still_matches(self) -> None:
        a = _finding(type="security", file_path="src/auth.py", line_start=10)
        b = _finding(type="architecture", vendor="grok",
                     file_path="src/auth.py", line_start=10)
        score, basis = match_score(a, b)
        assert score >= 0.6
        assert basis == "location"

    def test_paraphrased_description_without_file_reaches_threshold(self) -> None:
        # Previously score = min(0.3 + sim*0.3, 0.7) needed sim == 1.0 to
        # reach the 0.6 threshold — unreachable for paraphrased findings.
        a = _finding(description="SQL injection risk in query builder module")
        b = _finding(
            description="SQL injection vulnerability in the query builder",
            vendor="grok",
        )
        score, basis = match_score(a, b)
        assert score >= 0.6
        assert basis == "type+description"

    def test_end_to_end_mixed_formats_confirm(self) -> None:
        """Vendors agreeing through format skew must produce confirmed findings."""
        synth = ConsensusSynthesizer()
        result = synth.synthesize(
            review_type="pr",
            target="PR #281",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(
                        id=1, type="correctness", disposition="fix",
                        file_path="skills/implement-feature/SKILL.md",
                        line_start=268, line_end=272,
                        description="Grant sits after the dispatch sites it authorizes",
                    ),
                    _finding(
                        id=2, type="style", disposition="accept",
                        description="Codex-only nit about naming",
                    ),
                ]),
                VendorResult(vendor="grok", findings=[
                    _finding(
                        id=1, type="bug", disposition="fix", vendor="grok",
                        file_path="a/skills/implement-feature/SKILL.md",
                        line_start=268,
                        description="Authorization grant placed below dispatch call",
                    ),
                ]),
            ],
        )
        assert result.confirmed_count == 1
        assert result.blocking_count == 1
        confirmed = [cf for cf in result.consensus_findings if cf.status == "confirmed"]
        assert confirmed[0].match_score >= 0.6


# ---------------------------------------------------------------------------
# Consensus synthesis
# ---------------------------------------------------------------------------

class TestCoverageEligibility:
    def test_full_coverage_vendor_always_counts(self) -> None:
        vendors = [
            VendorResult(vendor="codex", findings=[]),
            VendorResult(vendor="grok", findings=[], reviewed_files=None),
        ]
        assert _eligible_vendor_count("src/api.py", vendors) == 2

    def test_partial_vendor_excluded_for_unreviewed_file(self) -> None:
        vendors = [
            VendorResult(vendor="codex", findings=[]),
            VendorResult(
                vendor="grok", findings=[],
                reviewed_files=frozenset({"src/a.py", "src/b.py"}),
            ),
        ]
        assert _eligible_vendor_count("src/unreviewed.py", vendors) == 1

    def test_partial_vendor_counted_for_reviewed_file(self) -> None:
        vendors = [
            VendorResult(vendor="codex", findings=[]),
            VendorResult(
                vendor="grok", findings=[],
                reviewed_files=frozenset({"src/a.py"}),
            ),
        ]
        assert _eligible_vendor_count("src/a.py", vendors) == 2

    def test_no_file_path_cannot_be_gated(self) -> None:
        vendors = [
            VendorResult(vendor="codex", findings=[]),
            VendorResult(vendor="grok", findings=[], reviewed_files=frozenset({"src/a.py"})),
        ]
        assert _eligible_vendor_count(None, vendors) == 2

    def test_reviewed_files_from_coverage_below_threshold(self) -> None:
        coverage = {"reviewed": ["src/a.py"], "skipped": [], "rate": 0.4}
        result = _reviewed_files_from_coverage(coverage, threshold=0.8)
        assert result == frozenset({"src/a.py"})

    def test_reviewed_files_from_coverage_at_or_above_threshold_is_full(self) -> None:
        coverage = {"reviewed": ["src/a.py"], "skipped": [], "rate": 0.8}
        assert _reviewed_files_from_coverage(coverage, threshold=0.8) is None

    def test_reviewed_files_from_coverage_missing_block_is_full(self) -> None:
        assert _reviewed_files_from_coverage(None, threshold=0.8) is None

    def test_reviewed_files_from_coverage_missing_rate_is_full(self) -> None:
        coverage = {"reviewed": ["src/a.py"], "skipped": []}
        assert _reviewed_files_from_coverage(coverage, threshold=0.8) is None

    def test_coverage_quorum_threshold_has_a_sane_default(self) -> None:
        assert 0.0 < _coverage_quorum_threshold() <= 1.0

    def test_eligible_vendors_flows_into_consensus_finding_and_to_dict(self) -> None:
        synth = ConsensusSynthesizer(quorum=2)
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[
                    _finding(id=1, file_path="src/unreviewed.py", description="Lone finding on a file grok never reviewed"),
                ]),
                VendorResult(
                    vendor="grok", findings=[],
                    reviewed_files=frozenset({"src/other.py"}),
                ),
            ],
        )
        cf = result.consensus_findings[0]
        assert cf.status == "unconfirmed"
        assert cf.eligible_vendors == 1
        d = synth.to_dict(result)
        assert d["consensus_findings"][0]["eligible_vendors"] == 1


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
                VendorResult(vendor="grok", findings=[
                    _finding(id=1, file_path="src/api.py", line_start=42, line_end=50, description="Auth check missing on user endpoint", disposition="fix", vendor="grok"),
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
                VendorResult(vendor="grok", findings=[
                    _finding(id=1, description="Completely different concern about widgets", vendor="grok"),
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
                VendorResult(vendor="grok", findings=[
                    _finding(id=1, file_path="src/handler.py", line_start=10, description="Error handling missing for edge case scenario", disposition="accept", vendor="grok"),
                ]),
            ],
        )
        assert result.disagreement_count == 1
        cf = result.consensus_findings[0]
        assert cf.status == "disagreement"
        assert cf.recommended_disposition == "escalate"
        assert cf.vendor_dispositions == {"codex": "fix", "grok": "accept"}

    def test_quorum_met(self) -> None:
        """Quorum met when enough vendors respond."""
        synth = ConsensusSynthesizer(quorum=2)
        result = synth.synthesize(
            review_type="plan",
            target="test-feature",
            vendor_results=[
                VendorResult(vendor="codex", findings=[]),
                VendorResult(vendor="grok", findings=[]),
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
                VendorResult(vendor="grok", findings=[], success=False, error="429 capacity"),
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
                VendorResult(vendor="grok", findings=[]),
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
                VendorResult(vendor="grok", findings=[
                    _finding(id=1, criticality="high", description="Missing input validation for API endpoint", vendor="grok", file_path="src/api.py", line_start=10),
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
                VendorResult(vendor="grok", findings=[
                    _finding(id=1, description="Authentication security vulnerability", disposition="fix", vendor="grok", file_path="src/auth.py", line_start=5),
                    _finding(id=2, description="Database query performance issue", disposition="accept", vendor="grok", type="performance", file_path="src/db.py", line_start=20),
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

    @pytest.mark.parametrize(
        ("line_range", "expected_start", "expected_end"),
        [
            ({"start": 10, "end": 20}, 10, 20),
            ("10-20", 10, 20),
            (None, None, None),
        ],
    )
    def test_finding_from_dict_accepts_vendor_line_range_shapes(
        self,
        line_range: object,
        expected_start: int | None,
        expected_end: int | None,
    ) -> None:
        """Finding.from_dict accepts line_range shapes emitted by vendors."""
        data = {
            "id": 3,
            "type": "security",
            "criticality": "high",
            "description": "XSS vulnerability",
            "disposition": "fix",
            "file_path": "src/views.py",
            "line_range": line_range,
        }

        f = Finding.from_dict(data, vendor="codex")

        assert f.line_start == expected_start
        assert f.line_end == expected_end
