"""Tests for skills.shared.trust_posture."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared import trust_posture as tp


def write_contract(root: Path, body: str, *, filename: str = tp.DEFAULT_CONTRACT_FILENAME) -> Path:
    path = root / filename
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return path


VALID_FULL = """
    ---
    schema_version: 1
    gates:
      gatekeeper_escalation:
        disposition: block
      proposal_approval:
        disposition: notify_with_timeout
        timeout_seconds: 3600
        default_action: proceed
      plan_review_convergence_failure:
        disposition: block
      validation_failure:
        disposition: block
      escalate_resume:
        disposition: notify_with_timeout
        timeout_seconds: 1800
        default_action: block
      replan_required:
        disposition: auto
      pr_creation:
        disposition: auto
      merge:
        disposition: block
    ---

    # Trust Posture
    Prose body that the loader ignores.
    """


# --------------------------------------------------------------------------- #
# Valid contract loads
# --------------------------------------------------------------------------- #

def test_valid_contract_loads(tmp_path: Path) -> None:
    write_contract(tmp_path, VALID_FULL)
    posture = tp.load_posture(tmp_path)
    assert posture.present is True
    assert posture.disposition_for(tp.Gate.PR_CREATION).disposition is tp.Disposition.AUTO
    nt = posture.disposition_for(tp.Gate.PROPOSAL_APPROVAL)
    assert nt.disposition is tp.Disposition.NOTIFY_WITH_TIMEOUT
    assert nt.timeout_seconds == 3600
    assert nt.default_action is tp.DefaultAction.PROCEED


def test_validate_posture_file_returns_no_errors_for_valid(tmp_path: Path) -> None:
    path = write_contract(tmp_path, VALID_FULL)
    assert tp.validate_posture_file(path) == []


# --------------------------------------------------------------------------- #
# The eight gates are all present / representable
# --------------------------------------------------------------------------- #

def test_all_eight_gates_enumerated() -> None:
    assert {g.value for g in tp.Gate} == {
        "gatekeeper_escalation",
        "proposal_approval",
        "plan_review_convergence_failure",
        "validation_failure",
        "escalate_resume",
        "replan_required",
        "pr_creation",
        "merge",
    }
    assert len(list(tp.Gate)) == 8


def test_all_eight_gates_representable_in_contract(tmp_path: Path) -> None:
    write_contract(tmp_path, VALID_FULL)
    posture = tp.load_posture(tmp_path)
    # every gate resolves to a concrete disposition without raising
    for gate in tp.Gate:
        assert isinstance(posture.disposition_for(gate), tp.GateDisposition)
    # and the template ships all eight too
    template = Path(__file__).resolve().parents[3] / tp.TEMPLATE_FILENAME
    assert template.exists(), "TRUST_POSTURE.template.md must ship at repo root"
    errors = tp.validate_posture_file(template)
    assert errors == [], errors


# --------------------------------------------------------------------------- #
# Absent file -> every gate blocks (the backward-compat guarantee)
# --------------------------------------------------------------------------- #

def test_absent_file_all_gates_block(tmp_path: Path) -> None:
    # tmp_path has no TRUST_POSTURE.md
    posture = tp.load_posture(tmp_path)
    assert posture.present is False
    assert posture.source_path is None
    for gate in tp.Gate:
        gd = posture.disposition_for(gate)
        assert gd.disposition is tp.Disposition.BLOCK
        assert gd.is_block is True
        assert gd.timeout_seconds is None
        assert gd.default_action is None


def test_gate_omitted_from_present_file_defaults_to_block(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 1
        gates:
          merge:
            disposition: auto
        ---
        """,
    )
    posture = tp.load_posture(tmp_path)
    assert posture.present is True
    assert posture.disposition_for(tp.Gate.MERGE).disposition is tp.Disposition.AUTO
    # every unconfigured gate falls back to block
    assert posture.disposition_for(tp.Gate.PR_CREATION).disposition is tp.Disposition.BLOCK


# --------------------------------------------------------------------------- #
# Each of the four disposition configurations round-trips
# (auto, block, notify_with_timeout+proceed, notify_with_timeout+block)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "gate_cfg, expected",
    [
        ({"disposition": "auto"}, tp.GateDisposition(tp.Disposition.AUTO)),
        ({"disposition": "block"}, tp.GateDisposition(tp.Disposition.BLOCK)),
        (
            {"disposition": "notify_with_timeout", "timeout_seconds": 900, "default_action": "proceed"},
            tp.GateDisposition(tp.Disposition.NOTIFY_WITH_TIMEOUT, 900, tp.DefaultAction.PROCEED),
        ),
        (
            {"disposition": "notify_with_timeout", "timeout_seconds": 120, "default_action": "block"},
            tp.GateDisposition(tp.Disposition.NOTIFY_WITH_TIMEOUT, 120, tp.DefaultAction.BLOCK),
        ),
    ],
)
def test_disposition_round_trip(tmp_path: Path, gate_cfg: dict, expected: tp.GateDisposition) -> None:
    import yaml

    doc = {"schema_version": 1, "gates": {"merge": gate_cfg}}
    (tmp_path / tp.DEFAULT_CONTRACT_FILENAME).write_text(
        "---\n" + yaml.safe_dump(doc, sort_keys=False) + "---\n", encoding="utf-8"
    )
    posture = tp.load_posture(tmp_path)
    assert posture.disposition_for(tp.Gate.MERGE) == expected


# --------------------------------------------------------------------------- #
# Unknown gate fails validation
# --------------------------------------------------------------------------- #

def test_unknown_gate_fails(tmp_path: Path) -> None:
    path = write_contract(
        tmp_path,
        """
        ---
        schema_version: 1
        gates:
          not_a_real_gate:
            disposition: block
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("not_a_real_gate" in e for e in exc.value.errors)
    assert any("not_a_real_gate" in e for e in tp.validate_posture_file(path))


# --------------------------------------------------------------------------- #
# Unknown disposition fails validation
# --------------------------------------------------------------------------- #

def test_unknown_disposition_fails(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 1
        gates:
          merge:
            disposition: yolo
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("yolo" in e for e in exc.value.errors)


# --------------------------------------------------------------------------- #
# Malformed / missing timeout for notify_with_timeout fails
# --------------------------------------------------------------------------- #

def test_notify_missing_timeout_fails(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 1
        gates:
          merge:
            disposition: notify_with_timeout
            default_action: block
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("timeout_seconds" in e for e in exc.value.errors)


@pytest.mark.parametrize("bad_timeout", ["0", "-5", "'abc'", "1.5", "true"])
def test_notify_malformed_timeout_fails(tmp_path: Path, bad_timeout: str) -> None:
    write_contract(
        tmp_path,
        f"""
        ---
        schema_version: 1
        gates:
          merge:
            disposition: notify_with_timeout
            timeout_seconds: {bad_timeout}
            default_action: proceed
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("timeout_seconds" in e for e in exc.value.errors)


def test_notify_missing_default_action_fails(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 1
        gates:
          merge:
            disposition: notify_with_timeout
            timeout_seconds: 600
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("default_action" in e for e in exc.value.errors)


def test_notify_unknown_default_action_fails(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 1
        gates:
          merge:
            disposition: notify_with_timeout
            timeout_seconds: 600
            default_action: maybe
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("default_action" in e for e in exc.value.errors)


def test_timeout_on_block_gate_fails(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 1
        gates:
          merge:
            disposition: block
            timeout_seconds: 600
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("only valid for notify_with_timeout" in e for e in exc.value.errors)


# --------------------------------------------------------------------------- #
# Structural / schema-version / front-matter errors
# --------------------------------------------------------------------------- #

def test_wrong_schema_version_fails(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 2
        gates:
          merge:
            disposition: block
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("schema_version" in e for e in exc.value.errors)


def test_missing_front_matter_fence_fails(tmp_path: Path) -> None:
    write_contract(tmp_path, "schema_version: 1\ngates: {}\n")
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("front-matter" in e for e in exc.value.errors)


def test_unterminated_front_matter_fails(tmp_path: Path) -> None:
    write_contract(tmp_path, "---\nschema_version: 1\ngates: {}\n")
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert any("unterminated" in e for e in exc.value.errors)


def test_multiple_errors_collected_in_one_pass(tmp_path: Path) -> None:
    write_contract(
        tmp_path,
        """
        ---
        schema_version: 9
        gates:
          bogus_gate:
            disposition: block
          merge:
            disposition: nonsense
        ---
        """,
    )
    with pytest.raises(tp.PostureValidationError) as exc:
        tp.load_posture(tmp_path)
    assert len(exc.value.errors) >= 3


# --------------------------------------------------------------------------- #
# disposition_for on unknown gate name raises (closed set)
# --------------------------------------------------------------------------- #

def test_disposition_for_unknown_gate_raises(tmp_path: Path) -> None:
    posture = tp.load_posture(tmp_path)  # absent -> all block
    with pytest.raises(ValueError):
        posture.disposition_for("no_such_gate")


def test_disposition_for_accepts_string_and_enum(tmp_path: Path) -> None:
    posture = tp.load_posture(tmp_path)
    assert posture.disposition_for("merge") == posture.disposition_for(tp.Gate.MERGE)


# --------------------------------------------------------------------------- #
# validate_posture_file on absent file
# --------------------------------------------------------------------------- #

def test_validate_posture_file_missing(tmp_path: Path) -> None:
    errors = tp.validate_posture_file(tmp_path / "nope.md")
    assert errors and "not found" in errors[0]


# --------------------------------------------------------------------------- #
# explicit path override
# --------------------------------------------------------------------------- #

def test_explicit_path_override(tmp_path: Path) -> None:
    path = write_contract(tmp_path, VALID_FULL, filename="custom.md")
    posture = tp.load_posture(path=path)
    assert posture.present is True
    assert posture.disposition_for(tp.Gate.MERGE).disposition is tp.Disposition.BLOCK
