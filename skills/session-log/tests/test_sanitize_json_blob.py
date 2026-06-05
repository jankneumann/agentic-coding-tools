"""Tests for sanitize_json_blob — extended sanitizer for tool-call argument blobs.

Covers:
- Dict blobs containing secrets are redacted
- List blobs containing secrets are redacted
- String blobs are passed through the full pipeline
- Clean blobs pass through unchanged
- Existing redaction rules (secrets, entropy, paths) still work
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestSanitizeJsonBlob:
    """Test sanitize_json_blob for tool-call argument coverage."""

    def test_redacts_api_key_in_dict(self) -> None:
        from sanitize_session_log import sanitize_json_blob

        blob = {"command": "curl -H 'Authorization: Bearer sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890' https://api.example.com"}
        sanitized, redactions = sanitize_json_blob(blob)
        assert "sk-ant-" not in sanitized
        assert len(redactions) >= 1

    def test_redacts_connection_string_in_dict(self) -> None:
        from sanitize_session_log import sanitize_json_blob

        blob = {"config": "postgres://user:pass@db.internal.company:5432/mydb"}
        sanitized, redactions = sanitize_json_blob(blob)
        assert "postgres://" not in sanitized
        assert len(redactions) >= 1

    def test_redacts_secret_in_list(self) -> None:
        from sanitize_session_log import sanitize_json_blob

        blob = [{"env": "API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"}]
        sanitized, redactions = sanitize_json_blob(blob)
        assert "sk-ant-" not in sanitized
        assert len(redactions) >= 1

    def test_string_blob_sanitized(self) -> None:
        from sanitize_session_log import sanitize_json_blob

        blob = "The key is ghp_1234567890abcdefghijklmnopqrstuvwxyz12"
        sanitized, redactions = sanitize_json_blob(blob)
        assert "ghp_" not in sanitized
        assert len(redactions) >= 1

    def test_clean_blob_passes_through(self) -> None:
        from sanitize_session_log import sanitize_json_blob

        blob = {"command": "ls -la", "path": "/tmp/test"}
        sanitized, redactions = sanitize_json_blob(blob)
        assert "ls -la" in sanitized
        assert redactions == []

    def test_normalizes_paths_in_blob(self) -> None:
        from sanitize_session_log import sanitize_json_blob

        blob = {"cwd": "/home/realuser/project/src"}
        sanitized, _ = sanitize_json_blob(blob)
        assert "/home/realuser/" not in sanitized
        assert "~/" in sanitized
