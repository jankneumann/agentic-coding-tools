"""The gate's output makes no satisfaction claim (task 3.8).

Spec scenarios:
  - The Gate Makes No Claim That A Requirement Is Satisfied
      · output does not claim satisfaction

Design decisions: D5.

Asserts the spec's pinned line verbatim — `<N> operations cite <M>
requirements. This gate does not check that any requirement is satisfied.`
— rather than freezing an invented literal, and that `implemented`,
`satisfied`, `verified` are never applied to a requirement as subject
(the pinned line itself contains "satisfied", but as the negated object of
"does not check", never as a claim about a specific requirement).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "traceability"))

import check_traceability as gate  # noqa: E402
from builders import op, write_exclusions, write_openapi_doc, write_spec  # noqa: E402

_CANONICAL_LINE = "This gate does not check that any requirement is satisfied."
_FORBIDDEN_AS_SUBJECT = re.compile(
    r"\brequirement[s]?\b[^.\n]{0,40}\b(implemented|satisfied|verified)\b", re.IGNORECASE
)


def _run_and_format(tmp_path: Path, **overrides):
    kwargs = {
        "contracts_root": tmp_path / "contracts",
        "specs_root": tmp_path / "specs",
        "changes_root": tmp_path / "changes",
        "repo_root": tmp_path,
        "scope": "capability",
        "change_id": None,
    }
    kwargs.update(overrides)
    result, _touched = gate.run_gate(**kwargs)
    text = gate._format_report(result, scope=kwargs["scope"], change_id=kwargs["change_id"])
    return result, text


def test_passing_run_contains_the_canonical_line(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    write_exclusions(tmp_path / "contracts", "widget", [])

    result, text = _run_and_format(tmp_path)
    assert result.exit_code == 0
    assert _CANONICAL_LINE in text
    pattern = r"^1 operations cite 1 requirements\. " + re.escape(_CANONICAL_LINE)
    assert re.search(pattern, text, re.MULTILINE)


def test_the_line_states_the_real_counts(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha", "Beta"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [
            op("op0", "/w0", x_traceability={"requirements": ["widget.alpha", "widget.beta"]}),
            op("op1", "/w1", x_traceability={"requirements": ["widget.alpha"]}),
        ],
    )
    write_exclusions(tmp_path / "contracts", "widget", [])
    result, text = _run_and_format(tmp_path)
    assert result.exit_code == 0
    assert "2 operations cite 2 requirements." in text


def test_output_never_applies_implemented_satisfied_verified_to_a_requirement(
    tmp_path: Path,
) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    write_exclusions(tmp_path / "contracts", "widget", [])
    _result, text = _run_and_format(tmp_path)

    # Strip the one pinned line before scanning, so the negated "satisfied"
    # inside it (which is the required phrasing, not a claim) can't produce
    # a false positive.
    stripped = text.replace(_CANONICAL_LINE, "")
    assert not _FORBIDDEN_AS_SUBJECT.search(stripped), (
        "output applied implemented/satisfied/verified to a requirement outside "
        "the pinned canonical line"
    )
