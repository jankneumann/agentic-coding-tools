"""Tests for DTU scaffold generation from public docs.

Covers spec scenarios:
- gen-eval-framework.3.1: DTU scaffold generated from public docs
- gen-eval-framework.3.2: Fidelity report marks low-confidence as non-holdout
- gen-eval-framework.3.3: Fidelity report captures live probe results

Design decisions: D3 (DTU-lite with fidelity reports)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.gen_eval.dtu_scaffold import (
    AuthDoc,
    DTUScaffold,
    EndpointDoc,
    ErrorMode,
    PublicDocInput,
    generate_scaffold,
    write_scaffold,
)
from evaluation.gen_eval.fidelity import (
    HOLDOUT_ELIGIBLE_THRESHOLD,
    FidelityReport,
    ProbeResult,
    compute_fidelity,
    write_fidelity_report,
)

# ── Scaffold generation ───────────────────────────────────────────


class TestGenerateScaffold:
    """Test DTU scaffold generation from public docs."""

    @pytest.fixture
    def sample_input(self) -> PublicDocInput:
        return PublicDocInput(
            system_name="github-api",
            base_url="https://api.github.com",
            version="v3",
            auth=AuthDoc(type="bearer", header="Authorization"),
            endpoints=[
                EndpointDoc(
                    path="/repos/{owner}/{repo}/pulls",
                    method="GET",
                    description="List pull requests",
                    response_schema={"type": "array"},
                    error_codes=[404, 403],
                ),
                EndpointDoc(
                    path="/repos/{owner}/{repo}/pulls",
                    method="POST",
                    description="Create a pull request",
                    auth_required=True,
                    request_schema={"type": "object"},
                    error_codes=[422],
                ),
            ],
            error_modes=[
                ErrorMode(code=403, name="Forbidden", description="Rate limited"),
                ErrorMode(code=404, name="Not Found"),
            ],
        )

    def test_scaffold_from_docs(self, sample_input: PublicDocInput) -> None:
        """gen-eval-framework.3.1: DTU scaffold generated from public docs."""
        scaffold = generate_scaffold(sample_input)
        assert scaffold.system_name == "github-api"
        assert scaffold.descriptor_seed["project"] == "dtu-github-api"
        assert len(scaffold.descriptor_seed["services"]) == 1
        assert len(scaffold.descriptor_seed["services"][0]["endpoints"]) == 2

    def test_fixture_paths_generated(self, sample_input: PublicDocInput) -> None:
        scaffold = generate_scaffold(sample_input)
        assert len(scaffold.fixture_paths) > 0
        assert any("success" in p for p in scaffold.fixture_paths)
        assert any("error_404" in p for p in scaffold.fixture_paths)

    def test_unsupported_surfaces_detected(self) -> None:
        doc = PublicDocInput(
            system_name="sparse-api",
            endpoints=[
                EndpointDoc(
                    path="/data",
                    method="GET",
                    # No response_schema, no examples → unsupported
                ),
            ],
        )
        scaffold = generate_scaffold(doc)
        assert len(scaffold.unsupported_surfaces) > 0
        assert "GET /data" in scaffold.unsupported_surfaces[0]

    def test_error_catalog(self, sample_input: PublicDocInput) -> None:
        scaffold = generate_scaffold(sample_input)
        assert len(scaffold.error_catalog) == 2
        assert scaffold.error_catalog[0]["code"] == 403

    def test_auth_config_in_descriptor(self, sample_input: PublicDocInput) -> None:
        scaffold = generate_scaffold(sample_input)
        svc = scaffold.descriptor_seed["services"][0]
        assert svc["auth"]["type"] == "bearer"

    def test_no_auth(self) -> None:
        doc = PublicDocInput(system_name="open-api")
        scaffold = generate_scaffold(doc)
        svc = scaffold.descriptor_seed["services"][0]
        assert svc["auth"]["type"] == "none"

    def test_metadata(self, sample_input: PublicDocInput) -> None:
        scaffold = generate_scaffold(sample_input)
        assert scaffold.metadata["endpoint_count"] == 2
        assert scaffold.metadata["has_auth"] is True

    def test_oauth2_unsupported(self) -> None:
        doc = PublicDocInput(
            system_name="oauth-api",
            auth=AuthDoc(type="oauth2"),
            endpoints=[
                EndpointDoc(
                    path="/me",
                    method="GET",
                    response_schema={"type": "object"},
                )
            ],
        )
        scaffold = generate_scaffold(doc)
        assert any("OAuth2" in s for s in scaffold.unsupported_surfaces)

    def test_rate_limit_unsupported(self) -> None:
        doc = PublicDocInput(
            system_name="limited-api",
            rate_limits={"requests_per_minute": 60},
            endpoints=[
                EndpointDoc(
                    path="/data",
                    method="GET",
                    response_schema={"type": "object"},
                )
            ],
        )
        scaffold = generate_scaffold(doc)
        assert any("Rate limiting" in s for s in scaffold.unsupported_surfaces)


class TestWriteScaffold:
    """Test writing scaffold artifacts to disk."""

    def test_writes_descriptor_seed(self, tmp_path: Path) -> None:
        scaffold = DTUScaffold(
            system_name="test",
            descriptor_seed={"project": "test", "services": []},
            fixture_paths=["get_health_success.json"],
            unsupported_surfaces=["GET /unknown"],
            error_catalog=[{"code": 500}],
        )
        write_scaffold(scaffold, tmp_path / "dtu")
        assert (tmp_path / "dtu" / "descriptor.seed.yaml").exists()
        assert (tmp_path / "dtu" / "fixtures").is_dir()
        assert (tmp_path / "dtu" / "error-catalog.json").exists()
        assert (tmp_path / "dtu" / "unsupported-surfaces.json").exists()

    def test_writes_fixture_placeholders(self, tmp_path: Path) -> None:
        scaffold = DTUScaffold(
            system_name="test",
            descriptor_seed={},
            fixture_paths=["get_data_success.json", "post_data_error_422.json"],
            unsupported_surfaces=[],
            error_catalog=[],
        )
        write_scaffold(scaffold, tmp_path / "out")
        fixtures = tmp_path / "out" / "fixtures"
        assert (fixtures / "get_data_success.json").exists()
        assert (fixtures / "post_data_error_422.json").exists()

    def test_empty_scaffold(self, tmp_path: Path) -> None:
        scaffold = DTUScaffold(
            system_name="empty",
            descriptor_seed={},
            fixture_paths=[],
            unsupported_surfaces=[],
            error_catalog=[],
        )
        write_scaffold(scaffold, tmp_path / "out")
        assert (tmp_path / "out" / "descriptor.seed.yaml").exists()


# ── Fidelity report ───────────────────────────────────────────────


class TestFidelityReport:
    """Test fidelity scoring and holdout eligibility."""

    def test_low_confidence_not_holdout_eligible(self) -> None:
        """gen-eval-framework.3.2: Low confidence marked non-holdout."""
        report = compute_fidelity(
            system_name="sparse-api",
            sources=["README.md"],
            unsupported_surfaces=["GET /a", "GET /b", "GET /c"],
            total_endpoints=4,
        )
        assert report.conformance_score < HOLDOUT_ELIGIBLE_THRESHOLD
        assert report.holdout_eligible is False

    def test_high_coverage_no_probes_still_not_holdout(self) -> None:
        """Without probes, max score is capped at 0.6."""
        report = compute_fidelity(
            system_name="well-documented",
            sources=["full-docs"],
            unsupported_surfaces=[],
            total_endpoints=10,
        )
        assert report.conformance_score <= 0.6
        assert report.holdout_eligible is False

    def test_probes_enable_holdout(self) -> None:
        """gen-eval-framework.3.3: Probes captured and enable holdout."""
        probes = [
            ProbeResult(
                endpoint="/health",
                method="GET",
                expected_status=200,
                actual_status=200,
                response_matches=True,
            ),
            ProbeResult(
                endpoint="/data",
                method="GET",
                expected_status=200,
                actual_status=200,
                response_matches=True,
            ),
        ]
        report = compute_fidelity(
            system_name="probed-api",
            sources=["docs"],
            unsupported_surfaces=[],
            total_endpoints=2,
            probe_results=probes,
        )
        assert report.conformance_score >= HOLDOUT_ELIGIBLE_THRESHOLD
        assert report.holdout_eligible is True
        assert report.has_probes is True
        assert report.probe_pass_rate == 1.0

    def test_failed_probes_reduce_score(self) -> None:
        probes = [
            ProbeResult(
                endpoint="/health",
                method="GET",
                expected_status=200,
                actual_status=200,
                response_matches=True,
            ),
            ProbeResult(
                endpoint="/data",
                method="GET",
                expected_status=200,
                actual_status=500,
                response_matches=False,
            ),
        ]
        report = compute_fidelity(
            system_name="partial",
            sources=["docs"],
            unsupported_surfaces=[],
            total_endpoints=2,
            probe_results=probes,
        )
        assert report.probe_pass_rate == 0.5
        assert report.conformance_score < 1.0

    def test_operator_approval_overrides(self) -> None:
        report = compute_fidelity(
            system_name="approved",
            sources=["docs"],
            unsupported_surfaces=["many surfaces"],
            total_endpoints=1,
            operator_approved=True,
        )
        assert report.holdout_eligible is True
        assert report.operator_approved is True

    def test_zero_endpoints(self) -> None:
        report = compute_fidelity(
            system_name="empty",
            sources=[],
            unsupported_surfaces=[],
            total_endpoints=0,
        )
        assert report.conformance_score == 0.0

    def test_no_probes_property(self) -> None:
        report = FidelityReport(system_name="test")
        assert report.has_probes is False
        assert report.probe_pass_rate == 0.0


class TestWriteFidelityReport:
    """Test writing fidelity reports to disk."""

    def test_writes_json(self, tmp_path: Path) -> None:
        report = compute_fidelity(
            system_name="test",
            sources=["docs"],
            unsupported_surfaces=["GET /x"],
            total_endpoints=2,
        )
        path = tmp_path / "fidelity-report.json"
        write_fidelity_report(report, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["system_name"] == "test"
        assert data["holdout_eligible"] is False

    def test_writes_probe_results(self, tmp_path: Path) -> None:
        probes = [
            ProbeResult(
                endpoint="/health",
                method="GET",
                expected_status=200,
                actual_status=200,
                response_matches=True,
            )
        ]
        report = compute_fidelity(
            system_name="probed",
            sources=["docs"],
            unsupported_surfaces=[],
            total_endpoints=1,
            probe_results=probes,
        )
        path = tmp_path / "fidelity.json"
        write_fidelity_report(report, path)
        data = json.loads(path.read_text())
        assert "probe_results" in data
        assert data["probe_pass_rate"] == 1.0
