"""Tests for consensus_synthesizer — multi-vendor finding matching and synthesis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import consensus_synthesizer as consensus_module

from consensus_synthesizer import (
    ConsensusSynthesizer,
    ConsensusInputError,
    Finding,
    VendorResult as VendorResultModel,
    _jaccard,
    _paths_match,
    _tokenize,
    _types_compatible,
    match_score,
    validate_consensus_payload,
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
    affected_symbol: str | None = None,
    requirement_id: str | None = None,
) -> Finding:
    return Finding(
        id=id, type=type, criticality=criticality,
        description=description, disposition=disposition,
        vendor=vendor, file_path=file_path,
        line_start=line_start, line_end=line_end,
        affected_symbol=affected_symbol, requirement_id=requirement_id,
    )


def _logical_result(vendor: str, *, success: bool) -> dict[str, object]:
    return {
        "logical_request_id": f"test-{vendor}",
        "requested_vendor": vendor,
        "requested_routing": {
            "archetype": "reviewer",
            "tier": "premium",
            "phase": "IMPL_REVIEW",
            "source": "test",
            "fallback_reason": None,
        },
        "deadline_at": "2026-08-05T00:01:00+00:00",
        "budget": {"corrective_max": 1, "replacement_max": 1, "fallback_models": []},
        "attempts": [{
            "attempt_index": 1,
            "vendor": vendor,
            "transport": "cli",
            "reason": "initial",
            "terminal": True,
            "success": success,
            "elapsed_seconds": 0.1,
            "parser_stage": "schema" if success else None,
            "validation_status": "schema_valid" if success else "not_reached",
            "error_class": None if success else "auth",
            "error_detail": None if success else "unavailable",
            "stdout_excerpt": None,
            "stderr_excerpt": None,
            "diagnostics_truncated": False,
            "resolved_execution": {
                "model": "test-model",
                "requested_thinking": None,
                "applied_thinking": None,
                "thinking_translation": "not_requested",
                "fallback_reason": None,
            },
        }],
        "terminal_outcome": "success" if success else "auth",
        "terminal_vendor": vendor,
        "quorum_eligible": success,
    }


def VendorResult(*args: object, **kwargs: object) -> VendorResultModel:
    vendor = str(kwargs.get("vendor", args[0] if args else "test"))
    success = bool(kwargs.get("success", True))
    kwargs.setdefault("logical_result", _logical_result(vendor, success=success))
    return VendorResultModel(*args, **kwargs)


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
    def test_normalized_path_and_nearby_location_match(self) -> None:
        a = _finding(file_path="./src/../src/api.py", line_start=10, line_end=12)
        b = _finding(file_path="src\\api.py", line_start=25, vendor="grok")
        score, basis = match_score(a, b)
        assert score >= 0.8
        assert basis == "nearby-location"

    def test_symbol_and_requirement_identity_match_paraphrases(self) -> None:
        symbol_a = _finding(description="writer accepts bad data", affected_symbol="Manifest.write")
        symbol_b = _finding(description="unrelated wording", affected_symbol="manifest.write", vendor="grok")
        assert match_score(symbol_a, symbol_b)[1] == "symbol"
        req_a = _finding(description="first phrasing", requirement_id="R-12")
        req_b = _finding(description="second phrasing", requirement_id="r-12", vendor="grok")
        assert match_score(req_a, req_b)[1] == "requirement"

    def test_owned_synonyms_match_differently_worded_defect(self) -> None:
        a = _finding(description="contract omits blocker validation and persisted duplicate votes")
        b = _finding(description="schema missing blocking validate and writes repeated votes", vendor="grok")
        assert match_score(a, b)[0] >= 0.6
    def test_different_types_without_structural_evidence_do_not_match(self) -> None:
        a = _finding(type="security")
        b = _finding(type="performance")
        score, _ = match_score(a, b)
        assert score == 0.0

    def test_exact_location_can_match_different_type_families(self) -> None:
        a = _finding(type="security", file_path="src/api.py", line_start=42)
        b = _finding(type="correctness", file_path="src/api.py", line_start=42, vendor="grok")
        score, basis = match_score(a, b)
        assert score >= 0.8
        assert basis == "location+cross-family"

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
        assert basis == "location+cross-family"

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
            review_type="implementation",
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

class TestConsensusSynthesizer:
    def test_success_only_vendor_result_is_audit_only(self) -> None:
        report = ConsensusSynthesizer(quorum=1).synthesize(
            "implementation",
            "target",
            [VendorResultModel(vendor="legacy", findings=[_finding(vendor="legacy")])],
        )

        assert report.quorum_received == 0
        assert report.consensus_findings == []

    def test_duplicate_wrappers_for_one_terminal_vendor_count_once(self) -> None:
        first_chain = _logical_result("codex", success=True)
        first_chain["logical_request_id"] = "slot-alpha"
        second_chain = _logical_result("codex", success=True)
        second_chain["logical_request_id"] = "slot-beta"
        finding = _finding(vendor="codex")

        report = ConsensusSynthesizer(quorum=2).synthesize(
            "implementation",
            "target",
            [
                VendorResultModel(vendor="alpha", findings=[finding], logical_result=first_chain),
                VendorResultModel(vendor="beta", findings=[finding], logical_result=second_chain),
            ],
        )

        assert report.quorum_received == 1
        assert report.quorum_met is False
        assert [reviewer["vendor"] for reviewer in report.reviewers if reviewer["success"]] == ["codex"]

    def test_duplicate_logical_request_ids_are_rejected(self) -> None:
        chain = _logical_result("codex", success=True)

        with pytest.raises(ConsensusInputError, match="duplicate logical review request"):
            ConsensusSynthesizer().synthesize(
                "implementation",
                "target",
                [
                    VendorResultModel(
                        vendor="alpha",
                        findings=[_finding(vendor="codex")],
                        logical_result=chain,
                    ),
                    VendorResultModel(
                        vendor="beta",
                        findings=[_finding(vendor="codex")],
                        logical_result=chain,
                    ),
                ],
            )

    def test_requested_quorum_uses_logical_slots_not_wrapper_names(self) -> None:
        codex = _logical_result("codex", success=True)
        codex["logical_request_id"] = "slot-codex"
        grok = _logical_result("grok", success=True)
        grok["logical_request_id"] = "slot-grok"

        report = ConsensusSynthesizer(quorum=2).synthesize(
            "implementation",
            "target",
            [
                VendorResultModel(vendor="same-wrapper", findings=[], logical_result=codex),
                VendorResultModel(vendor="same-wrapper", findings=[], logical_result=grok),
            ],
        )

        assert report.quorum_requested == 2
        assert report.quorum_received == 2
        assert report.quorum_met is True

    def test_manifest_loader_indexes_only_eligible_terminal_vendors(self, tmp_path: Path) -> None:
        eligible = _logical_result("codex", success=True)
        ineligible = _logical_result("grok", success=False)
        manifest = tmp_path / "review-manifest.json"
        manifest.write_text(
            json.dumps({"dispatches": [ineligible, eligible]}),
            encoding="utf-8",
        )

        indexed = consensus_module._load_manifest_logical_results(manifest)

        assert indexed == {"codex": [eligible]}

    def test_cli_counts_manifest_slot_with_zero_findings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        eligible = _logical_result("codex", success=True)
        (tmp_path / "review-manifest.json").write_text(
            json.dumps({"dispatches": [eligible]}),
            encoding="utf-8",
        )
        output = tmp_path / "consensus.json"
        monkeypatch.setattr(sys, "argv", [
            "consensus_synthesizer.py",
            "--review-type", "implementation",
            "--target", "target",
            "--input-dir", str(tmp_path),
            "--output", str(output),
            "--quorum", "1",
        ])

        assert consensus_module.main() == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["quorum_received"] == 1
        assert payload["quorum_met"] is True
        assert payload["summary"]["total_unique_findings"] == 0

    def test_matching_total_work_is_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(consensus_module, "MAX_MATCH_COMPARISONS", 1)
        findings = [
            _finding(id=index, vendor=f"vendor-{index}", description="shared token distinct concern")
            for index in range(3)
        ]
        with pytest.raises(ValueError, match="bounded work budget"):
            ConsensusSynthesizer()._match_all(findings)

    def test_full_consensus_contract_rejects_false_zero_and_non_boolean_policy(self) -> None:
        synth = ConsensusSynthesizer(quorum=1)
        report = synth.to_dict(synth.synthesize(
            "implementation", "target", [VendorResult(vendor="claude_code", findings=[
                _finding(type="behavioral_failure", vendor="claude_code"),
            ])],
        ))
        validate_consensus_payload(report)
        report["consensus_findings"][0]["policy"]["effective_blocking"] = 0
        with pytest.raises(ValueError, match="invalid consensus report"):
            validate_consensus_payload(report)

    def test_full_consensus_contract_requires_revision_two_fields(self) -> None:
        synth = ConsensusSynthesizer(quorum=1)
        report = synth.to_dict(synth.synthesize(
            "plan", "target", [VendorResult(vendor="codex", findings=[_finding()])],
        ))
        del report["consensus_findings"][0]["source_findings"]
        with pytest.raises(ValueError, match="invalid consensus report"):
            validate_consensus_payload(report)
    def test_fingerprint_is_stable_across_vendor_and_local_id(self) -> None:
        a = _finding(id=1, vendor="codex", file_path="src/api.py", line_start=7)
        b = _finding(id=99, vendor="grok", file_path="src/api.py", line_start=7)
        assert ConsensusSynthesizer._concern_fingerprint(a) == ConsensusSynthesizer._concern_fingerprint(b)

    def test_ledger_applies_evidence_backed_false_positive(self) -> None:
        synth = ConsensusSynthesizer()
        initial = synth.synthesize("plan", "test", [
            VendorResult(vendor="codex", findings=[_finding()]),
        ])
        finding = initial.consensus_findings[0]
        ledger = [{
            "group_id": finding.group_id,
            "concern_fingerprints": finding.concern_fingerprints,
            "adjudication": {
                "status": "false_positive", "rationale": "out of scope",
                "evidence": ["scope-proof.json"],
            },
            "recorded_at": "2026-08-01T00:00:00Z",
        }]

        report = synth.synthesize(
            "plan", "test", [VendorResult(vendor="codex", findings=[_finding()])],
            adjudication_ledger=ledger,
        )

        assert report.consensus_findings[0].adjudication["status"] == "false_positive"
        assert report.consensus_findings[0].effective_blocking is False
        assert synth.to_dict(report)["applied_adjudications"] == ledger

    def test_stale_or_untrusted_ledger_entries_fail_closed(self) -> None:
        synth = ConsensusSynthesizer()
        report = synth.synthesize("plan", "test", [
            VendorResult(vendor="codex", findings=[_finding()]),
        ])
        finding = report.consensus_findings[0]
        stale = [{
            "group_id": finding.group_id,
            "concern_fingerprints": ["different-fingerprint"],
            "adjudication": {"status": "unreviewed"},
            "recorded_at": "2026-08-01T00:00:00Z",
        }]
        with pytest.raises(ValueError, match="stale or malformed"):
            synth.synthesize(
                "plan", "test", [VendorResult(vendor="codex", findings=[_finding()])],
                adjudication_ledger=stale,
            )

        fabricated = [{
            "group_id": finding.group_id,
            "concern_fingerprints": finding.concern_fingerprints,
            "adjudication": {
                "status": "accepted_risk", "rationale": "looks fine",
                "authorization": {
                    "actor_id": "someone", "actor_type": "human",
                    "mechanism": "github_approval", "authorized_at": "2026-08-01T00:00:00Z",
                    "approval_ref": "PR-1",
                },
            },
            "recorded_at": "2026-08-01T00:00:00Z",
        }]
        with pytest.raises(ValueError, match="evidence or authorization"):
            synth.synthesize(
                "plan", "test", [VendorResult(vendor="codex", findings=[_finding()])],
                adjudication_ledger=fabricated,
            )

    def test_description_bridge_does_not_merge_non_clique(self) -> None:
        synth = ConsensusSynthesizer(match_threshold=0.45)
        first = _finding(id=1, vendor="alpha", description="alpha beta gamma delta")
        bridge = _finding(id=2, vendor="beta", description="alpha beta gamma epsilon")
        third = _finding(id=3, vendor="gamma", description="beta gamma epsilon zeta")

        matches = synth._match_all([first, bridge, third])

        assert sorted(len(match.matched) + 1 for match in matches) == [1, 2]

    def test_rejects_vendor_result_over_finding_limit(self) -> None:
        synth = ConsensusSynthesizer()
        finding = _finding()
        with pytest.raises(ValueError, match="finding limit"):
            synth.synthesize("plan", "test", [
                VendorResult(vendor="codex", findings=[finding] * 501),
            ])

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

    def test_unmatched_actionable_finding_is_not_rewritten_to_accept(self) -> None:
        result = ConsensusSynthesizer().synthesize(
            review_type="plan", target="test-feature",
            vendor_results=[VendorResult(vendor="codex", findings=[
                _finding(description="Only codex found this issue", disposition="fix"),
            ])],
        )
        finding = result.consensus_findings[0]
        assert finding.recommended_disposition == "fix"
        assert finding.effective_blocking is True

    def test_groups_are_order_invariant(self) -> None:
        first = _finding(id=1, vendor="codex", file_path="src/a.py", line_start=4)
        second = _finding(id=8, vendor="grok", file_path="src/a.py", line_start=4)
        synth = ConsensusSynthesizer()
        forward = synth.synthesize("plan", "test", [
            VendorResult(vendor="codex", findings=[first]),
            VendorResult(vendor="grok", findings=[second]),
        ])
        reverse = synth.synthesize("plan", "test", [
            VendorResult(vendor="grok", findings=[second]),
            VendorResult(vendor="codex", findings=[first]),
        ])
        assert forward.consensus_findings[0].group_id == reverse.consensus_findings[0].group_id

    def test_grouping_is_stable_when_vendor_identities_are_permuted(self) -> None:
        concerns = [
            _finding(id=1, description="alpha beta gamma delta"),
            _finding(id=2, description="alpha beta gamma epsilon"),
            _finding(id=3, description="beta gamma epsilon zeta"),
        ]

        def synthesize(vendors: tuple[str, str, str]) -> list[tuple[str, tuple[str, ...]]]:
            results = [
                VendorResult(
                    vendor=vendor,
                    findings=[Finding(**{**concern.__dict__, "vendor": vendor})],
                )
                for vendor, concern in zip(vendors, concerns, strict=True)
            ]
            report = ConsensusSynthesizer(match_threshold=0.45).synthesize(
                "implementation", "target", results,
            )
            return sorted(
                (finding.group_id, tuple(finding.concern_fingerprints))
                for finding in report.consensus_findings
            )

        assert synthesize(("alpha", "beta", "gamma")) == synthesize(("gamma", "alpha", "beta"))

    def test_fingerprint_is_stable_across_absolute_and_relative_paths(self) -> None:
        relative = _finding(file_path="skills/example/check.py", line_start=9)
        absolute = _finding(file_path="/tmp/repo/skills/example/check.py", line_start=9)

        assert ConsensusSynthesizer._concern_fingerprint(relative) == ConsensusSynthesizer._concern_fingerprint(absolute)

    def test_duplicate_adjudication_groups_are_rejected_before_mutation(self) -> None:
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target", [VendorResult(vendor="codex", findings=[_finding()])],
        )
        finding = report.consensus_findings[0]
        first = {
            "group_id": finding.group_id,
            "concern_fingerprints": finding.concern_fingerprints,
            "adjudication": {
                "status": "false_positive",
                "rationale": "verified out of scope",
                "evidence": ["scope-proof.json"],
            },
            "recorded_at": "2026-08-05T00:00:00Z",
        }
        second = {
            **first,
            "adjudication": {
                "status": "fixed",
                "rationale": "covered by regression",
                "evidence": ["test-output.txt"],
            },
        }

        with pytest.raises(ConsensusInputError, match="duplicate adjudication"):
            synth._apply_adjudications(
                report.consensus_findings,
                adjudication_ledger=[first, second],
                trusted_approval_resolver=None,
            )

        assert finding.adjudication == {"status": "unreviewed"}

    def test_validator_rejects_duplicate_applied_adjudications(self) -> None:
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation",
            "target",
            [VendorResult(vendor="codex", findings=[_finding()])],
        )
        finding = report.consensus_findings[0]
        entry = {
            "group_id": finding.group_id,
            "concern_fingerprints": finding.concern_fingerprints,
            "adjudication": {
                "status": "false_positive",
                "rationale": "verified out of scope",
                "evidence": ["scope-proof.json"],
            },
            "recorded_at": "2026-08-05T00:00:00Z",
        }
        report = synth.synthesize(
            "implementation",
            "target",
            [VendorResult(vendor="codex", findings=[_finding()])],
            adjudication_ledger=[entry],
        )
        payload = synth.to_dict(report)
        payload["applied_adjudications"].append(dict(entry))

        with pytest.raises(ConsensusInputError, match="duplicate or inconsistent"):
            validate_consensus_payload(payload)

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
        assert d["schema_version"] == 2
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
        assert data["schema_version"] == 2

    def test_write_report_preserves_trusted_accepted_risk(self, tmp_path: Path) -> None:
        synth = ConsensusSynthesizer()
        initial = synth.synthesize(
            "implementation",
            "target",
            [VendorResult(vendor="codex", findings=[_finding()])],
        )
        finding = initial.consensus_findings[0]
        ledger = [{
            "group_id": finding.group_id,
            "concern_fingerprints": finding.concern_fingerprints,
            "adjudication": {
                "status": "accepted_risk",
                "rationale": "approved by the repository owner",
                "authorization": {
                    "actor_id": "owner",
                    "actor_type": "human",
                    "mechanism": "github_approval",
                    "authorized_at": "2026-08-05T00:00:00Z",
                    "approval_ref": "PR-123",
                },
            },
            "recorded_at": "2026-08-05T00:00:00Z",
        }]
        def resolver(authorization: dict[str, object]) -> bool:
            return authorization.get("approval_ref") == "PR-123"
        report = synth.synthesize(
            "implementation",
            "target",
            [VendorResult(vendor="codex", findings=[_finding()])],
            adjudication_ledger=ledger,
            trusted_approval_resolver=resolver,
        )

        output = tmp_path / "consensus.json"
        synth.write_report(report, output, trusted_approval_resolver=resolver)

        assert json.loads(output.read_text(encoding="utf-8"))["summary"]["blocking_count"] == 0

    def test_validator_recomputes_policy_and_rejects_false_zero(self) -> None:
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target", [VendorResult(vendor="codex", findings=[_finding()])],
        )
        payload = synth.to_dict(report)
        finding = payload["consensus_findings"][0]
        finding["policy"] = {
            "integration_blocking": False,
            "convergence_blocking": False,
            "effective_blocking": False,
        }
        for key in (
            "integration_blocking_count",
            "convergence_blocking_count",
            "effective_blocking_count",
            "blocking_count",
        ):
            payload["summary"][key] = 0

        with pytest.raises(ConsensusInputError, match="canonical blocking policy"):
            validate_consensus_payload(payload)

    def test_validator_rejects_false_quorum_and_source_membership(self) -> None:
        synth = ConsensusSynthesizer()
        report = synth.synthesize(
            "implementation", "target", [VendorResult(vendor="codex", findings=[_finding()])],
        )
        payload = synth.to_dict(report)
        payload["reviewers"][0]["success"] = False
        with pytest.raises(ConsensusInputError, match="eligible vendors"):
            validate_consensus_payload(payload)

        payload = synth.to_dict(report)
        payload["consensus_findings"][0]["source_findings"][0]["vendor"] = "invented"
        with pytest.raises(ConsensusInputError, match="source membership"):
            validate_consensus_payload(payload)

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
