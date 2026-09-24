"""Tests for the judged cross-vendor matching path in consensus_synthesizer.

Covers spec scenarios:
- parallel-infrastructure (Judged Cross-Vendor Finding Matching): Fast-path
  pairs never call decide(), Same-file same-axis pairs are judged in one
  batched call, A judged match never raises blocking_count, Decision helper
  unavailable falls back to Jaccard, MATCH_THRESHOLD has no literal in the
  scoring path

Design decisions: D1 (judged path beside match_score, not inside it), D2
(judged eligibility and batching shape), D3 (Jaccard fallback), D4
(evidence_class override), D5 (MATCH_THRESHOLD from config)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import system_one_decisions
from system_one_decisions.testing import stub_decide

from consensus_synthesizer import (
    DETERMINISTIC,
    JUDGMENT,
    ConsensusSynthesizer,
    Finding,
    VendorResult,
    _judge_pairs,
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
    evidence_class: str = DETERMINISTIC,
) -> Finding:
    return Finding(
        id=id, type=type, criticality=criticality,
        description=description, disposition=disposition,
        vendor=vendor, file_path=file_path,
        line_start=line_start, line_end=line_end,
        existing_code=existing_code, axis=axis,
        evidence_class=evidence_class,
    )


def _noul_answers(**pair_scores: float) -> dict[str, object]:
    return {key: SimpleNamespace(noul=value) for key, value in pair_scores.items()}


def _spy_decide(monkeypatch, *, returns: dict[str, object] | None) -> MagicMock:
    """Like stub_decide, but a MagicMock so call-count can be asserted.

    Patches the attribute on the real `system_one_decisions` module object
    (not a pre-bound name) -- the same requirement `stub_decide` documents.
    """
    mock = MagicMock(return_value=returns)
    monkeypatch.setattr(system_one_decisions, "decide", mock)
    return mock


# ---------------------------------------------------------------------------
# _judge_pairs
# ---------------------------------------------------------------------------


class TestJudgePairs:
    def test_empty_pairs_makes_no_call(self, monkeypatch) -> None:
        decide = _spy_decide(monkeypatch, returns=None)
        result = _judge_pairs("foo.py", [])
        assert result == {}
        decide.assert_not_called()

    def test_one_call_for_n_pairs(self, monkeypatch) -> None:
        a1, b1 = _finding(id=1, vendor="antigravity"), _finding(id=1, vendor="pi")
        a2, b2 = _finding(id=2, vendor="antigravity"), _finding(id=2, vendor="pi")
        decide = _spy_decide(monkeypatch, returns=_noul_answers(pair_0=0.9, pair_1=0.2))

        result = _judge_pairs("foo.py", [(a1, b1), (a2, b2)])

        assert result == {0: 0.9, 1: 0.2}
        decide.assert_called_once()

    def test_unavailable_decide_returns_empty(self, monkeypatch) -> None:
        stub_decide(monkeypatch, returns=None)
        a, b = _finding(id=1, vendor="antigravity"), _finding(id=1, vendor="pi")

        assert _judge_pairs("foo.py", [(a, b)]) == {}

    def test_missing_module_returns_empty(self, monkeypatch) -> None:
        import consensus_synthesizer as module

        monkeypatch.setattr(module, "system_one_decisions", None)
        a, b = _finding(id=1, vendor="antigravity"), _finding(id=1, vendor="pi")

        assert _judge_pairs("foo.py", [(a, b)]) == {}


# ---------------------------------------------------------------------------
# ConsensusSynthesizer._match_all / synthesize integration
# ---------------------------------------------------------------------------


class TestJudgedMatchAll:
    def test_fast_path_pair_calls_decide_zero_times(self, monkeypatch) -> None:
        """Location+type fast-path match issues no decide() call at all."""
        decide = _spy_decide(monkeypatch, returns=None)

        a = _finding(
            id=1, vendor="antigravity", file_path="foo.py",
            line_start=10, line_end=15, description="Off-by-one in loop bound",
        )
        b = _finding(
            id=1, vendor="pi", file_path="foo.py",
            line_start=12, line_end=12, description="Loop bound is off by one",
        )
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target",
            [VendorResult(vendor="antigravity", findings=[a]),
             VendorResult(vendor="pi", findings=[b])],
        )
        assert report.confirmed_count == 1
        decide.assert_not_called()

    def test_same_file_axis_pairs_judged_in_one_call(self, monkeypatch) -> None:
        """Two paraphrased, no-location findings on the same file/axis get
        one decide() call, and a confident answer produces a judged match."""
        decide = _spy_decide(monkeypatch, returns=_noul_answers(pair_0=0.9))

        a = _finding(
            id=1, vendor="antigravity", file_path="foo.py",
            description="Critical: contract mismatch between footer format and disclosure line",
        )
        b = _finding(
            id=1, vendor="pi", file_path="foo.py",
            description="Multi-language disclosure footer format unspecified causing mismatch",
        )
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target",
            [VendorResult(vendor="antigravity", findings=[a]),
             VendorResult(vendor="pi", findings=[b])],
        )
        decide.assert_called_once()
        cf = report.consensus_findings[0]
        assert cf.matched_findings
        assert cf.evidence_class == JUDGMENT

    def test_judged_match_never_raises_blocking_count(self, monkeypatch) -> None:
        """Two deterministic findings matched only via judgment stay
        non-blocking: evidence_class is judgment, blocking_count excludes it."""
        _spy_decide(monkeypatch, returns=_noul_answers(pair_0=0.95))

        a = _finding(
            id=1, vendor="antigravity", file_path="foo.py",
            disposition="fix", evidence_class=DETERMINISTIC,
            description="Alpha bravo charlie delta echo",
        )
        b = _finding(
            id=1, vendor="pi", file_path="foo.py",
            disposition="fix", evidence_class=DETERMINISTIC,
            description="Foxtrot golf hotel india juliet",
        )
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target",
            [VendorResult(vendor="antigravity", findings=[a]),
             VendorResult(vendor="pi", findings=[b])],
        )
        cf = report.consensus_findings[0]
        assert cf.status == "confirmed"
        assert cf.evidence_class == JUDGMENT
        assert report.blocking_count == 0
        assert report.advisory_count == 1

    def test_multiple_primaries_on_one_file_share_a_single_call(self, monkeypatch) -> None:
        """Two primaries, each needing judgment against a same-file, same-
        axis candidate, still cost exactly one decide() call for the file
        -- not one call per primary (Codex review, PR #590 P2)."""
        decide = _spy_decide(
            monkeypatch, returns=_noul_answers(pair_0=0.9, pair_1=0.85),
        )

        # Different axes on the two pairs so only (a1, b1) and (a2, b2) are
        # judgment-eligible -- cross-pairs (a1, b2) / (a2, b1) are filtered
        # out by the axis gate before reaching _judge_pairs, giving exactly
        # the 2 pairs this test's stub answers for.
        a1 = _finding(
            id=1, vendor="antigravity", file_path="foo.py", axis="correctness",
            description="Alpha issue one",
        )
        b1 = _finding(
            id=1, vendor="pi", file_path="foo.py", axis="correctness",
            description="Bravo issue one paraphrase",
        )
        a2 = _finding(
            id=2, vendor="antigravity", file_path="foo.py", axis="security",
            description="Charlie issue two",
        )
        b2 = _finding(
            id=2, vendor="pi", file_path="foo.py", axis="security",
            description="Delta issue two paraphrase",
        )

        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target",
            [VendorResult(vendor="antigravity", findings=[a1, a2]),
             VendorResult(vendor="pi", findings=[b1, b2])],
        )
        decide.assert_called_once()
        assert report.confirmed_count == 2
        assert all(cf.evidence_class == JUDGMENT for cf in report.consensus_findings)

    def test_evidence_class_is_order_independent_across_three_vendors(self, monkeypatch) -> None:
        """A primary matched via judgment against one vendor and via a
        fast path against another must still carry evidence_class
        "judgment" -- regardless of which vendor's match is recorded last
        (Codex review, PR #590 P1)."""
        decide = _spy_decide(monkeypatch, returns=_noul_answers(pair_0=0.9))

        judged_peer = _finding(
            id=1, vendor="pi", file_path="foo.py",
            description="Multi-language disclosure footer format unspecified causing mismatch",
            disposition="fix",
        )
        fast_path_peer = _finding(
            id=1, vendor="codex", file_path="foo.py",
            line_start=10, line_end=15, disposition="fix",
            description="Off-by-one in loop bound",
        )
        # A second, unrelated finding on the primary's own file/axis so the
        # fast-path candidate above actually has an overlapping-lines match
        # against the primary too (both must describe the primary's own
        # location for the fast path to fire against it specifically).
        primary_with_location = _finding(
            id=1, vendor="antigravity", file_path="foo.py",
            line_start=10, line_end=15, disposition="fix",
            description="Critical: contract mismatch between footer format and disclosure line",
        )

        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target",
            [VendorResult(vendor="antigravity", findings=[primary_with_location]),
             VendorResult(vendor="pi", findings=[judged_peer]),
             VendorResult(vendor="codex", findings=[fast_path_peer])],
        )
        assert len(report.consensus_findings) == 1
        cf = report.consensus_findings[0]
        assert len(cf.matched_findings) == 2
        assert cf.evidence_class == JUDGMENT
        decide.assert_called_once()

    def test_unavailable_decide_falls_back_to_jaccard(self, monkeypatch) -> None:
        """decide() returning None for same-file/axis pairs falls back to
        the existing Jaccard bands -- unchanged, non-judged behavior."""
        stub_decide(monkeypatch, returns=None)

        a = _finding(
            id=1, vendor="antigravity", file_path="foo.py", type="security",
            description="missing input validation on user endpoint handler",
        )
        b = _finding(
            id=1, vendor="pi", file_path="foo.py", type="security",
            description="missing input validation on user endpoint route",
        )
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target",
            [VendorResult(vendor="antigravity", findings=[a]),
             VendorResult(vendor="pi", findings=[b])],
        )
        cf = report.consensus_findings[0]
        assert cf.matched_findings  # matched via Jaccard, not judgment
        assert cf.evidence_class == DETERMINISTIC


# ---------------------------------------------------------------------------
# Fixture replay (reconstructed -- see design.md's grounding note)
# ---------------------------------------------------------------------------


class TestPr484FixtureReplay:
    """Reconstructs the two real per-vendor findings behind the
    footer/percent-format defect from
    add-orchestrator-adjudication-review-gate/fixtures/pr484-consensus.json
    (antigravity finding id 1, pi finding id 14). The consensus-report
    schema that fixture is written in keeps neither finding's real
    file_path/line_range, so both are reconstructed with the one file both
    descriptions name (build_atlas.py's --tree footer/disclosure output) --
    an honest reconstruction, not a literal byte-for-byte replay.
    """

    def test_footer_percent_pair_matches_via_judgment(self, monkeypatch) -> None:
        decide = _spy_decide(monkeypatch, returns=_noul_answers(pair_0=0.85))

        antigravity_finding = _finding(
            id=1, vendor="antigravity", file_path="build_atlas.py",
            type="contract_mismatch", criticality="high", axis="compatibility",
            description=(
                "Critical: Spec contract mismatch between build_atlas.py --tree "
                "footer format and explain-code grounding disclosure line."
            ),
        )
        pi_finding = _finding(
            id=14, vendor="pi", file_path="build_atlas.py",
            type="spec_gap", criticality="medium", axis="compatibility",
            description=(
                "Multi-language disclosure footer format unspecified: the spec "
                "says footer has 'per language present' but doesn't define the "
                "exact format. Design shows 'python 14% / sql 37% covered' with "
                "slashes but spec uses ellipsis. Format mismatch will cause test "
                "failures."
            ),
        )
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "pr484",
            [VendorResult(vendor="antigravity", findings=[antigravity_finding]),
             VendorResult(vendor="pi", findings=[pi_finding])],
        )
        decide.assert_called_once()
        cf = report.consensus_findings[0]
        assert cf.status in ("confirmed", "disagreement")
        assert cf.matched_findings
        assert cf.evidence_class == JUDGMENT
