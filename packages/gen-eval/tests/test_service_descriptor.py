"""Service-descriptor derivation from an OpenAPI contract (task 2.1).

Spec scenarios:
  - gen-eval-framework.contract-as-descriptor-source-of-truth
      · descriptor derives from a contract
      · unreachable implementation does not shrink the declared surface
  - gen-eval-framework.operation-and-surface-coverage-model
      · a surface that does not expose an operation is not a gap
      · one surface element serving two operations is covered once

Design decisions: D1 (contract is the source), D4 (coverage is keyed on
operation × surface), D7 (the projection is mechanical but not total).

The fail-closed case is the one that distinguishes this design from the
rejected alternative. Populating the declared surface by introspecting a
running implementation looks equivalent right up to the moment the
implementation is broken — at which point the declared set shrinks to match
whatever still answers, ``unevaluated_interfaces`` empties out, and the
report claims full coverage of nothing. So the surface derived with every
outbound call sabotaged must be *identical*, not merely non-empty.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from gen_eval.service_descriptor import ServiceDescriptor

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
CHANGE_ID = "derive-descriptors-from-contracts"
FIXTURE_REL = Path("contracts") / "openapi" / "v1.yaml"


def _fixture_path() -> Path:
    """Locate the service-contract fixture, before or after change archival.

    ``openspec/changes/<id>/`` becomes ``openspec/changes/archive/<date>-<id>/``
    when the change lands, so a test pinned to the live path passes today and
    raises ``FileNotFoundError`` later. Resolving both locations keeps the one
    authored copy authoritative without duplicating it into the package.
    """
    live = REPO_ROOT / "openspec" / "changes" / CHANGE_ID / FIXTURE_REL
    if live.is_file():
        return live
    archive = REPO_ROOT / "openspec" / "changes" / "archive"
    for candidate in sorted(archive.glob(f"*-{CHANGE_ID}")):
        if (candidate / FIXTURE_REL).is_file():
            return candidate / FIXTURE_REL
    pytest.fail(f"service-contract fixture not found — task 1.10 authors it at {FIXTURE_REL}")


CONTRACT_PATH = _fixture_path()


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def contract_operation_ids(contract: dict[str, Any]) -> set[str]:
    """Read operation ids straight from the document, not from the model."""
    return {
        operation["operationId"]
        for item in contract["paths"].values()
        for operation in item.values()
    }


def write_contract(tmp_path: Path, contract: dict[str, Any]) -> Path:
    path = tmp_path / "openapi.yaml"
    path.write_text(yaml.safe_dump(contract, sort_keys=False))
    return path


MINIMAL_CONTRACT: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "minimal", "version": "1.0.0"},
    "paths": {
        "/things": {
            "get": {
                "operationId": "list_things",
                "summary": "List things.",
                "x-gen-eval-surface": {
                    "http": {"exposed": True, "element": "GET /things"},
                    "mcp": {"exposed": True, "element": "list_things"},
                },
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}


# ---------------------------------------------------------------------------
# D1 — operations come from the contract
# ---------------------------------------------------------------------------


class TestOperationExtraction:
    def test_every_operation_is_extracted(self) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert {op.operation_id for op in descriptor.operations} == contract_operation_ids(
            load_contract()
        )

    def test_the_surface_is_not_empty(self) -> None:
        """Guards every equality here against a both-sides-empty pass."""
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert len(descriptor.operations) >= 5

    def test_method_and_path_are_captured(self) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        acquire = descriptor.operation("acquire_lock")
        assert acquire.method == "POST"
        assert acquire.path == "/locks/acquire"

    def test_path_templating_is_preserved(self) -> None:
        """``{path}`` is part of the identifier; collapsing it merges operations."""
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.operation("get_lock_status").path == "/locks/status/{path}"

    def test_summary_is_carried(self) -> None:
        """Agent-readable and load-bearing (D7) — an agent reads it to decide."""
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.operation("reap_expired_locks").summary.strip()

    def test_an_operation_without_an_operation_id_is_rejected(self, tmp_path: Path) -> None:
        """Fail closed: a nameless operation cannot be a coverage key.

        Skipping it silently would shrink the declared surface, which is the
        failure mode this whole design exists to prevent — arriving through
        the contract rather than through introspection.
        """
        contract = {
            "openapi": "3.1.0",
            "info": {"title": "t", "version": "1"},
            "paths": {"/x": {"get": {"responses": {"200": {"description": "ok"}}}}},
        }
        with pytest.raises(ValueError, match="operationId"):
            ServiceDescriptor.from_contract(write_contract(tmp_path, contract))


# ---------------------------------------------------------------------------
# D4 — exposure is recorded per surface, separately from coverage
# ---------------------------------------------------------------------------


class TestSurfaceExposure:
    def test_exposed_surfaces_name_their_element(self) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        acquire = descriptor.operation("acquire_lock")
        assert acquire.surfaces["mcp"].exposed is True
        assert acquire.surfaces["mcp"].element == "acquire_lock"
        assert acquire.surfaces["cli"].element == "lock acquire"

    def test_an_unexposed_surface_is_recorded_with_its_reason(self) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        release = descriptor.operation("release_lock")
        assert release.surfaces["cli"].exposed is False
        assert release.surfaces["cli"].reason

    def test_an_unexposed_surface_contributes_no_declared_interface(self) -> None:
        """ "Not exposed" is not "not covered" — it must not become a gap."""
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        surface = descriptor.all_interfaces()
        assert "cli:lock release" not in surface
        assert not [i for i in surface if i.startswith("mcp:reap")]

    def test_an_operation_exposed_nowhere_but_http_still_declares_http(self) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert "POST /locks/reap" in descriptor.all_interfaces()


class TestDeclaredSurface:
    def test_one_element_serving_two_operations_is_declared_once(self) -> None:
        """``check_locks`` serves list_active_locks and get_lock_status (D7).

        Deriving one name per operation invents a tool that does not exist,
        and then subset verification reports it as an omission.
        """
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        surface = descriptor.all_interfaces()
        assert surface.count("mcp:check_locks") == 1

    def test_the_declared_surface_has_no_duplicates(self) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        surface = descriptor.all_interfaces()
        assert len(surface) == len(set(surface))

    def test_identifiers_use_the_contract_element_names(self) -> None:
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        surface = set(descriptor.all_interfaces())
        assert {"GET /locks/active", "mcp:acquire_lock", "cli:lock status"} <= surface

    def test_the_coverage_unit_is_the_operation_not_the_interface(self) -> None:
        """D3's table: a service's coverage unit is the operation.

        The two numbers differ here (one operation spans up to three surface
        elements), which is what makes the distinction checkable at all.
        """
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.coverage_unit_count() == len(descriptor.operations)
        assert descriptor.coverage_unit_count() != len(descriptor.all_interfaces())


# ---------------------------------------------------------------------------
# D1 — the fail-closed direction
# ---------------------------------------------------------------------------


class TestUnreachableImplementationDoesNotShrinkTheSurface:
    def test_surface_is_identical_with_every_outbound_call_sabotaged(self) -> None:
        reachable = ServiceDescriptor.from_contract(CONTRACT_PATH)

        with (
            patch.object(urllib.request, "urlopen", side_effect=AssertionError("urlopen called")),
            patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run called")),
            patch.object(subprocess, "Popen", side_effect=AssertionError("Popen called")),
        ):
            unreachable = ServiceDescriptor.from_contract(CONTRACT_PATH)

        assert unreachable.all_interfaces() == reachable.all_interfaces()
        assert [op.operation_id for op in unreachable.operations] == [
            op.operation_id for op in reachable.operations
        ]

    def test_a_base_url_that_answers_nothing_changes_nothing(self, tmp_path: Path) -> None:
        """The descriptor may know where the service lives; it must not ask."""
        with_url = ServiceDescriptor.from_contract(CONTRACT_PATH, base_url="http://127.0.0.1:9/")
        without = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert with_url.all_interfaces() == without.all_interfaces()


# ---------------------------------------------------------------------------
# Archetype
# ---------------------------------------------------------------------------


class TestArchetype:
    def test_it_is_the_document_level_not_the_service_container(self) -> None:
        """``ServiceDescriptor`` aliased ``ServiceSpec`` — one service — before this.

        The element container keeps that name inside ``descriptor.py``; the
        archetype takes it here. Comparing the two by identity is the mistake
        this test exists to catch early.
        """
        from gen_eval.descriptor import ServiceSpec

        assert ServiceDescriptor is not ServiceSpec
        for field in ("operations", "contract"):
            assert field in ServiceDescriptor.model_fields

    def test_it_declares_services_the_evaluator_can_drive(self) -> None:
        descriptor = ServiceDescriptor.from_contract(
            CONTRACT_PATH, base_url="http://127.0.0.1:8000"
        )
        assert {s.type for s in descriptor.services} == {"http", "mcp", "cli"}
        http = next(s for s in descriptor.services if s.type == "http")
        assert http.base_url == "http://127.0.0.1:8000"

    def test_a_contract_with_one_surface_declares_only_that_surface(self, tmp_path: Path) -> None:
        """Negative control for the test above: surfaces come from the contract."""
        descriptor = ServiceDescriptor.from_contract(write_contract(tmp_path, MINIMAL_CONTRACT))
        assert {s.type for s in descriptor.services} == {"http", "mcp"}


# ---------------------------------------------------------------------------
# D2/D3 — the service drift guard (task 2.5)
# ---------------------------------------------------------------------------

GENERATOR = PACKAGE_ROOT / "scripts" / "generate_service_descriptor.py"


def run_generator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *(str(a) for a in args)],
        cwd=str(PACKAGE_ROOT),
        capture_output=True,
        text=True,
    )


@pytest.fixture
def generated(tmp_path: Path) -> tuple[Path, Path]:
    contract = write_contract(tmp_path, load_contract())
    out = tmp_path / "descriptor.yaml"
    result = run_generator("--contract", contract, "--out", out)
    assert result.returncode == 0, result.stderr
    return contract, out


class TestServiceDriftGuard:
    def test_generates_a_loadable_descriptor(self, generated: tuple[Path, Path]) -> None:
        _, out = generated
        assert ServiceDescriptor.from_yaml(out).coverage_unit_count() == 5

    def test_generation_is_deterministic(self, generated: tuple[Path, Path]) -> None:
        contract, out = generated
        first = out.read_text()
        assert run_generator("--contract", contract, "--out", out).returncode == 0
        assert out.read_text() == first

    def test_check_passes_on_a_fresh_artifact(self, generated: tuple[Path, Path]) -> None:
        """Negative control: the guard is satisfiable."""
        contract, out = generated
        assert run_generator("--contract", contract, "--out", out, "--check").returncode == 0

    def test_drift_fails_and_names_the_artifact(self, generated: tuple[Path, Path]) -> None:
        contract, out = generated
        document = yaml.safe_load(out.read_text())
        document["operations"][0]["summary"] = "edited by hand"
        out.write_text(yaml.safe_dump(document, sort_keys=False))

        result = run_generator("--contract", contract, "--out", out, "--check")
        assert result.returncode != 0
        assert out.name in result.stderr

    def test_operation_count_mismatch_fails_and_reports_both_counts(
        self, generated: tuple[Path, Path]
    ) -> None:
        contract, out = generated
        document = yaml.safe_load(out.read_text())
        document["operations"] = document["operations"][:3]
        out.write_text(yaml.safe_dump(document, sort_keys=False))

        result = run_generator("--contract", contract, "--out", out, "--check")
        assert result.returncode != 0
        assert "3" in result.stderr and "5" in result.stderr

    def test_an_empty_contract_fails_rather_than_generating_an_empty_surface(
        self, tmp_path: Path
    ) -> None:
        contract = write_contract(tmp_path, {"openapi": "3.1.0", "info": {}, "paths": {}})
        out = tmp_path / "descriptor.yaml"
        result = run_generator("--contract", contract, "--out", out)
        assert result.returncode != 0
        assert "zero operations" in result.stderr
        assert not out.exists()

    def test_the_coverage_unit_is_the_operation_not_the_interface(
        self, generated: tuple[Path, Path]
    ) -> None:
        """Counting interfaces here would report 11 for a 5-operation contract."""
        contract, out = generated
        stdout = run_generator("--contract", contract, "--out", out, "--check").stdout
        assert "5 operations" in stdout
