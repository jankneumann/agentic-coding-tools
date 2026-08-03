"""The generated Contract Ref column (tasks 5.4-5.5).

Design decisions: D8.

Must fail on the current hand-filled matrix, which is the point — the
column has never been checked against anything before this generator
existed. Joins matrix rows to citations by parse position of the same spec
parse, never by name similarity, and never changes the ordinal Req ID
format.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "traceability"))

import generate_contract_refs as refgen  # noqa: E402
from builders import op, write_cli_doc, write_openapi_doc  # noqa: E402


def _write_change_delta(
    changes_root: Path, change_id: str, capability: str, headings: list[str]
) -> None:
    body = "## ADDED Requirements\n\n" + "\n\n".join(
        f"### Requirement: {h}\n\nThe system SHALL do the {h} thing.\n\n"
        f"#### Scenario: it happens\n\n- WHEN x\n- THEN y\n"
        for h in headings
    )
    target = changes_root / change_id / "specs" / capability / "spec.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def _write_change_context(changes_root: Path, change_id: str, rows: list[tuple[str, str]]) -> Path:
    """``rows``: ``[(req_id, contract_ref_cell), ...]``."""
    header = (
        "# Change Context: "
        + change_id
        + "\n\n## Requirement Traceability Matrix\n\n"
        + "| Req ID | Spec Source | Description | Contract Ref | Design Decision | "
        "Files Changed | Test(s) | Evidence |\n"
        "|--------|------------|-------------|-------------|----------------|"
        "---------------|---------|----------|\n"
    )
    body = "".join(
        f"| {req_id} | spec.md | some requirement | {ref} | --- | --- | --- | --- |\n"
        for req_id, ref in rows
    )
    target = changes_root / change_id / "change-context.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(header + body, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------


def test_generates_contract_ref_from_a_real_citation(tmp_path: Path) -> None:
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="my-change",
    )
    assert refs["widget.1"] == "contracts/widget/openapi/svc.yaml"


def test_uncited_requirement_gets_the_placeholder(tmp_path: Path) -> None:
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="my-change",
    )
    assert refs["widget.1"] == "---"


def test_multiple_citing_documents_are_joined(tmp_path: Path) -> None:
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
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
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="my-change",
    )
    cell = refs["widget.1"]
    assert "contracts/widget/openapi/one.yaml" in cell
    assert "contracts/widget/openapi/two.yaml" in cell


def test_cli_archetype_citations_are_found_too(tmp_path: Path) -> None:
    _write_change_delta(tmp_path / "changes", "widget", "widget", ["Alpha"])
    write_cli_doc(
        tmp_path / "contracts",
        "widget",
        "widget.yaml",
        [
            {
                "name": "",
                "flags": [
                    {
                        "name": "--x",
                        "type": "string",
                        "traceability": {"requirements": ["widget.alpha"]},
                    }
                ],
            }
        ],
    )
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="widget",
    )
    assert refs["widget.1"] == "contracts/widget/cli/widget.yaml"


def test_ordinal_req_id_format_is_unchanged(tmp_path: Path) -> None:
    """<capability>.<N>, sequential — D8 leaves the ordinal format alone."""
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha", "Beta", "Gamma"])
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="my-change",
    )
    assert set(refs) == {"widget.1", "widget.2", "widget.3"}


def test_join_is_by_parse_position_not_by_heading_name_similarity(tmp_path: Path) -> None:
    """Two capabilities each add a requirement titled identically ("Alpha").
    A name-matching join would conflate them; a position-based join (D8)
    keeps each capability's own citation separate.
    """
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
    _write_change_delta(tmp_path / "changes", "my-change", "gadget", ["Alpha"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    # gadget.alpha is never cited.
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="my-change",
    )
    assert refs["widget.1"] == "contracts/widget/openapi/svc.yaml"
    assert refs["gadget.1"] == "---"  # NOT contaminated by widget's citation


# ---------------------------------------------------------------------------
# the RED demonstration: a hand-filled matrix has never been checked
# ---------------------------------------------------------------------------


def test_a_hand_filled_wrong_ref_is_corrected_by_the_rewrite(tmp_path: Path) -> None:
    """The whole point of task 5.4: the current hand-filled column has never
    been checked against anything, so a stale/wrong value must FAIL an
    identity check and be corrected by regeneration — not silently agree
    with the generator because it always agreed with itself.
    """
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    context_path = _write_change_context(
        tmp_path / "changes",
        "my-change",
        [("widget.1", "contracts/some/renamed-three-changes-ago.yaml")],  # stale hand-fill
    )
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="my-change",
    )
    original = context_path.read_text(encoding="utf-8")
    updated = refgen.rewrite_contract_ref_column(original, refs)

    assert original != updated, "the stale hand-filled value must not silently agree with itself"
    assert "contracts/widget/openapi/svc.yaml" in updated
    assert "renamed-three-changes-ago" not in updated


def test_rewrite_leaves_rows_outside_the_matrix_untouched(tmp_path: Path) -> None:
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
    context_path = _write_change_context(tmp_path / "changes", "my-change", [("widget.1", "---")])
    text = context_path.read_text(encoding="utf-8")
    text += "\n## Design Decision Trace\n\n| Decision | Rationale |\n|---|---|\n| D1 | x |\n"
    refs = refgen.generate(
        changes_root=tmp_path / "changes",
        contracts_root=tmp_path / "contracts",
        repo_root=tmp_path,
        change_id="my-change",
    )
    updated = refgen.rewrite_contract_ref_column(text, refs)
    assert "| D1 | x |" in updated


def test_check_mode_exits_nonzero_on_a_stale_matrix(tmp_path: Path, capsys) -> None:
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    _write_change_context(tmp_path / "changes", "my-change", [("widget.1", "---")])  # stale

    exit_code = refgen.main(
        [
            "--change",
            "my-change",
            "--changes-root",
            str(tmp_path / "changes"),
            "--contracts-root",
            str(tmp_path / "contracts"),
            "--repo-root",
            str(tmp_path),
            "--check",
        ]
    )
    assert exit_code == 1


def test_check_mode_exits_zero_once_regenerated(tmp_path: Path) -> None:
    _write_change_delta(tmp_path / "changes", "my-change", "widget", ["Alpha"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    _write_change_context(tmp_path / "changes", "my-change", [("widget.1", "---")])

    write_args = [
        "--change",
        "my-change",
        "--changes-root",
        str(tmp_path / "changes"),
        "--contracts-root",
        str(tmp_path / "contracts"),
        "--repo-root",
        str(tmp_path),
    ]
    assert refgen.main(write_args) == 0
    assert refgen.main([*write_args, "--check"]) == 0
