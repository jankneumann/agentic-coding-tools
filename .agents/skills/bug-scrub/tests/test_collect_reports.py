"""Tests for architecture and security signal collectors."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import collect_architecture
import collect_security

# ---------------------------------------------------------------------------
# Fixtures: sample JSON data
# ---------------------------------------------------------------------------

SAMPLE_ARCH_DIAGNOSTICS: dict = {
    "findings": [
        {
            "severity": "error",
            "category": "broken-flow",
            "message": "Handler references missing module",
            "file": "src/api/handlers.py",
            "line": 42,
            "suggestion": "Add the missing import or remove the reference",
        },
        {
            "severity": "warning",
            "category": "unused-endpoint",
            "message": "Endpoint /health is declared but never routed",
            "file": "src/api/routes.py",
            "line": 10,
            "suggestion": "Wire the endpoint or remove the declaration",
        },
        {
            "severity": "info",
            "category": "naming",
            "message": "Module name does not follow convention",
            "file": "src/utils/helpers.py",
            "line": None,
            "suggestion": "",
        },
    ],
}

SAMPLE_SECURITY_REPORT: dict = {
    "findings": [
        {
            "finding_id": "SEC-001",
            "severity": "critical",
            "title": "Hardcoded secret in source",
            "description": "API key is hardcoded in configuration module",
            "location": "src/config.py:15",
            "scanner": "gitleaks",
        },
        {
            "finding_id": "SEC-002",
            "severity": "high",
            "title": "SQL injection risk",
            "description": "User input passed directly to query builder",
            "location": "src/db/queries.py:88",
            "scanner": "semgrep",
        },
        {
            "finding_id": "SEC-003",
            "severity": "medium",
            "title": "Missing rate limiting",
            "description": "Public endpoint lacks rate limiting middleware",
            "location": "src/api/routes.py",
            "scanner": "manual",
        },
        {
            "finding_id": "SEC-004",
            "severity": "low",
            "title": "Verbose error messages",
            "description": "Stack traces exposed in production error responses",
            "location": "src/api/error_handler.py:30",
            "scanner": "semgrep",
        },
        {
            "finding_id": "SEC-005",
            "severity": "info",
            "title": "Dependency has known advisory",
            "description": "Non-exploitable advisory in transitive dependency",
            "location": "requirements.txt",
            "scanner": "osv-scanner",
        },
    ],
}


def _write_json(path: Path, data: dict) -> None:
    """Helper to write JSON data, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _arch_diag_path(project_dir: Path) -> Path:
    return project_dir / "docs" / "architecture-analysis" / "architecture.diagnostics.json"


def _security_report_path(project_dir: Path) -> Path:
    return project_dir / "docs" / "security-review" / "security-review-report.json"


# ===================================================================
# Architecture collector tests
# ===================================================================


class TestArchitectureCollector:
    """Tests for collect_architecture.collect()."""

    def test_parse_sample_diagnostics(self, tmp_path: Path) -> None:
        """Collector parses valid diagnostics JSON and returns findings."""
        _write_json(_arch_diag_path(tmp_path), SAMPLE_ARCH_DIAGNOSTICS)

        result = collect_architecture.collect(str(tmp_path))

        assert result.source == "architecture"
        assert result.status == "ok"
        assert len(result.findings) == 3

    def test_finding_fields_populated(self, tmp_path: Path) -> None:
        """Each finding has correct id, title, file_path, and line."""
        _write_json(_arch_diag_path(tmp_path), SAMPLE_ARCH_DIAGNOSTICS)

        result = collect_architecture.collect(str(tmp_path))

        f0 = result.findings[0]
        assert f0.id == "arch-broken-flow-0"
        assert f0.source == "architecture"
        assert f0.category == "architecture"
        assert f0.file_path == "src/api/handlers.py"
        assert f0.line == 42
        assert "Handler references missing module" in f0.title
        assert "Suggestion:" in f0.detail

    def test_severity_mapping_error_to_high(self, tmp_path: Path) -> None:
        """Diagnostic severity 'error' maps to finding severity 'high'."""
        _write_json(_arch_diag_path(tmp_path), SAMPLE_ARCH_DIAGNOSTICS)

        result = collect_architecture.collect(str(tmp_path))
        assert result.findings[0].severity == "high"

    def test_severity_mapping_warning_to_medium(self, tmp_path: Path) -> None:
        """Diagnostic severity 'warning' maps to finding severity 'medium'."""
        _write_json(_arch_diag_path(tmp_path), SAMPLE_ARCH_DIAGNOSTICS)

        result = collect_architecture.collect(str(tmp_path))
        assert result.findings[1].severity == "medium"

    def test_severity_mapping_info_to_low(self, tmp_path: Path) -> None:
        """Diagnostic severity 'info' maps to finding severity 'low'."""
        _write_json(_arch_diag_path(tmp_path), SAMPLE_ARCH_DIAGNOSTICS)

        result = collect_architecture.collect(str(tmp_path))
        assert result.findings[2].severity == "low"

    def test_severity_mapping_unknown_defaults_to_low(self, tmp_path: Path) -> None:
        """Unknown severity values default to 'low'."""
        data = {
            "findings": [
                {
                    "severity": "catastrophic",
                    "category": "test",
                    "message": "Unknown severity level",
                },
            ],
        }
        _write_json(_arch_diag_path(tmp_path), data)

        result = collect_architecture.collect(str(tmp_path))
        assert result.findings[0].severity == "low"

    def test_staleness_detection(self, tmp_path: Path) -> None:
        """Files older than 7 days produce a staleness warning message."""
        diag_file = _arch_diag_path(tmp_path)
        _write_json(diag_file, SAMPLE_ARCH_DIAGNOSTICS)

        # Set modification time to 10 days ago
        ten_days_ago = time.time() - (10 * 86400)
        os.utime(diag_file, (ten_days_ago, ten_days_ago))

        result = collect_architecture.collect(str(tmp_path))

        assert result.status == "ok"
        assert len(result.messages) == 1
        assert "days old" in result.messages[0]
        assert "make architecture" in result.messages[0]

    def test_no_staleness_warning_when_fresh(self, tmp_path: Path) -> None:
        """Recently modified files do not produce a staleness warning."""
        _write_json(_arch_diag_path(tmp_path), SAMPLE_ARCH_DIAGNOSTICS)
        # File was just created, so mtime is fresh -- no staleness warning

        result = collect_architecture.collect(str(tmp_path))

        assert result.status == "ok"
        assert len(result.messages) == 0

    def test_missing_file_returns_skipped(self, tmp_path: Path) -> None:
        """When the diagnostics file does not exist, status is 'skipped'."""
        result = collect_architecture.collect(str(tmp_path))

        assert result.source == "architecture"
        assert result.status == "skipped"
        assert len(result.findings) == 0
        assert any("not found" in m for m in result.messages)

    def test_empty_findings_list(self, tmp_path: Path) -> None:
        """A valid file with zero findings returns ok with empty list."""
        _write_json(_arch_diag_path(tmp_path), {"findings": []})

        result = collect_architecture.collect(str(tmp_path))

        assert result.status == "ok"
        assert result.findings == []

    def test_invalid_json_returns_error(self, tmp_path: Path) -> None:
        """Malformed JSON returns status 'error'."""
        diag_file = _arch_diag_path(tmp_path)
        diag_file.parent.mkdir(parents=True, exist_ok=True)
        diag_file.write_text("{not valid json", encoding="utf-8")

        result = collect_architecture.collect(str(tmp_path))

        assert result.status == "error"
        assert any("Failed to read/parse" in m for m in result.messages)

    def test_duration_ms_is_non_negative(self, tmp_path: Path) -> None:
        """duration_ms should be a non-negative integer."""
        _write_json(_arch_diag_path(tmp_path), SAMPLE_ARCH_DIAGNOSTICS)

        result = collect_architecture.collect(str(tmp_path))
        assert result.duration_ms >= 0


# ===================================================================
# Security collector tests
# ===================================================================


class TestSecurityCollector:
    """Tests for collect_security.collect()."""

    def test_parse_sample_security_report(self, tmp_path: Path) -> None:
        """Collector parses valid security report and returns findings."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))

        assert result.source == "security"
        assert result.status == "ok"
        assert len(result.findings) == 5

    def test_finding_fields_populated(self, tmp_path: Path) -> None:
        """Each finding has correct id, title, file_path, line, and detail."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))

        f0 = result.findings[0]
        assert f0.id == "sec-SEC-001"
        assert f0.source == "security"
        assert f0.category == "security"
        assert f0.title == "Hardcoded secret in source"
        assert f0.file_path == "src/config.py"
        assert f0.line == 15
        assert "API key is hardcoded" in f0.detail
        assert "Scanner: gitleaks" in f0.detail

    def test_severity_critical_preserved(self, tmp_path: Path) -> None:
        """Security severity 'critical' is preserved as-is."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))
        assert result.findings[0].severity == "critical"

    def test_severity_high_preserved(self, tmp_path: Path) -> None:
        """Security severity 'high' is preserved as-is."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))
        assert result.findings[1].severity == "high"

    def test_severity_medium_preserved(self, tmp_path: Path) -> None:
        """Security severity 'medium' is preserved as-is."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))
        assert result.findings[2].severity == "medium"

    def test_severity_low_preserved(self, tmp_path: Path) -> None:
        """Security severity 'low' is preserved as-is."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))
        assert result.findings[3].severity == "low"

    def test_severity_info_preserved(self, tmp_path: Path) -> None:
        """Security severity 'info' is preserved as-is."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))
        assert result.findings[4].severity == "info"

    def test_severity_unknown_defaults_to_info(self, tmp_path: Path) -> None:
        """Unknown severity values default to 'info'."""
        data = {
            "findings": [
                {
                    "finding_id": "SEC-X",
                    "severity": "catastrophic",
                    "title": "Unknown severity",
                },
            ],
        }
        _write_json(_security_report_path(tmp_path), data)

        result = collect_security.collect(str(tmp_path))
        assert result.findings[0].severity == "info"

    def test_location_with_line_number(self, tmp_path: Path) -> None:
        """Location 'path:line' is split into file_path and line."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))

        # SEC-002: src/db/queries.py:88
        f1 = result.findings[1]
        assert f1.file_path == "src/db/queries.py"
        assert f1.line == 88

    def test_location_without_line_number(self, tmp_path: Path) -> None:
        """Location without ':line' sets file_path only, line is None."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))

        # SEC-003: src/api/routes.py (no line)
        f2 = result.findings[2]
        assert f2.file_path == "src/api/routes.py"
        assert f2.line is None

    def test_finding_without_finding_id_is_skipped(self, tmp_path: Path) -> None:
        """Entries missing finding_id are silently skipped."""
        data = {
            "findings": [
                {
                    "severity": "low",
                    "title": "No ID finding",
                },
                {
                    "finding_id": "SEC-OK",
                    "severity": "low",
                    "title": "Valid finding",
                },
            ],
        }
        _write_json(_security_report_path(tmp_path), data)

        result = collect_security.collect(str(tmp_path))
        assert len(result.findings) == 1
        assert result.findings[0].id == "sec-SEC-OK"

    def test_staleness_detection(self, tmp_path: Path) -> None:
        """Files older than 7 days produce a staleness warning message."""
        report_file = _security_report_path(tmp_path)
        _write_json(report_file, SAMPLE_SECURITY_REPORT)

        # Set modification time to 10 days ago
        ten_days_ago = time.time() - (10 * 86400)
        os.utime(report_file, (ten_days_ago, ten_days_ago))

        result = collect_security.collect(str(tmp_path))

        assert result.status == "ok"
        assert len(result.messages) == 1
        assert "days old" in result.messages[0]
        assert "/security-review" in result.messages[0]

    def test_no_staleness_warning_when_fresh(self, tmp_path: Path) -> None:
        """Recently modified files do not produce a staleness warning."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))

        assert result.status == "ok"
        assert len(result.messages) == 0

    def test_missing_file_returns_skipped(self, tmp_path: Path) -> None:
        """When the security report does not exist, status is 'skipped'."""
        result = collect_security.collect(str(tmp_path))

        assert result.source == "security"
        assert result.status == "skipped"
        assert len(result.findings) == 0
        assert any("not found" in m for m in result.messages)

    def test_empty_findings_list(self, tmp_path: Path) -> None:
        """A valid report with zero findings returns ok with empty list."""
        _write_json(_security_report_path(tmp_path), {"findings": []})

        result = collect_security.collect(str(tmp_path))

        assert result.status == "ok"
        assert result.findings == []

    def test_invalid_json_returns_error(self, tmp_path: Path) -> None:
        """Malformed JSON returns status 'error'."""
        report_file = _security_report_path(tmp_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text("<<<not json>>>", encoding="utf-8")

        result = collect_security.collect(str(tmp_path))

        assert result.status == "error"
        assert any("Failed to parse" in m for m in result.messages)

    def test_duration_ms_is_non_negative(self, tmp_path: Path) -> None:
        """duration_ms should be a non-negative integer."""
        _write_json(_security_report_path(tmp_path), SAMPLE_SECURITY_REPORT)

        result = collect_security.collect(str(tmp_path))
        assert result.duration_ms >= 0
