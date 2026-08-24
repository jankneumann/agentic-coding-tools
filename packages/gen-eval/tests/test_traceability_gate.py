"""The bidirectional completeness gate: forward, reverse, exclusions, opt-in
switches, and malformed-input fail-closed behavior (tasks 3.1-3.7).

Spec scenarios (gen-eval-framework spec delta):
  - Traceability Completeness Is Enforced In Both Directions (forward,
    reverse, every-failure-is-named)
  - Traceability Exclusions State A Reason (blank/stale/valid exclusions,
    cross-capability exclusion fails)
  - Forward Enforcement Is Opt-In Per Contract Document
  - Reverse Enforcement Is Opt-In Per Capability Via The Exclusions File
  - The Gate Fails Closed On Malformed Input (all sub-scenarios)

Design decisions: D3, D4, D5, D6, D13.

Every check below is demonstrated to FAIL per the RED protocol before
asserting the corresponding pass — a gate observed only to pass is
decoration.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "traceability"))

import check_traceability as gate  # noqa: E402
from builders import (  # noqa: E402
    op,
    write_exclusions,
    write_openapi_doc,
    write_spec,
)


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
# 3.1 — forward completeness
# ---------------------------------------------------------------------------


class TestForwardCompleteness:
    def test_ten_operations_nine_cite_one_does_not(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        operations = [
            op(f"op{i}", f"/w{i}", x_traceability={"requirements": ["widget.alpha"]})
            for i in range(9)
        ]
        operations.append(op("op9", "/w9"))  # the tenth: uncited, no exclusion
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", operations)

        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("op9" in f for f in result.forward_failures)
        # the gate must NOT pass on the 90% proportion
        assert not any("op0" in f or "op8" in f for f in result.forward_failures)

    def test_all_operations_cite_passes(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        operations = [
            op(f"op{i}", f"/w{i}", x_traceability={"requirements": ["widget.alpha"]})
            for i in range(3)
        ]
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", operations)
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert result.forward_failures == []


# ---------------------------------------------------------------------------
# 3.2 — reverse completeness
# ---------------------------------------------------------------------------


class TestReverseCompleteness:
    def test_uncited_requirement_fails_when_reverse_enforced(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
        )
        write_exclusions(tmp_path / "contracts", "widget", [])  # opts in, empty

        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("widget.beta" in f for f in result.reverse_failures)

    def test_every_failure_reported_in_one_run(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta", "Gamma", "Delta"])
        operations = [
            op("op0", "/w0"),  # uncited operation 1
            op("op1", "/w1"),  # uncited operation 2
            op("op2", "/w2", x_traceability={"requirements": ["widget.alpha"]}),
        ]
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", operations)
        write_exclusions(tmp_path / "contracts", "widget", [])  # beta, gamma, delta uncited

        result = _run(tmp_path)
        assert result.exit_code == 1
        assert len(result.forward_failures) == 2
        assert len(result.reverse_failures) == 3  # beta, gamma, delta


# ---------------------------------------------------------------------------
# 3.3 — operation exclusions
# ---------------------------------------------------------------------------


class TestOperationExclusions:
    def test_blank_reason_fails(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [op("op0", "/w0", x_traceability={"excluded": {"reason": ""}})],
        )
        # The traceability.schema.json's minLength:1 rejects this at parse
        # time (TraceabilityBlock's own pydantic validator mirrors it) — the
        # document therefore fails to parse rather than "excludes with a
        # blank reason", which is still the required outcome: non-zero exit
        # naming the file.
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert result.errors

    def test_stale_exclusion_target_operation_removed(self, tmp_path: Path) -> None:
        """An operation exclusion whose operation no longer exists is simply
        absent from the document — there is nothing to be "stale": the
        contract IS the source of truth for which operations exist. Verifies
        the excluded operation, while present, is not double-counted."""
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [op("op0", "/w0", x_traceability={"excluded": {"reason": "health probe"}})],
        )
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any("op0" in r and "health probe" in r for r in result.reports)

    def test_excluded_operation_does_not_fail_forward_and_reason_appears(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [
                op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]}),
                op("op1", "/w1", x_traceability={"excluded": {"reason": "infra, not product"}}),
            ],
        )
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert result.forward_failures == []
        assert any("op1" in r and "infra, not product" in r for r in result.reports)


# ---------------------------------------------------------------------------
# 3.4 — requirement exclusions and the reverse opt-in switch
# ---------------------------------------------------------------------------


class TestRequirementExclusions:
    def test_file_present_uncited_requirement_fails(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_exclusions(tmp_path / "contracts", "widget", [])
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("widget.alpha" in f for f in result.reverse_failures)

    def test_file_present_excluded_requirement_passes_with_reason(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_exclusions(
            tmp_path / "contracts",
            "widget",
            [{"requirement": "widget.alpha", "reason": "no CLI surface"}],
        )
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any("widget.alpha" in r and "no CLI surface" in r for r in result.reports)

    def test_file_absent_uncited_requirement_reported_exit_zero(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", [op("op0", "/w0")])
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any("widget.alpha" in r for r in result.reports)
        assert result.reverse_failures == []

    def test_file_present_empty_list_means_every_requirement_cited(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
        )
        write_exclusions(tmp_path / "contracts", "widget", [])
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("widget.beta" in f for f in result.reverse_failures)

    def test_cross_capability_exclusion_fails_naming_both(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "a", ["Alpha"])
        write_spec(tmp_path / "specs", "b", ["Beta"])
        write_exclusions(tmp_path / "contracts", "a", [{"requirement": "b.beta", "reason": "n/a"}])
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("a" in e and "b" in e for e in result.errors)

    def test_cross_capability_exclusion_does_not_discharge_bs_own_enforcement(
        self, tmp_path: Path
    ) -> None:
        """b's own reverse completeness, once b opts in independently, is
        untouched by a's illegal exclusion — beta still fails b's own run."""
        write_spec(tmp_path / "specs", "a", ["Alpha"])
        write_spec(tmp_path / "specs", "b", ["Beta"])
        write_exclusions(tmp_path / "contracts", "a", [{"requirement": "b.beta", "reason": "n/a"}])
        write_exclusions(tmp_path / "contracts", "b", [])  # b opts in itself, excludes nothing
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("b.beta" in f for f in result.reverse_failures)


class TestUnreadableExclusionsFile:
    """3.4b — the highest-consensus finding of the plan review. D13 makes
    the file's EXISTENCE the reverse switch, so an accident must never read
    as an absent one."""

    def test_unparseable_yaml_fails_and_does_not_report_not_opted_in(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_exclusions(tmp_path / "contracts", "widget", raw_text="not: valid: yaml: [")
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("widget" in e for e in result.errors)
        assert not any("not opted in" in r for r in result.reports if "widget" in r)

    def test_schema_invalid_content_fails(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_exclusions(tmp_path / "contracts", "widget", raw_text="some_other_key: true\n")
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert not any("not opted in" in r for r in result.reports if "widget" in r)

    def test_zero_byte_file_fails(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        target = write_exclusions(tmp_path / "contracts", "widget", raw_text="")
        assert target.stat().st_size == 0
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert not any("not opted in" in r for r in result.reports if "widget" in r)

    def test_unreadable_file_fails(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        target = write_exclusions(tmp_path / "contracts", "widget", [])
        target.chmod(0o000)
        try:
            result = _run(tmp_path)
            assert result.exit_code == 1
            assert not any("not opted in" in r for r in result.reports if "widget" in r)
        finally:
            target.chmod(stat.S_IRUSR | stat.S_IWUSR)  # restore so tmp_path cleanup can remove it


# ---------------------------------------------------------------------------
# 3.5 — forward opt-in enforcement
# ---------------------------------------------------------------------------


class TestForwardOptIn:
    def test_declaring_traceability_commits_the_whole_document(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [
                op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]}),
                op("op1", "/w1"),  # omits it
            ],
        )
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("op1" in f for f in result.forward_failures)

    def test_untraced_document_is_recorded_not_failed(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", [op("op0", "/w0")])
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any("untraced" in r for r in result.reports)

    def test_mixed_capability_traced_and_untraced_documents(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "traced.yaml",
            [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
        )
        write_openapi_doc(tmp_path / "contracts", "widget", "untraced.yaml", [op("op1", "/w1")])
        write_exclusions(tmp_path / "contracts", "widget", [])

        result = _run(tmp_path)
        assert result.exit_code == 1  # widget.beta is uncited (reverse-enforced)
        assert result.forward_failures == []  # untraced.yaml's op1 is not enforced
        assert any("untraced.yaml" in r and "untraced" in r for r in result.reports)
        # the traced document's citation still counts toward reverse completeness
        assert not any("widget.alpha" in f for f in result.reverse_failures)


# ---------------------------------------------------------------------------
# 3.6 — malformed input and document discovery
# ---------------------------------------------------------------------------


class TestMalformedInputAndDiscovery:
    def test_unparseable_contract_fails_naming_the_file_not_untraced(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        target = write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", [op("op0", "/w0")])
        target.write_text("openapi: 3.1.0\npaths: [unterminated", encoding="utf-8")
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("svc.yaml" in e for e in result.errors)
        assert not any("svc.yaml" in r and "untraced" in r for r in result.reports)

    def test_schema_invalid_traceability_block_fails_naming_file_and_operation(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [
                op(
                    "op0",
                    "/w0",
                    x_traceability={"requirements": ["widget.alpha"], "excluded": {"reason": "x"}},
                )
            ],
        )
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("svc.yaml" in e for e in result.errors)

    def test_contracts_without_a_capability_spec_fails_distinctly(self, tmp_path: Path) -> None:
        # No write_spec call — capability has no spec.md at all.
        write_openapi_doc(
            tmp_path / "contracts",
            "widget",
            "svc.yaml",
            [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
        )
        result = _run(tmp_path)
        assert result.exit_code == 1
        message = next(e for e in result.errors if "widget" in e)
        assert "no spec" in message or "spec.md" in message
        assert "not in the effective requirement set" not in message

    def test_specless_untraced_capability_is_reported_not_failed(self, tmp_path: Path) -> None:
        write_openapi_doc(tmp_path / "contracts", "widget", "svc.yaml", [op("op0", "/w0")])
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any("widget" in r for r in result.reports)

    def test_capability_with_spec_and_no_contracts_is_forward_untraced(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        result = _run(tmp_path)
        assert result.exit_code == 0

    def test_capability_with_spec_no_contracts_but_exclusions_enforces_reverse(
        self, tmp_path: Path
    ) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_exclusions(tmp_path / "contracts", "widget", [])
        result = _run(tmp_path)
        assert result.exit_code == 1
        assert any("widget.alpha" in f for f in result.reverse_failures)

    def test_misplaced_instance_is_reported_and_sweep_does_not_fail(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        write_openapi_doc(
            tmp_path / "contracts", "widget", "root.yaml", [op("op0", "/w0")], location="root"
        )
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert any("misplaced" in r and "root.yaml" in r for r in result.reports)

    def test_readme_and_exclusions_at_root_are_never_instances(self, tmp_path: Path) -> None:
        write_spec(tmp_path / "specs", "widget", ["Alpha"])
        cap_dir = tmp_path / "contracts" / "widget"
        cap_dir.mkdir(parents=True, exist_ok=True)
        (cap_dir / "README.md").write_text("# widget contracts\n", encoding="utf-8")
        write_exclusions(tmp_path / "contracts", "widget", [])  # the switch itself
        result = _run(tmp_path)
        assert result.exit_code == 1  # widget.alpha uncited, reverse enforced
        assert not any("README.md" in r for r in result.reports)
        assert not any("misplaced" in r and "traceability-exclusions" in r for r in result.reports)

    def test_schemas_only_capability_holds_no_contract_documents(self, tmp_path: Path) -> None:
        schemas_dir = tmp_path / "contracts" / "widget" / "schemas"
        schemas_dir.mkdir(parents=True, exist_ok=True)
        (schemas_dir / "thing.schema.json").write_text("{}", encoding="utf-8")
        result = _run(tmp_path)
        assert result.exit_code == 0
        assert not any("widget" in e for e in result.errors)
