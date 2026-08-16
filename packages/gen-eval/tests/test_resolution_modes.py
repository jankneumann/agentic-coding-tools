"""The two resolution modes, and their orthogonality to `--scope` (task 3.16).

Spec scenarios:
  - The Full Sweep Blocks Opted-In Surfaces And Reports The Rest
      · the change flag selects which delta shadows the archive
      · omitting the change flag unions every on-branch delta

Design decisions: D12.

`--change` selects RESOLUTION and is orthogonal to `--scope`:
`--scope capability --change <id>` is exactly what task 5.7c runs on the
merge candidate. Supplied: the archive is shadowed by that one change's
delta, other in-flight changes neither citable nor excludable. Omitted: the
archive is shadowed by the union of every delta directly under
`openspec/changes/<id>/`, EXCLUDING `openspec/changes/archive/` — asserted
here against a fixture that has an `archive/` subtree, since the real
`openspec/changes/archive/` is 128 deltas deep and makes a poor unit
fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "traceability"))

import check_traceability as gate  # noqa: E402
from builders import op, write_delta, write_openapi_doc, write_spec  # noqa: E402


def _run(tmp_path: Path, *, change_id: str | None, scope: str = "capability"):
    result, touched = gate.run_gate(
        contracts_root=tmp_path / "contracts",
        specs_root=tmp_path / "specs",
        changes_root=tmp_path / "changes",
        repo_root=tmp_path,
        scope=scope,
        change_id=change_id,
    )
    return result


# ---------------------------------------------------------------------------
# --change <id> selects which delta shadows the archive
# ---------------------------------------------------------------------------


def test_change_flag_selects_the_resolution_delta(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    write_delta(tmp_path / "changes", "change-a", "widget", added=["FromA"])
    write_delta(tmp_path / "changes", "change-b", "widget", added=["FromB"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.froma"]})],
    )

    # --scope capability --change change-a: citation to change-a's own new
    # requirement resolves; change-b's is simply not in this run's universe
    # (not asserted here — op0 doesn't cite it).
    result = _run(tmp_path, change_id="change-a")
    assert result.exit_code == 0
    assert not any("widget.froma" in e for e in result.errors)


def test_other_in_flight_changes_do_not_resolve_under_a_named_change(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    write_delta(tmp_path / "changes", "change-a", "widget", added=["FromA"])
    write_delta(tmp_path / "changes", "change-b", "widget", added=["FromB"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        # change-b's requirement, not change-a's
        [op("op0", "/w0", x_traceability={"requirements": ["widget.fromb"]})],
    )
    result = _run(tmp_path, change_id="change-a")
    assert result.exit_code == 1
    message = next(e for e in result.errors if "widget.fromb" in e)
    assert "not in the effective requirement set" in message


# ---------------------------------------------------------------------------
# omitting --change unions every on-branch delta, excluding archive/
# ---------------------------------------------------------------------------


def test_omitted_change_flag_unions_every_on_branch_delta(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    write_delta(tmp_path / "changes", "change-a", "widget", added=["FromA"])
    write_delta(tmp_path / "changes", "change-b", "widget", added=["FromB"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "one.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.froma"]})],
    )
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "two.yaml",
        [op("op1", "/w1", x_traceability={"requirements": ["widget.fromb"]})],
    )
    result = _run(tmp_path, change_id=None)
    assert result.exit_code == 0
    assert result.errors == []


def test_union_mode_does_not_fail_for_the_absence_of_a_change_id(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    result = _run(tmp_path, change_id=None)
    assert result.exit_code == 0
    assert not any("--change" in e for e in result.errors)


def test_union_mode_excludes_archived_deltas(tmp_path: Path) -> None:
    """Deltas under `openspec/changes/archive/` are already merged into
    `openspec/specs/`; re-applying them would resurrect a REMOVED
    requirement or re-move a RENAMED one. Fixture: the archived delta
    REMOVES a requirement the (already-merged) archive spec still carries —
    if union mode incorrectly re-applied it, the requirement would
    disappear and the citation below would fail to resolve.
    """
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    archive_delta = (
        tmp_path / "changes" / "archive" / "2026-01-01-old-change" / "specs" / "widget" / "spec.md"
    )
    archive_delta.parent.mkdir(parents=True, exist_ok=True)
    archive_delta.write_text(
        "## REMOVED Requirements\n\n### Requirement: Alpha\n", encoding="utf-8"
    )
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]})],
    )
    result = _run(tmp_path, change_id=None)
    assert result.exit_code == 0
    assert not any("widget.alpha" in e for e in result.errors)


# ---------------------------------------------------------------------------
# --scope capability --change <id> — the orthogonal combination 5.7c runs
# ---------------------------------------------------------------------------


def test_scope_capability_with_change_combination_parses_and_runs(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    write_delta(tmp_path / "changes", "my-change", "widget", added=["FromChange"])
    write_openapi_doc(
        tmp_path / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.fromchange"]})],
    )
    result = _run(tmp_path, change_id="my-change", scope="capability")
    assert result.exit_code == 0


def test_scope_capability_bare_is_the_post_merge_job_and_does_not_error(tmp_path: Path) -> None:
    write_spec(tmp_path / "specs", "widget", ["Alpha"])
    result = _run(tmp_path, change_id=None, scope="capability")
    assert result.exit_code == 0
