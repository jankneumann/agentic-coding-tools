"""Tests for artifact sanitization utilities."""

from __future__ import annotations

from pathlib import Path

from sanitizer import sanitize_dict, sanitize_string, validate_no_secrets


class TestSanitizeString:
    def test_redacts_api_key(self):
        result = sanitize_string("api_key: sk-abc123def456")
        assert "[REDACTED:api_key]" in result
        assert "sk-abc123" not in result

    def test_redacts_token(self):
        result = sanitize_string("bearer: eyJhbGciOiJSUzI1NiJ9")
        assert "[REDACTED:token]" in result

    def test_redacts_password(self):
        result = sanitize_string("password=hunter2")
        assert "[REDACTED:password]" in result

    def test_redacts_github_token(self):
        result = sanitize_string("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm")
        assert "[REDACTED:github_token]" in result

    def test_preserves_safe_content(self):
        safe = "Selected REST API approach for better tooling"
        assert sanitize_string(safe) == safe

class TestSanitizeDict:
    def test_removes_prohibited_fields(self):
        data = {
            "decision": "Use REST",
            "raw_prompt": "This is a secret prompt",
            "credentials": {"key": "value"},
        }
        result = sanitize_dict(data)
        assert result["raw_prompt"] == "[REDACTED:raw_prompt]"
        assert result["credentials"] == "[REDACTED:credentials]"
        assert result["decision"] == "Use REST"

    def test_nested_sanitization(self):
        data = {
            "vendor_notes": {
                "config": "api_key: sk-test123 was used",
                "normal": "safe content",
            }
        }
        result = sanitize_dict(data)
        assert "sk-test123" not in str(result)

    def test_list_sanitization(self):
        data = {
            "items": [
                {"secret": "password=abc123"},
                {"safe": "normal text"},
            ]
        }
        result = sanitize_dict(data)
        assert "abc123" not in str(result)

class TestValidateNoSecrets:
    def test_clean_data(self):
        data = {"decision": "Use REST", "cost_usd": 1.50}
        warnings = validate_no_secrets(data)
        assert warnings == []

    def test_detects_prohibited_field(self):
        data = {"raw_prompt": "something"}
        warnings = validate_no_secrets(data)
        assert any("Prohibited" in w for w in warnings)

    def test_detects_pattern_in_value(self):
        data = {"notes": "the api_key: sk-abc123 was used"}
        warnings = validate_no_secrets(data)
        assert any("api_key" in w for w in warnings)
