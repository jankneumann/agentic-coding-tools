"""Tests for multi-source scenario bootstrap.

Covers spec scenarios:
- gen-eval-framework.4.1: Bootstrap from spec deltas
- gen-eval-framework.4.2: Bootstrap from archived exemplar
- gen-eval-framework.4.3: Bootstrap from contract artifact
- gen-eval-framework.4.4: Bootstrap from empty spec delta produces no scenarios
- gen-eval-framework.4.5: Bootstrap from malformed source skips gracefully

Design decisions: D1 (manifest-driven visibility), D6 (deterministic normalization)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Add scripts dir to path so we can import the bootstrap module
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "scripts"),
)

from bootstrap import (
    ScenarioSeed,
    bootstrap_from_archive,
    bootstrap_from_contract,
    bootstrap_from_incident,
    bootstrap_from_spec_delta,
    seeds_to_manifest_entries,
    seeds_to_scenario_yaml,
)

# ── Bootstrap from spec delta ─────────────────────────────────────


class TestBootstrapFromSpecDelta:
    """Test scenario seed extraction from spec delta files."""

    def _write_spec(self, path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_extracts_scenarios_from_spec(self, tmp_path: Path) -> None:
        """gen-eval-framework.4.1: Bootstrap from spec deltas."""
        spec = self._write_spec(
            tmp_path / "spec.md",
            """\
### Requirement: Lock Acquisition

The system SHALL support file lock acquisition.

#### Scenario: Lock acquired successfully
Given a file is not locked
When an agent requests a lock
Then the lock is granted

#### Scenario: Lock rejected when already held
Given a file is locked by another agent
When an agent requests a lock
Then the request is rejected
""",
        )
        seeds = bootstrap_from_spec_delta(spec)
        assert len(seeds) == 2
        assert seeds[0].source == "spec"
        assert seeds[0].source_ref == "Lock Acquisition"
        assert seeds[0].name == "Lock acquired successfully"
        assert seeds[1].name == "Lock rejected when already held"

    def test_empty_spec_produces_no_seeds(self, tmp_path: Path) -> None:
        """gen-eval-framework.4.4: Empty spec produces no scenarios."""
        spec = self._write_spec(tmp_path / "empty.md", "")
        seeds = bootstrap_from_spec_delta(spec)
        assert seeds == []

    def test_spec_without_scenarios_produces_no_seeds(self, tmp_path: Path) -> None:
        spec = self._write_spec(
            tmp_path / "no-scenarios.md",
            "### Requirement: Something\n\nJust text, no scenarios.\n",
        )
        seeds = bootstrap_from_spec_delta(spec)
        assert seeds == []

    def test_missing_spec_file(self, tmp_path: Path) -> None:
        seeds = bootstrap_from_spec_delta(tmp_path / "missing.md")
        assert seeds == []

    def test_multiple_requirements(self, tmp_path: Path) -> None:
        spec = self._write_spec(
            tmp_path / "multi.md",
            """\
### Requirement: Feature A

#### Scenario: A works

### Requirement: Feature B

#### Scenario: B works
""",
        )
        seeds = bootstrap_from_spec_delta(spec)
        assert len(seeds) == 2
        assert seeds[0].source_ref == "Feature A"
        assert seeds[1].source_ref == "Feature B"

    def test_seeds_have_correct_tags(self, tmp_path: Path) -> None:
        spec = self._write_spec(
            tmp_path / "spec.md",
            "### Requirement: X\n\n#### Scenario: Test X\n",
        )
        seeds = bootstrap_from_spec_delta(spec)
        assert "bootstrapped" in seeds[0].tags
        assert "spec-derived" in seeds[0].tags


# ── Bootstrap from contract ───────────────────────────────────────


class TestBootstrapFromContract:
    """Test scenario seed extraction from contract artifacts."""

    def test_openapi_endpoints(self, tmp_path: Path) -> None:
        """gen-eval-framework.4.3: Bootstrap from contract artifact."""
        contract = tmp_path / "openapi.yaml"
        with open(contract, "w") as f:
            yaml.dump(
                {
                    "openapi": "3.0.0",
                    "paths": {
                        "/locks/acquire": {
                            "post": {
                                "operationId": "acquireLock",
                                "summary": "Acquire a file lock",
                            }
                        },
                        "/health": {
                            "get": {
                                "operationId": "healthCheck",
                                "summary": "Health check",
                            }
                        },
                    },
                },
                f,
            )
        seeds = bootstrap_from_contract(contract)
        assert len(seeds) == 2
        assert all(s.source == "contract" for s in seeds)
        assert any("POST /locks/acquire" in s.interfaces for s in seeds)

    def test_missing_contract(self, tmp_path: Path) -> None:
        seeds = bootstrap_from_contract(tmp_path / "missing.yaml")
        assert seeds == []

    def test_malformed_contract(self, tmp_path: Path) -> None:
        """gen-eval-framework.4.5: Malformed source skips gracefully."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(": : :")
        seeds = bootstrap_from_contract(bad)
        # Should not crash, returns empty or partial
        assert isinstance(seeds, list)

    def test_contract_without_paths(self, tmp_path: Path) -> None:
        contract = tmp_path / "empty-api.yaml"
        with open(contract, "w") as f:
            yaml.dump({"openapi": "3.0.0", "info": {"title": "Test"}}, f)
        seeds = bootstrap_from_contract(contract)
        assert seeds == []


# ── Bootstrap from incident ───────────────────────────────────────


class TestBootstrapFromIncident:
    """Test incident-derived scenario seed creation."""

    def test_creates_holdout_seed(self) -> None:
        seeds = bootstrap_from_incident(
            incident_id="INC-42",
            description="Lock contention under high concurrency",
            affected_interfaces=["POST /locks/acquire"],
        )
        assert len(seeds) == 1
        assert seeds[0].visibility == "holdout"
        assert seeds[0].source == "incident"
        assert seeds[0].source_ref == "INC-42"
        assert "INC-42" in seeds[0].tags

    def test_no_interfaces(self) -> None:
        seeds = bootstrap_from_incident(
            incident_id="INC-99",
            description="General failure",
        )
        assert len(seeds) == 1
        assert seeds[0].interfaces == []


# ── Bootstrap from archive ────────────────────────────────────────


class TestBootstrapFromArchive:
    """Test archive-derived scenario seed extraction."""

    def test_extracts_from_archived_specs(self, tmp_path: Path) -> None:
        """gen-eval-framework.4.2: Bootstrap from archived exemplar."""
        archive = tmp_path / "archive" / "old-change"
        specs = archive / "specs" / "some-spec"
        specs.mkdir(parents=True)
        (specs / "spec.md").write_text(
            "### Requirement: Old Feature\n\n#### Scenario: Old test\n"
        )
        seeds = bootstrap_from_archive("old-change", archive)
        assert len(seeds) == 1
        assert seeds[0].source == "archive"
        assert "old-change" in seeds[0].tags

    def test_missing_archive(self, tmp_path: Path) -> None:
        seeds = bootstrap_from_archive("missing", tmp_path / "nope")
        assert seeds == []

    def test_archive_without_specs(self, tmp_path: Path) -> None:
        archive = tmp_path / "empty-archive"
        archive.mkdir()
        seeds = bootstrap_from_archive("empty", archive)
        assert seeds == []


# ── Seed conversion ───────────────────────────────────────────────


class TestSeedConversion:
    """Test conversion of seeds to manifest entries and scenario YAML."""

    @pytest.fixture
    def sample_seeds(self) -> list[ScenarioSeed]:
        return [
            ScenarioSeed(
                scenario_id="test-1",
                name="Test scenario 1",
                description="A test",
                category="testing",
                source="spec",
                source_ref="Requirement A",
                visibility="public",
            ),
            ScenarioSeed(
                scenario_id="test-2",
                name="Test scenario 2",
                description="Another test",
                category="testing",
                source="incident",
                source_ref="INC-1",
                visibility="holdout",
            ),
        ]

    def test_manifest_entries(self, sample_seeds: list[ScenarioSeed]) -> None:
        entries = seeds_to_manifest_entries(sample_seeds)
        assert len(entries) == 2
        assert entries[0]["visibility"] == "public"
        assert entries[0]["source"] == "spec"
        assert entries[1]["visibility"] == "holdout"
        assert entries[1]["incident_ref"] == "INC-1"

    def test_scenario_yaml(self, sample_seeds: list[ScenarioSeed]) -> None:
        scenarios = seeds_to_scenario_yaml(sample_seeds)
        assert len(scenarios) == 2
        assert scenarios[0]["id"] == "test-1"
        assert scenarios[0]["category"] == "testing"
        # Default placeholder step
        assert len(scenarios[0]["steps"]) == 1
        assert scenarios[0]["steps"][0]["transport"] == "http"
