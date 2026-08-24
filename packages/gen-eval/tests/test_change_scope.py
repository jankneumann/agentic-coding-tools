"""Change-scoped evaluation (task 3.15).

Spec scenarios:
  - Validation-Time Evaluation Is Scoped To The Change
      · a pre-existing gap does not fail a change that did not create it
      · a requirement the change adds and nobody cites fails the
        change-scoped run
      · opting a document in touches every operation in it
      · opting a capability in touches every requirement of it
      · an unresolvable merge base is an error, not an empty scope
      · the output states which scope it evaluated

Design decisions: D12.

Every fixture `git init`s a throwaway repo under `tmp_path` — a test
diffing the real worktree's merge base would be nondeterministic, changing
as this package itself commits (task 3.15's note).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "traceability"))

import check_traceability as gate  # noqa: E402
from builders import (  # noqa: E402
    checkout_branch,
    commit_all,
    init_repo,
    op,
    write_delta,
    write_exclusions,
    write_openapi_doc,
    write_spec,
)


def _run_change_scope(repo: Path, change_id: str, **overrides):
    kwargs = {
        "contracts_root": repo / "contracts",
        "specs_root": repo / "specs",
        "changes_root": repo / "changes",
        "repo_root": repo,
        "scope": "change",
        "change_id": change_id,
        "base_ref": "main",
    }
    kwargs.update(overrides)
    result, touched = gate.run_gate(**kwargs)
    return result, touched


def _base_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    init_repo(repo)
    return repo


# ---------------------------------------------------------------------------
# a pre-existing gap does not fail a change that did not create it
# ---------------------------------------------------------------------------


def test_pre_existing_gap_does_not_block_a_change_that_did_not_create_it(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    write_spec(repo / "specs", "widget", ["Alpha", "Beta"])
    write_openapi_doc(
        repo / "contracts",
        "widget",
        "svc.yaml",
        [
            op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]}),
            op("op1", "/w1"),  # pre-existing uncited operation, same file
        ],
    )
    commit_all(repo, "base: widget contract, op1 already uncited")
    checkout_branch(repo, "feature")

    # The change touches op0's requirement list (still just alpha) — a
    # no-op edit to the same node, so the file changes but op1 does not.
    write_openapi_doc(
        repo / "contracts",
        "widget",
        "svc.yaml",
        [
            op(
                "op0",
                "/w0",
                x_traceability={"requirements": ["widget.alpha"]},
                summary="touched",
            ),
            op("op1", "/w1"),
        ],
    )
    write_delta(repo / "changes", "my-change", "widget", added=[])
    commit_all(repo, "my-change: touch op0's summary")

    result, touched = _run_change_scope(repo, "my-change")
    assert result.exit_code == 0
    assert not any("op1" in f for f in result.forward_failures)
    assert any("op1" in r and "pre-existing" in r for r in result.reports)


# ---------------------------------------------------------------------------
# a requirement the change adds and nobody cites fails the change-scoped run
# ---------------------------------------------------------------------------


def test_added_requirement_nobody_cites_fails_change_scope(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    write_spec(repo / "specs", "widget", ["Alpha"])
    write_exclusions(repo / "contracts", "widget", [])
    commit_all(repo, "base: widget opts into reverse enforcement")
    checkout_branch(repo, "feature")

    write_delta(repo / "changes", "my-change", "widget", added=["Gamma"])
    commit_all(repo, "my-change: adds Gamma, nobody cites it")

    result, touched = _run_change_scope(repo, "my-change")
    assert result.exit_code == 1
    assert any("widget.gamma" in f for f in result.reverse_failures)


def test_added_requirement_that_is_cited_does_not_fail(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    write_spec(repo / "specs", "widget", ["Alpha"])
    write_exclusions(repo / "contracts", "widget", [])
    write_openapi_doc(repo / "contracts", "widget", "svc.yaml", [op("op0", "/w0")])
    commit_all(repo, "base")
    checkout_branch(repo, "feature")

    write_delta(repo / "changes", "my-change", "widget", added=["Gamma"])
    write_openapi_doc(
        repo / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0", x_traceability={"requirements": ["widget.gamma"]})],
    )
    commit_all(repo, "my-change: adds Gamma and cites it")

    result, touched = _run_change_scope(repo, "my-change")
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# opting a document in touches every operation in it
# ---------------------------------------------------------------------------


def test_opting_a_document_in_touches_every_operation_in_it(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    write_spec(repo / "specs", "widget", ["Alpha", "Beta"])
    write_openapi_doc(
        repo / "contracts",
        "widget",
        "svc.yaml",
        [op("op0", "/w0"), op("op1", "/w1")],  # fully untraced document
    )
    commit_all(repo, "base: untraced document")
    checkout_branch(repo, "feature")

    write_delta(repo / "changes", "my-change", "widget", added=[])
    write_openapi_doc(
        repo / "contracts",
        "widget",
        "svc.yaml",
        [
            op("op0", "/w0", x_traceability={"requirements": ["widget.alpha"]}),
            op("op1", "/w1"),  # still uncited — but the document just opted in
        ],
    )
    commit_all(repo, "my-change: opts svc.yaml into forward enforcement")

    result, touched = _run_change_scope(repo, "my-change")
    assert result.exit_code == 1
    assert any("op1" in f for f in result.forward_failures)
    # NOT reported as merely pre-existing/untouched
    assert not any("op1" in r and "pre-existing" in r for r in result.reports)


# ---------------------------------------------------------------------------
# opting a capability in touches every requirement of it
# ---------------------------------------------------------------------------


def test_opting_a_capability_in_touches_every_requirement_of_it(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    write_spec(repo / "specs", "widget", ["Alpha", "Beta"])
    # No exclusions file yet — reverse not opted in.
    commit_all(repo, "base: no reverse enforcement")
    checkout_branch(repo, "feature")

    write_delta(repo / "changes", "my-change", "widget", added=[])
    write_exclusions(repo / "contracts", "widget", [])  # newly added, empty
    commit_all(repo, "my-change: opts widget into reverse enforcement")

    result, touched = _run_change_scope(repo, "my-change")
    assert result.exit_code == 1
    assert any("widget.alpha" in f for f in result.reverse_failures)
    assert any("widget.beta" in f for f in result.reverse_failures)


# ---------------------------------------------------------------------------
# an unresolvable merge base is an error, not an empty scope
# ---------------------------------------------------------------------------


def test_unresolvable_merge_base_is_an_error(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    write_spec(repo / "specs", "widget", ["Alpha"])
    commit_all(repo, "base")

    result, touched = _run_change_scope(repo, "my-change", base_ref="does-not-exist")
    assert result.exit_code == 1
    assert any("merge base" in e for e in result.errors)
    assert touched is None


def test_missing_change_id_is_an_error(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    commit_all(repo, "base")
    result, touched = gate.run_gate(
        contracts_root=repo / "contracts",
        specs_root=repo / "specs",
        changes_root=repo / "changes",
        repo_root=repo,
        scope="change",
        change_id=None,
    )
    assert result.exit_code == 1
    assert any("--change" in e for e in result.errors)


# ---------------------------------------------------------------------------
# the output states which scope it evaluated
# ---------------------------------------------------------------------------


def test_output_states_the_scope_it_evaluated(tmp_path: Path) -> None:
    repo = _base_repo(tmp_path)
    write_spec(repo / "specs", "widget", ["Alpha"])
    commit_all(repo, "base")
    checkout_branch(repo, "feature")
    write_delta(repo / "changes", "my-change", "widget", added=[])
    commit_all(repo, "my-change: no-op")

    result, _touched = _run_change_scope(repo, "my-change")
    text = gate._format_report(result, scope="change", change_id="my-change")
    assert (
        "scope: change (my-change) — touched operations and requirements only; "
        "capability completeness not evaluated" in text
    )
    assert "traceability complete" not in text
