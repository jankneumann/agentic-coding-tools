"""Capability-scoped completeness, concentration reporting, and
cross-capability citations (tasks 3.9, 3.11, 3.13).

Spec scenarios:
  - The Gate Reports Citation Concentration Deterministically
  - Completeness Is Evaluated Per Capability
  - Citations May Name Requirements In Another Capability

Design decisions: D7, D9, D10.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "traceability"))

import check_traceability as gate  # noqa: E402
from builders import op, write_exclusions, write_openapi_doc, write_spec  # noqa: E402


def _run(tmp_path: Path, **overrides):
    kwargs = {
        "contracts_root": tmp_path / "contracts",
        "specs_root": tmp_path / "specs",
        "changes_root": tmp_path / "changes",
        "repo_root": tmp_path,
        "scope": "capability",
        "change_id": None,
    }
    kwargs.update(overrides)
    result, touched = gate.run_gate(**kwargs)
    return result


# ---------------------------------------------------------------------------
# 3.9 — concentration reporting
# ---------------------------------------------------------------------------


class TestConcentrationReporting:
    def test_concentration_appears_at_or_above_the_trigger(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        operations = [
            op(f"op{i}", f"/w{i}", x_traceability={"requirements": ["widget.alpha"]})
            for i in range(4)
        ] + [
            op(f"op{i}", f"/w{i}", x_traceability={"requirements": ["widget.beta"]})
            for i in range(4, 6)
        ]
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", operations)
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any(
            "widget.alpha" in c and "4/6" in c and "concentrated" in c for c in result.concentration
        )
        assert any("widget.beta" in c and "2/6" in c for c in result.concentration)
        assert not any("widget.beta" in c and "concentrated" in c for c in result.concentration)
        assert gate.CONCENTRATION_REPORT_SHARE <= 4 / 6

    def test_concentration_only_run_still_exits_zero(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        operations = [
            op(f"op{i}", f"/w{i}", x_traceability={"requirements": ["widget.alpha"]})
            for i in range(3)
        ]
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", operations)
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert result.concentration  # concentration WAS reported
        assert any("concentrated" in c for c in result.concentration)

    def test_concentration_entry_still_present_when_run_fails(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        operations = [
            op(f"op{i}", f"/w{i}", x_traceability={"requirements": ["widget.alpha"]})
            for i in range(3)
        ]
        operations.append(op("uncited", "/uncited"))  # forces a forward failure
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", operations)
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("concentrated" in c for c in result.concentration)


# ---------------------------------------------------------------------------
# 3.11 — capability-scoped completeness
# ---------------------------------------------------------------------------


class TestCapabilityScopedCompleteness:
    def test_requirement_served_from_a_different_document_is_covered(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "one.yaml",
            [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
        )
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "two.yaml",
            [op("op1", "/w1", x_traceability={"requirements": ["widget.beta"]})],
        )
        write_exclusions(tmp_path / "contracts", "widget", [])
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert result.reverse_failures == []

    def test_requirement_cited_by_neither_document_fails_exactly_once(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "one.yaml",
            [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
        )
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "two.yaml",
            [op("op1", "/w1", x_traceability={"requirements": ["widget.alpha"]})],
        )
        write_exclusions(tmp_path / "contracts", "widget", [])
        result = _run(tmp_path)
        assert result.exit_code == 1
        beta_failures = [f for f in result.reverse_failures if "widget.beta" in f]
        assert len(beta_failures) == 1

    def test_split_capability_evaluated_identically_to_combined(self, tmp_path: Path) -> None:
        # Split version.
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "one.yaml",
            [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
        )
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "two.yaml",
            [op("op1", "/w1", x_traceability={"requirements": ["widget.beta"]})],
        )
        write_exclusions(tmp_path / "contracts", "widget", [])
        split_result = _run(tmp_path)

        # Combined version, same citations, one document.
        tmp_path2 = tmp_path / "combined"
        write_spec(tmp_path2 / "specs", "widget", ["Alpha", "Beta"])
        write_openapi_doc(
            tmp_path2 / "contracts",
            "widget",
            "combined.yaml",
            [
                op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]}),
                op("op1", "/w1", x_traceability={"requirements": ["widget.beta"]}),
            ],
        )
        write_exclusions(tmp_path2 / "contracts", "widget", [])
        combined_result = _run(tmp_path2)

        assert split_result.exit_code == combined_result.exit_code == 0
        assert split_result.reverse_failures == combined_result.reverse_failures == []


# ---------------------------------------------------------------------------
# 3.13 — cross-capability citations
# ---------------------------------------------------------------------------


class TestCrossCapabilityCitations:
    def test_operation_cites_another_capabilitys_requirement(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "a", ["Alpha"])
        write_spec(tmp_path / "specs", "b", ["Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "a",
            "svc.yaml",
            [op("op0", "/a0", x_traceability={"requirements": ["b.beta"]})],
        )
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any("op0" in c and "b.beta" in c for c in result.cross_capability)

    def test_cross_capability_citation_credits_the_cited_capabilitys_reverse_completeness(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "a", ["Alpha"])
        write_spec(tmp_path / "specs", "b", ["Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "a",
            "svc.yaml",
            [op("op0", "/a0", x_traceability={"requirements": ["b.beta"]})],
        )
        write_exclusions(tmp_path / "contracts", "b", [])  # b opts in, cites nothing itself
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert result.reverse_failures == []

    def test_unresolvable_cross_capability_citation_fails_unknown_capability(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "a", ["Alpha"])
        write_openapi_doc(
            tmp_path / "contracts",
            "a",
            "svc.yaml",
            [op("op0", "/a0", x_traceability={"requirements": ["nonexistent-capability.x"]})],
        )
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("nonexistent-capability" in e for e in result.errors)

    def test_unresolvable_cross_capability_citation_fails_unknown_requirement(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "a", ["Alpha"])
        write_spec(tmp_path / "specs", "b", ["Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "a",
            "svc.yaml",
            [op("op0", "/a0", x_traceability={"requirements": ["b.nonexistent-requirement"]})],
        )
        result = _run(tmp_path)
        assert result.exit_code == 1
        message = next(e for e in result.errors if "b.nonexistent-requirement" in e)
        assert "not in the effective requirement set" in message

    def test_unknown_capability_and_unknown_requirement_are_distinguishable(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "a", ["Alpha"])
        write_spec(tmp_path / "specs", "b", ["Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "a",
            "svc.yaml",
            [
                op("op0", "/a0", x_traceability={"requirements": ["ghost-capability.x"]}),
                op("op1", "/a1", x_traceability={"requirements": ["b.ghost-requirement"]}),
            ],
        )
        result = _run(tmp_path)
        unknown_cap = next(e for e in result.errors if "ghost-capability" in e)
        unknown_req = next(e for e in result.errors if "b.ghost-requirement" in e)
        assert unknown_cap != unknown_req
