"""The convergence identity is directory-derived, and what that costs.

Measured during the ri-11 rehearsal (tasks 6.3/6.4): two clones of the same
repository into differently named directories compute different ``operation_id``
values for the *same* merged revision, so neither finds the other's
``Context-Refresh-Operation`` trailer. The rehearsal saw ``reh1`` produce
``pcr-d1f79f036271c8ff`` while a fresh clone at ``reh2`` computed
``pcr-2ae8ac65e1dee545`` and reported ``prior.found=false`` with the trailer
sitting in ``HEAD``.

The directory-name rule is deliberately *not* changed here: it is ri-04's
canonical ``provenance.repository_id``, inherited byte-for-byte by ri-07's
``resolve_repository_identity`` so the ledger cannot split *within* one clone.
Changing it would alter every committed ``architecture.provenance.json`` and make
ri-10's drift gate report a producer-identity mismatch repository-wide.

So these tests pin the behaviour and its escape hatch rather than asserting a fix
that does not exist. If someone later makes the identity intrinsically portable
(a normalized origin URL, or the root-commit SHA), the first test here is the one
that should be rewritten — deliberately, not by accident.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "skills" / "merge-pull-requests" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import main_convergence as mc  # noqa: E402

_REVISION = "2cfaccf59c78940360ef07415dceea012a1d4217"


def _no_git(argv, cwd=None):
    """A runner reporting no git toplevel, so the path basename is used.

    Returns the driver's own ``CommandResult`` rather than a stand-in, so the
    fixture cannot drift from the ``ok`` contract the caller relies on.
    """
    return mc.CommandResult(argv=tuple(argv), returncode=1)


def test_the_same_revision_in_two_clone_paths_yields_two_operation_ids() -> None:
    """The known limitation, pinned so a future fix is a deliberate change."""
    left = mc.derive_convergence_identity(
        "/tmp/clone-a", merged_revision=_REVISION, environ={}, runner=_no_git
    )
    right = mc.derive_convergence_identity(
        "/tmp/clone-b", merged_revision=_REVISION, environ={}, runner=_no_git
    )
    assert left.merged_revision == right.merged_revision
    assert left.operation_id != right.operation_id, (
        "The operation id is now stable across clone paths. That is an "
        "improvement, but it must be made deliberately and together with ri-04's "
        "provenance.repository_id and ri-07's resolve_repository_identity, or the "
        "ledger splits within a clone and ri-10's drift gate reports a "
        "producer-identity mismatch repository-wide. Update this test with that "
        "change, not ahead of it."
    )


def test_project_context_repo_id_makes_the_identity_clone_independent() -> None:
    """The documented escape hatch actually closes the hole."""
    env = {"PROJECT_CONTEXT_REPO_ID": "agentic-coding-tools"}
    left = mc.derive_convergence_identity(
        "/tmp/clone-a", merged_revision=_REVISION, environ=env, runner=_no_git
    )
    right = mc.derive_convergence_identity(
        "/tmp/clone-b", merged_revision=_REVISION, environ=env, runner=_no_git
    )
    assert left.operation_id == right.operation_id, (
        "PROJECT_CONTEXT_REPO_ID no longer makes the convergence identity "
        "clone-independent. Step 11.6 tells operators to set it for exactly this "
        "reason, so the instruction would now be wrong."
    )
    assert left.repository_id == "agentic-coding-tools"


def test_the_override_is_read_from_the_same_variable_the_orchestrator_uses() -> None:
    """One value must configure both, or they disagree inside one clone."""
    source = Path(mc.__file__).read_text(encoding="utf-8")
    assert "PROJECT_CONTEXT_REPO_ID" in source, (
        "The driver no longer honors PROJECT_CONTEXT_REPO_ID, so it and the ri-07 "
        "orchestrator would derive different repository ids from the same "
        "environment -- splitting the ledger inside a single clone, which is the "
        "failure resolve_repository_id's docstring exists to prevent."
    )
    orchestrator = (
        _REPO_ROOT
        / "skills"
        / "project-context-refresh"
        / "scripts"
        / "orchestrator.py"
    ).read_text(encoding="utf-8")
    assert "PROJECT_CONTEXT_REPO_ID" in orchestrator, (
        "ri-07's orchestrator no longer honors the variable that Step 11.6 tells "
        "operators to set."
    )
