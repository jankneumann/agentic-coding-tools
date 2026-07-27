"""Durable convergence identity and two-source idempotence (ri-11 D4).

The convergence operation is keyed on ``(repository_id, merged_main_sha)`` so a
retry after a crash resolves the *same* operation rather than minting a new one.
Everything below pins that, plus the property the roadmap actually cares about:
a retry must not produce a second convergence commit, a second archive, or a
second index request.

Idempotence rests on two independent checks because each has a hole the other
covers:

* the terminal ri-06 operation record lives in the Git *common* dir, so it is
  lost on a fresh clone;
* the ``Context-Refresh-Operation:`` commit trailer travels with history, but
  does not exist until the convergence commit lands.

Either alone is sufficient to conclude "already converged". Neither alone is
sufficient as the *only* check, so a run that cannot consult both and found
nothing must report an inconclusive result rather than "no prior convergence" --
this roadmap exists because checks reported green for work never done.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SUITE_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SUITE_DIR.parents[1]
for _extra in (
    _SKILLS_DIR / "merge-pull-requests" / "scripts",
    _SKILLS_DIR / "project-context-runtime" / "scripts",
    _SKILLS_DIR / "shared",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import main_convergence as mc  # noqa: E402
from models import OperationState, derive_operation_id  # noqa: E402
from store import OperationStore  # noqa: E402

MERGED_SHA = "a" * 40
OTHER_SHA = "b" * 40


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Convergence Test",
            "-c",
            "user.email=convergence@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "convergence-repo"
    root.mkdir()
    _git(root, "init", "--initial-branch=main")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "seed")
    return root


@pytest.fixture()
def store(tmp_path: Path) -> OperationStore:
    return OperationStore(tmp_path, base_dir=tmp_path / "ledger")


def _terminal_record(store: OperationStore, identity, outcome: OperationState) -> None:
    store.create_or_load(identity.repository_id, identity.merged_revision)
    store.begin_attempt(identity.operation_id)
    store.finalize(
        identity.operation_id,
        outcome,
        error=None
        if outcome is not OperationState.FAILED
        else __import__("models").SafeError(error_class="X", summary="boom"),
    )


# --------------------------------------------------------------------------- #
# Identity (task 3.1)
# --------------------------------------------------------------------------- #
def test_identity_is_the_ri06_derivation_for_the_merged_sha(repo: Path) -> None:
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)

    assert identity.merged_revision == MERGED_SHA
    assert identity.operation_id == derive_operation_id(identity.repository_id, MERGED_SHA)
    assert identity.operation_id.startswith("pcr-")


def test_identity_is_stable_across_retries(repo: Path) -> None:
    first = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    second = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)

    assert first == second


def test_identity_differs_when_the_merged_sha_differs(repo: Path) -> None:
    first = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    second = mc.derive_convergence_identity(repo, merged_revision=OTHER_SHA)

    assert first.operation_id != second.operation_id


def test_repository_id_matches_the_refresh_orchestrator_rule(repo: Path) -> None:
    """A split repository_id would split the ledger and hide prior convergence."""
    default = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA, environ={})
    assert default.repository_id == repo.name

    overridden = mc.derive_convergence_identity(
        repo, merged_revision=MERGED_SHA, environ={"PROJECT_CONTEXT_REPO_ID": "pinned-id"}
    )
    assert overridden.repository_id == "pinned-id"
    assert overridden.operation_id == derive_operation_id("pinned-id", MERGED_SHA)


def test_identity_reads_head_when_no_revision_is_supplied(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    identity = mc.derive_convergence_identity(repo)

    assert identity.merged_revision == head


def test_identity_refuses_a_revision_that_is_not_a_full_sha(repo: Path) -> None:
    with pytest.raises(Exception):
        mc.derive_convergence_identity(repo, merged_revision="HEAD")


# --------------------------------------------------------------------------- #
# Two-source idempotence (task 3.2)
# --------------------------------------------------------------------------- #
def test_terminal_operation_record_alone_is_sufficient(repo: Path, store: OperationStore) -> None:
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    _terminal_record(store, identity, OperationState.SUCCEEDED)

    prior = mc.find_prior_convergence(repo, identity, store=store)

    assert prior.found is True
    assert mc.SOURCE_OPERATION_RECORD in prior.sources
    assert mc.SOURCE_COMMIT_TRAILER not in prior.sources


def test_commit_trailer_alone_is_sufficient(repo: Path, store: OperationStore) -> None:
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    (repo / "converged.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "converged.txt")
    _git(
        repo,
        "commit",
        "-m",
        f"chore(context): converge main\n\n{mc.CONVERGENCE_TRAILER}: {identity.operation_id}",
    )
    expected = _git(repo, "rev-parse", "HEAD")

    prior = mc.find_prior_convergence(repo, identity, store=store)

    assert prior.found is True
    assert mc.SOURCE_COMMIT_TRAILER in prior.sources
    assert mc.SOURCE_OPERATION_RECORD not in prior.sources
    assert prior.convergence_commit == expected


def test_neither_source_means_not_converged_and_conclusive(
    repo: Path, store: OperationStore
) -> None:
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)

    prior = mc.find_prior_convergence(repo, identity, store=store)

    assert prior.found is False
    assert prior.unreadable == ()
    assert prior.conclusive is True


def test_a_trailer_for_a_different_operation_does_not_count(
    repo: Path, store: OperationStore
) -> None:
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    other = mc.derive_convergence_identity(repo, merged_revision=OTHER_SHA)
    (repo / "other.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "other.txt")
    _git(
        repo,
        "commit",
        "-m",
        f"chore(context): converge main\n\n{mc.CONVERGENCE_TRAILER}: {other.operation_id}",
    )

    prior = mc.find_prior_convergence(repo, identity, store=store)

    assert prior.found is False


def test_a_failed_operation_is_resumable_not_converged(
    repo: Path, store: OperationStore
) -> None:
    """D6 leaves a failed convergence resumable; treating it as done would strand it."""
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    _terminal_record(store, identity, OperationState.FAILED)

    prior = mc.find_prior_convergence(repo, identity, store=store)

    assert prior.found is False


def test_a_degraded_operation_counts_as_converged(repo: Path, store: OperationStore) -> None:
    """Degraded is the NORMAL outcome for a deferred index; it still committed."""
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    _terminal_record(store, identity, OperationState.DEGRADED)

    prior = mc.find_prior_convergence(repo, identity, store=store)

    assert prior.found is True


def test_both_sources_unreadable_is_inconclusive_never_silent_success(
    repo: Path, tmp_path: Path
) -> None:
    """Unknown state is not 'no prior convergence'. Never fail open."""
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)

    def _exploding_runner(argv, cwd):  # noqa: ANN001, ARG001
        raise OSError("git is unavailable")

    class _ExplodingStore:
        def load(self, operation_id: str):  # noqa: ANN201, ARG002
            raise OSError("ledger is unreadable")

    prior = mc.find_prior_convergence(
        repo, identity, store=_ExplodingStore(), runner=_exploding_runner
    )

    assert prior.found is False
    assert prior.conclusive is False
    assert set(prior.unreadable) == {mc.SOURCE_OPERATION_RECORD, mc.SOURCE_COMMIT_TRAILER}


def test_one_unreadable_source_with_the_other_positive_is_still_conclusive(
    repo: Path, store: OperationStore
) -> None:
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    _terminal_record(store, identity, OperationState.SUCCEEDED)

    def _exploding_runner(argv, cwd):  # noqa: ANN001, ARG001
        raise OSError("git is unavailable")

    prior = mc.find_prior_convergence(repo, identity, store=store, runner=_exploding_runner)

    assert prior.found is True
    assert prior.conclusive is True


def test_trailer_lookup_is_not_confused_by_the_id_appearing_in_prose(
    repo: Path, store: OperationStore
) -> None:
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    (repo / "notes.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    _git(
        repo,
        "commit",
        "-m",
        f"docs: mention {identity.operation_id} in passing without converging",
    )

    prior = mc.find_prior_convergence(repo, identity, store=store)

    assert prior.found is False


def test_environ_default_reads_the_process_environment(repo: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("PROJECT_CONTEXT_REPO_ID", "from-process-env")
    identity = mc.derive_convergence_identity(repo, merged_revision=MERGED_SHA)
    assert identity.repository_id == "from-process-env"
    assert os.environ["PROJECT_CONTEXT_REPO_ID"] == "from-process-env"
