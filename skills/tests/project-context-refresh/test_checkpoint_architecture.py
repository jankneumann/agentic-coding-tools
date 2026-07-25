"""Architecture coverage in the checkpoint report (ri-09 tasks 3.7-3.8).

Spec scenarios: pcro "Stale architecture artifact yields a labelled delta",
pcro "Fresh architecture artifact yields an authoritative delta". Design
decision: D6 — freshness and delta answer different questions and can disagree,
so they are reported as two findings and a delta computed from a non-fresh
artifact is never presented as authoritative.

Freshness is provenance-based (``arch_utils.provenance.check_freshness``, the
function ``run_architecture.py --check`` delegates to) and therefore
mtime-independent. The delta is a graph diff against the *committed* merge-base
graph, read out of git rather than off the working tree.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

import checkpoint
from _runtime import ProducerResult, ProducerStatus

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKPOINT_SCHEMA = (
    _REPO_ROOT
    / "skills"
    / "project-context-refresh"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "context-checkpoint.schema.json"
)
_TYPES_SCHEMA = (
    _REPO_ROOT
    / "skills"
    / "project-context-runtime"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "context-refresh-types.schema.json"
)

CHANGE_ID = "add-branch-local-context-checkpoints"
PACKAGE_ID = "wp-checkpoint"
CHANGED_FILES = ("docs/architecture-analysis/architecture.graph.json",)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _rules() -> Any:
    from context_impact import ImpactRules

    return ImpactRules(
        surface_globs={"architecture": ("docs/architecture-analysis/**",)},
        source=Path("test-rules.yaml"),
    )


def _package() -> dict[str, Any]:
    return {
        "package_id": PACKAGE_ID,
        "scope": {
            "read_allow": ["docs/**"],
            "write_allow": ["docs/**"],
            "deny": [],
        },
        "context_impact": {"surfaces": ["architecture"]},
    }


def _fresh_producer(producer_id: str, mode: str, repository: Path, revision: str):
    return ProducerResult(
        producer_id=producer_id,
        producer_version="1.0.0",
        status=ProducerStatus.FRESH,
    )


def _graph(*node_ids: str) -> dict[str, Any]:
    return {
        "nodes": [{"id": nid, "name": nid, "kind": "module"} for nid in node_ids],
        "edges": [],
        "entrypoints": [],
        "snapshots": [],
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo_with_two_graph_revisions(tmp_path: Path) -> tuple[Path, str, str]:
    """Commit graph v1, then graph v2; return ``(root, baseline_sha, head_sha)``."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        _git(tmp_path, "config", key, value)

    graph_path = tmp_path / checkpoint.ARCHITECTURE_GRAPH_PATH
    graph_path.parent.mkdir(parents=True, exist_ok=True)

    graph_path.write_text(json.dumps(_graph("mod.a", "mod.b")), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "baseline graph")
    baseline = _git(tmp_path, "rev-parse", "HEAD")

    graph_path.write_text(json.dumps(_graph("mod.b", "mod.c")), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "branch graph")
    head = _git(tmp_path, "rev-parse", "HEAD")
    return tmp_path, baseline, head


def _validator() -> Draft202012Validator:
    schema = json.loads(_CHECKPOINT_SCHEMA.read_text(encoding="utf-8"))
    types = json.loads(_TYPES_SCHEMA.read_text(encoding="utf-8"))
    registry = Registry().with_resources(
        [
            (doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
            for doc in (schema, types)
        ]
    )
    return Draft202012Validator(schema, registry=registry)


def _run(repo: Path, revision: str, **kwargs: Any) -> Any:
    return checkpoint.run_checkpoint(
        repo,
        change_id=CHANGE_ID,
        package_id=PACKAGE_ID,
        package=_package(),
        changed_files=CHANGED_FILES,
        revision=revision,
        rules=_rules(),
        producer_ids=("documentation.inventory",),
        producer_runner=_fresh_producer,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# D6 — authority is derived, never asserted
# --------------------------------------------------------------------------- #
class TestArchitectureFinding:
    def test_a_fresh_artifact_may_carry_an_authoritative_delta(self) -> None:
        finding = checkpoint.ArchitectureFinding(
            freshness="fresh", changed_nodes=("mod.a",)
        )
        assert finding.delta_authoritative is True

    @pytest.mark.parametrize("freshness", ["stale", "unknown"])
    def test_a_non_fresh_artifact_can_never_claim_authority(self, freshness: str) -> None:
        finding = checkpoint.ArchitectureFinding(
            freshness=freshness, changed_nodes=("mod.a", "mod.c")
        )
        assert finding.delta_authoritative is False
        # The delta is still reported: it is evidence, just not authoritative.
        assert finding.changed_nodes == ("mod.a", "mod.c")

    def test_authority_cannot_be_supplied_by_a_caller(self) -> None:
        """The one value that must never be wrong is the one nobody can set."""
        with pytest.raises(TypeError):
            checkpoint.ArchitectureFinding(  # type: ignore[call-arg]
                freshness="stale", delta_authoritative=True
            )

    def test_changed_nodes_are_deduplicated_and_sorted(self) -> None:
        finding = checkpoint.ArchitectureFinding(
            freshness="fresh", changed_nodes=("z", "a", "z")
        )
        assert finding.changed_nodes == ("a", "z")

    def test_an_unknown_freshness_value_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="freshness"):
            checkpoint.ArchitectureFinding(freshness="probably-fine")


# --------------------------------------------------------------------------- #
# Freshness — provenance-based, mtime-independent
# --------------------------------------------------------------------------- #
class TestFreshness:
    def test_missing_provenance_is_unknown_not_stale(self, tmp_path: Path) -> None:
        # ri-04 calls this 'invalid'. We cannot assert the artifact is stale,
        # only that we cannot vouch for it, so it must not masquerade as stale.
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        assert checkpoint.architecture_freshness(tmp_path) == "unknown"

    @pytest.mark.parametrize(
        ("status", "expected"),
        [("fresh", "fresh"), ("stale", "stale"), ("invalid", "unknown")],
    )
    def test_ri04_status_is_mapped_faithfully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, expected: str
    ) -> None:
        assert checkpoint._ensure_architecture_on_path()
        from arch_utils import provenance  # type: ignore[import-not-found]

        monkeypatch.setattr(
            provenance,
            "check_freshness",
            lambda *a, **k: provenance.CheckResult(status),
        )
        assert checkpoint.architecture_freshness(tmp_path) == expected

    def test_a_raising_owner_degrades_to_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert checkpoint._ensure_architecture_on_path()
        from arch_utils import provenance  # type: ignore[import-not-found]

        def explode(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("provenance backend unavailable")

        monkeypatch.setattr(provenance, "check_freshness", explode)
        assert checkpoint.architecture_freshness(tmp_path) == "unknown"


# --------------------------------------------------------------------------- #
# Delta — a graph diff against the committed merge base
# --------------------------------------------------------------------------- #
class TestDelta:
    def test_added_and_removed_nodes_are_reported_against_the_merge_base(
        self, tmp_path: Path
    ) -> None:
        repo, baseline, _head = _repo_with_two_graph_revisions(tmp_path)
        assert checkpoint.architecture_changed_nodes(repo, baseline) == (
            "mod.a",
            "mod.c",
        )

    def test_no_merge_base_yields_an_empty_delta(self, tmp_path: Path) -> None:
        repo, _baseline, _head = _repo_with_two_graph_revisions(tmp_path)
        assert checkpoint.architecture_changed_nodes(repo, None) == ()

    def test_a_baseline_without_the_graph_yields_an_empty_delta(
        self, tmp_path: Path
    ) -> None:
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
            _git(tmp_path, "config", key, value)
        (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", "no graph")
        baseline = _git(tmp_path, "rev-parse", "HEAD")

        graph_path = tmp_path / checkpoint.ARCHITECTURE_GRAPH_PATH
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(json.dumps(_graph("mod.a")), encoding="utf-8")

        assert checkpoint.architecture_changed_nodes(tmp_path, baseline) == ()

    def test_a_missing_current_graph_yields_an_empty_delta(self, tmp_path: Path) -> None:
        repo, baseline, _head = _repo_with_two_graph_revisions(tmp_path)
        (repo / checkpoint.ARCHITECTURE_GRAPH_PATH).unlink()
        assert checkpoint.architecture_changed_nodes(repo, baseline) == ()

    def test_an_unparseable_graph_yields_an_empty_delta(self, tmp_path: Path) -> None:
        repo, baseline, _head = _repo_with_two_graph_revisions(tmp_path)
        (repo / checkpoint.ARCHITECTURE_GRAPH_PATH).write_text("{ not json", encoding="utf-8")
        assert checkpoint.architecture_changed_nodes(repo, baseline) == ()

    def test_merge_base_resolution_returns_a_full_sha_or_none(
        self, tmp_path: Path
    ) -> None:
        repo, baseline, _head = _repo_with_two_graph_revisions(tmp_path)
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        assert checkpoint.resolve_merge_base(repo, integration_branch=branch) == _git(
            repo, "rev-parse", "HEAD"
        )
        assert (
            checkpoint.resolve_merge_base(repo, integration_branch="no-such-branch")
            is None
        )
        assert baseline  # the fixture really produced two revisions


# --------------------------------------------------------------------------- #
# The report carries both findings, separately
# --------------------------------------------------------------------------- #
class TestReportedArchitecture:
    def test_a_stale_artifact_yields_a_labelled_delta(self, tmp_path: Path) -> None:
        repo, baseline, head = _repo_with_two_graph_revisions(tmp_path)
        result = _run(
            repo,
            head,
            merge_base=baseline,
            architecture=lambda repository, merge_base: checkpoint.ArchitectureFinding(
                freshness="stale",
                changed_nodes=checkpoint.architecture_changed_nodes(
                    repository, merge_base
                ),
            ),
        )
        architecture = result.report["architecture"]

        assert architecture["freshness"] == "stale"
        assert architecture["delta_authoritative"] is False
        # D6: the delta survives the staleness label rather than being suppressed.
        assert architecture["changed_nodes"] == ["mod.a", "mod.c"]
        assert result.report["merge_base_revision"] == baseline
        assert _errors(result.report) == []

    def test_a_fresh_artifact_yields_an_authoritative_changed_node_list(
        self, tmp_path: Path
    ) -> None:
        repo, baseline, head = _repo_with_two_graph_revisions(tmp_path)
        result = _run(
            repo,
            head,
            merge_base=baseline,
            architecture=lambda repository, merge_base: checkpoint.ArchitectureFinding(
                freshness="fresh",
                changed_nodes=checkpoint.architecture_changed_nodes(
                    repository, merge_base
                ),
            ),
        )
        architecture = result.report["architecture"]

        assert architecture["freshness"] == "fresh"
        assert architecture["delta_authoritative"] is True
        assert architecture["changed_nodes"] == ["mod.a", "mod.c"]
        assert _errors(result.report) == []

    def test_the_default_resolver_is_used_when_none_is_injected(
        self, tmp_path: Path
    ) -> None:
        repo, baseline, head = _repo_with_two_graph_revisions(tmp_path)
        result = _run(repo, head, merge_base=baseline)
        architecture = result.report["architecture"]

        # No provenance in the fixture, so freshness is unknown — and that is
        # exactly the case where the (real, non-empty) delta must be labelled.
        assert architecture["freshness"] == "unknown"
        assert architecture["delta_authoritative"] is False
        assert architecture["changed_nodes"] == ["mod.a", "mod.c"]

    def test_a_raising_resolver_degrades_the_finding_not_the_checkpoint(
        self, tmp_path: Path
    ) -> None:
        repo, _baseline, head = _repo_with_two_graph_revisions(tmp_path)

        def explode(repository: Path, merge_base: str | None) -> Any:
            raise RuntimeError("architecture analysis crashed")

        result = _run(repo, head, architecture=explode)

        assert result.report["architecture"] == {
            "freshness": "unknown",
            "delta_authoritative": False,
            "changed_nodes": [],
        }
        assert result.exit_code() == 0

    def test_no_merge_base_omits_the_optional_field(self, tmp_path: Path) -> None:
        repo, _baseline, head = _repo_with_two_graph_revisions(tmp_path)
        result = _run(repo, head)

        assert "merge_base_revision" not in result.report
        assert _errors(result.report) == []


def _errors(document: Any) -> list[Any]:
    return sorted(_validator().iter_errors(document), key=lambda e: list(e.absolute_path))
