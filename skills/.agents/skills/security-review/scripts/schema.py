#!/usr/bin/env python3
"""Canonical report schema for /security-review outputs."""

from __future__ import annotations

from typing import Any

try:
    from jsonschema import validate as jsonschema_validate
except ImportError:  # pragma: no cover - optional runtime dependency
    jsonschema_validate = None

REPORT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["profile", "scanner_results", "summary", "gate"],
    "properties": {
        "profile": {
            "type": "object",
            "required": ["primary_profile", "profiles", "confidence", "signals"],
            "properties": {
                "primary_profile": {"type": "string"},
                "profiles": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["low", "med", "high"]},
                "signals": {"type": "array", "items": {"type": "string"}},
            },
        },
        "scanner_results": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scanner", "status", "findings"],
                "properties": {
                    "scanner": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["ok", "skipped", "unavailable", "error"],
                    },
                    "messages": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "metadata": {"type": "object"},
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["scanner", "finding_id", "title", "severity"],
                            "properties": {
                                "scanner": {"type": "string"},
                                "finding_id": {"type": "string"},
                                "title": {"type": "string"},
                                "severity": {
                                    "type": "string",
                                    "enum": ["info", "low", "medium", "high", "critical"],
                                },
                                "description": {"type": "string"},
                                "location": {"type": "string"},
                                "metadata": {"type": "object"},
                            },
                        },
                    },
                },
            },
        },
        "summary": {
            "type": "object",
            "required": ["total_findings", "by_severity"],
            "properties": {
                "total_findings": {"type": "integer", "minimum": 0},
                "by_severity": {
                    "type": "object",
                    "required": ["info", "low", "medium", "high", "critical"],
                    "properties": {
                        "info": {"type": "integer", "minimum": 0},
                        "low": {"type": "integer", "minimum": 0},
                        "medium": {"type": "integer", "minimum": 0},
                        "high": {"type": "integer", "minimum": 0},
                        "critical": {"type": "integer", "minimum": 0},
                    },
                },
            },
        },
        "gate": {
            "type": "object",
            "required": ["decision", "fail_on", "triggered_count", "reasons"],
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["PASS", "FAIL", "INCONCLUSIVE"],
                },
                "fail_on": {
                    "type": "string",
                    "enum": ["info", "low", "medium", "high", "critical"],
                },
                "triggered_count": {"type": "integer", "minimum": 0},
                "reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    },
}


def validate_report(report: dict[str, Any]) -> None:
    """Validate report payload when jsonschema is available."""
    if jsonschema_validate is None:
        return
    jsonschema_validate(report, REPORT_SCHEMA)
