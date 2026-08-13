"""Architecture freshness fails closed (ri-10 wp-lifecycle task 2.2, design D4).

The pre-ri-10 ``_default_architecture_producer`` called
``provenance.build_provenance(repository, mode="full")`` — which *builds*
provenance from the working tree — and returned ``fresh`` unconditionally. On the
same tree, ``make architecture-check`` reported
``{"status": "invalid", "reasons": [{"code": "PROVENANCE_MISSING"}]}`` and exit 1.

These tests pin the corrected mapping over ``arch_utils.provenance.check_freshness``:

| ``check_freshness`` status            | producer status  |
|---------------------------------------|------------------|
| ``fresh``                             | ``fresh``        |
| ``stale``                             | ``degraded``     |
| ``invalid`` (missing/malformed/schema) | ``degraded``     |
| owner not importable                  | ``not-configured`` |

The third row is the load-bearing one: ``not-configured`` means "optional owner
absent" and by design must not fail the gate, so routing unverifiable evidence
there would reintroduce the fail-open behaviour through the classifier instead of
the producer. Absent tooling degrades; unverifiable evidence blocks.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import orchestrator
from _runtime import ProducerStatus, ValidationStatus

FULL_SHA_PLACEHOLDER = "c" * 40

_ARCH_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "refresh-architecture" / "scripts"
)
if str(_ARCH_SCRIPTS) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(_ARCH_SCRIPTS))

from arch_utils import provenance as arch_provenance  # noqa: E402

ARCH_DIR = arch_provenance.ARCH_DIR_DEFAULT
PROVENANCE_REL = f"{ARCH_DIR}/{arch_provenance.PROVENANCE_FILENAME}"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def arch_repo(tmp_path: Path) -> tuple[Path, str]:
    """A committed checkout carrying architecture artifacts but no provenance."""
    repo = tmp_path / "repo"
    (repo / ARCH_DIR).mkdir(parents=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        _git(repo, "config", key, value)

    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / ARCH_DIR / "architecture.graph.json").write_text(
        json.dumps({"nodes": []}, indent=2) + "\n", encoding="utf-8"
    )
    (repo / ARCH_DIR / "architecture.summary.json").write_text(
        json.dumps({"summary": "fixture"}, indent=2) + "\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo, _git(repo, "rev-parse", "HEAD")


def _commit_fresh_provenance(repo: Path) -> dict[str, object]:
    """Write and commit provenance that ``check_freshness`` will call ``fresh``."""
    doc = arch_provenance.build_provenance(repo, mode="full")
    arch_provenance.write_provenance(repo, doc)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "provenance")
    return doc


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digests(repo: Path) -> dict[str, str]:
    return {
        p.relative_to(repo).as_posix(): _digest(p)
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git/" not in p.relative_to(repo).as_posix()
    }


def _run(repo: Path, revision: str, mode: str = "check"):
    return orchestrator._default_architecture_producer(repo, revision, mode)  # type: ignore[arg-type]


def _codes(result) -> set[str]:  # noqa: ANN001
    """Drift reason codes surfaced through the result's validations."""
    return {
        code
        for validation in result.validations
        for code in _known_codes()
        if code in validation.summary or code in validation.validation_id
    }


def _known_codes() -> tuple[str, ...]:
    return (
        arch_provenance.PROVENANCE_MISSING,
        arch_provenance.PROVENANCE_INVALID,
        arch_provenance.INPUT_FINGERPRINT_MISMATCH,
        arch_provenance.PRODUCER_IDENTITY_MISMATCH,
        arch_provenance.ARTIFACT_DIGEST_MISMATCH,
        arch_provenance.ARTIFACT_MISSING,
    )


# --------------------------------------------------------------------------- #
# Unverifiable provenance blocks (drift, never not-configured)
# --------------------------------------------------------------------------- #
class TestUnverifiableProvenanceBlocks:
    def test_missing_provenance_is_drift(self, arch_repo: tuple[Path, str]) -> None:
        repo, head = arch_repo
        assert not (repo / PROVENANCE_REL).exists()

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED
        assert result.status is not ProducerStatus.NOT_CONFIGURED
        assert result.status is not ProducerStatus.FRESH

    def test_missing_provenance_names_the_reason_code(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        repo, head = arch_repo
        result = _run(repo, head)
        assert arch_provenance.PROVENANCE_MISSING in _codes(result)

    def test_malformed_provenance_is_drift(self, arch_repo: tuple[Path, str]) -> None:
        repo, head = arch_repo
        (repo / PROVENANCE_REL).write_text("{ not json", encoding="utf-8")

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED

    def test_schema_invalid_provenance_is_drift(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        repo, head = arch_repo
        # Valid JSON, structurally wrong: no producer, no artifacts, no fingerprint.
        (repo / PROVENANCE_REL).write_text(
            json.dumps({"schema_version": 1}, indent=2) + "\n", encoding="utf-8"
        )

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED
        assert _codes(result) & {
            arch_provenance.PROVENANCE_INVALID,
            arch_provenance.PROVENANCE_MISSING,
        }

    def test_a_non_fresh_result_carries_remediation_and_a_fallback(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        """ri-06 rejects a non-fresh result missing either; the drift path must not raise."""
        repo, head = arch_repo
        result = _run(repo, head)
        assert result.remediation
        assert result.fallback is not None

    def test_drift_records_a_failed_validation(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        repo, head = arch_repo
        result = _run(repo, head)
        assert any(v.status is ValidationStatus.FAILED for v in result.validations)


# --------------------------------------------------------------------------- #
# Stale provenance blocks
# --------------------------------------------------------------------------- #
class TestStaleProvenanceBlocks:
    def test_a_changed_artifact_is_drift(self, arch_repo: tuple[Path, str]) -> None:
        repo, head = arch_repo
        _commit_fresh_provenance(repo)
        # Committed artifact bytes now differ from the recorded digest.
        (repo / ARCH_DIR / "architecture.graph.json").write_text(
            json.dumps({"nodes": ["changed"]}, indent=2) + "\n", encoding="utf-8"
        )

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED
        assert arch_provenance.ARTIFACT_DIGEST_MISMATCH in _codes(result)

    def test_a_missing_recorded_artifact_is_drift(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        repo, head = arch_repo
        _commit_fresh_provenance(repo)
        (repo / ARCH_DIR / "architecture.summary.json").unlink()

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED
        assert arch_provenance.ARTIFACT_MISSING in _codes(result)

    def test_changed_inputs_are_drift(self, arch_repo: tuple[Path, str]) -> None:
        repo, head = arch_repo
        _commit_fresh_provenance(repo)
        (repo / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED

    def test_stale_drift_names_the_stale_artifact_paths(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        """The gate's precise stale-artifact list comes from these artifacts."""
        repo, head = arch_repo
        _commit_fresh_provenance(repo)
        (repo / ARCH_DIR / "architecture.graph.json").write_text(
            json.dumps({"nodes": ["changed"]}, indent=2) + "\n", encoding="utf-8"
        )

        result = _run(repo, head)

        paths = {a.path for a in result.artifacts}
        assert f"{ARCH_DIR}/architecture.graph.json" in paths

    def test_pathless_input_drift_names_the_provenance_document(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        """INPUT_FINGERPRINT_MISMATCH carries no path; the drifted artifact is
        the provenance document whose recorded fingerprint no longer matches.

        Regression: unnamed drift was reported by the gate as an apparatus
        failure ("drift without naming any artifact"), hiding the
        ``make architecture-refresh`` remediation. Seen on main after commits
        changed input-root files without regenerating provenance.
        """
        repo, head = arch_repo
        _commit_fresh_provenance(repo)
        (repo / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

        result = _run(repo, head)

        assert arch_provenance.INPUT_FINGERPRINT_MISMATCH in _codes(result)
        assert {a.path for a in result.artifacts} == {PROVENANCE_REL}

    def test_pathless_identity_drift_names_the_provenance_document(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        """PRODUCER_IDENTITY_MISMATCH is equally pathless and equally must
        surface a named artifact rather than an empty stale list."""
        repo, head = arch_repo
        doc = _commit_fresh_provenance(repo)
        doc["optional_tools"] = [
            {"name": "tree-sitter", "available": True, "version": "0.0.0-other"}
        ]
        arch_provenance.write_provenance(repo, doc)

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED
        assert arch_provenance.PRODUCER_IDENTITY_MISMATCH in _codes(result)
        assert PROVENANCE_REL in {a.path for a in result.artifacts}

    def test_every_drift_result_names_at_least_one_artifact(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        """The gate-level invariant this producer must uphold: a drift verdict
        with an empty artifact list is unactionable by construction."""
        repo, head = arch_repo
        _commit_fresh_provenance(repo)
        (repo / "src" / "app.py").write_text("VALUE = 3\n", encoding="utf-8")

        result = _run(repo, head)

        assert result.status is ProducerStatus.DEGRADED
        assert result.artifacts


# --------------------------------------------------------------------------- #
# Committed, matching provenance is fresh
# --------------------------------------------------------------------------- #
class TestCommittedProvenanceIsFresh:
    def test_matching_provenance_is_fresh(self, arch_repo: tuple[Path, str]) -> None:
        repo, head = arch_repo
        _commit_fresh_provenance(repo)

        result = _run(repo, head)

        assert result.status is ProducerStatus.FRESH
        assert result.producer_id == orchestrator.ARCHITECTURE_PRODUCER_ID
        assert all(v.status is ValidationStatus.PASSED for v in result.validations)

    def test_fresh_reports_the_recorded_artifacts(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        repo, head = arch_repo
        doc = _commit_fresh_provenance(repo)

        result = _run(repo, head)

        recorded = {a["path"] for a in doc["artifacts"]}  # type: ignore[index]
        assert {a.path for a in result.artifacts} == recorded

    def test_freshness_is_decided_by_check_freshness_not_by_building_provenance(
        self, arch_repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``build_provenance`` reads the working tree, so it can never prove freshness.

        This is the defect in one assertion: with ``build_provenance`` made
        unusable the producer must still reach the correct verdict, because the
        verdict comes from comparing against committed provenance.
        """
        repo, head = arch_repo
        _commit_fresh_provenance(repo)

        def _forbidden(*_args: object, **_kwargs: object) -> object:
            raise AssertionError(
                "the architecture producer must not build provenance from the "
                "working tree; freshness comes from check_freshness"
            )

        monkeypatch.setattr(arch_provenance, "build_provenance", _forbidden)

        result = _run(repo, head)

        assert result.status is ProducerStatus.FRESH

    def test_check_freshness_is_the_seam_the_producer_calls(
        self, arch_repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, head = arch_repo
        calls: list[tuple[object, ...]] = []
        real = arch_provenance.check_freshness

        def _spy(repo_root, *args, **kwargs):  # noqa: ANN001, ANN202
            calls.append((repo_root, args, kwargs))
            return real(repo_root, *args, **kwargs)

        monkeypatch.setattr(arch_provenance, "check_freshness", _spy)

        _run(repo, head)

        assert len(calls) == 1


# --------------------------------------------------------------------------- #
# Absent owner degrades without blocking
# --------------------------------------------------------------------------- #
class TestAbsentOwnerDegrades:
    def test_an_unimportable_owner_is_not_configured(
        self, arch_repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, head = arch_repo
        # A ``None`` entry makes ``from arch_utils import provenance`` raise, which
        # is what an installed runtime without refresh-architecture looks like.
        monkeypatch.setitem(sys.modules, "arch_utils", None)
        monkeypatch.delitem(sys.modules, "arch_utils.provenance", raising=False)

        result = _run(repo, head)

        assert result.status is ProducerStatus.NOT_CONFIGURED
        assert result.fallback is not None
        assert result.remediation

    def test_an_absent_owner_is_distinguishable_from_unverifiable_provenance(
        self, arch_repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of D4: the two conditions must not share a status."""
        repo, head = arch_repo

        unverifiable = _run(repo, head)

        monkeypatch.setitem(sys.modules, "arch_utils", None)
        monkeypatch.delitem(sys.modules, "arch_utils.provenance", raising=False)
        absent = _run(repo, head)

        assert unverifiable.status is not absent.status
        assert absent.status is ProducerStatus.NOT_CONFIGURED
        assert unverifiable.status is ProducerStatus.DEGRADED


# --------------------------------------------------------------------------- #
# The producer never writes
# --------------------------------------------------------------------------- #
class TestProducerIsReadOnly:
    @pytest.mark.parametrize("mode", ["check", "generate"])
    def test_the_producer_leaves_the_checkout_byte_identical(
        self, arch_repo: tuple[Path, str], mode: str
    ) -> None:
        repo, head = arch_repo
        _commit_fresh_provenance(repo)
        before = _tree_digests(repo)

        _run(repo, head, mode)

        assert _tree_digests(repo) == before

    def test_the_producer_does_not_create_provenance_when_it_is_missing(
        self, arch_repo: tuple[Path, str]
    ) -> None:
        repo, head = arch_repo

        _run(repo, head)

        assert not (repo / PROVENANCE_REL).exists()
