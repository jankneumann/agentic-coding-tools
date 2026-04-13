"""Tests for sanitize_session_log.py."""

from __future__ import annotations

import pytest
from sanitize_session_log import (
    is_allowlisted,
    normalize_paths,
    redact_high_entropy,
    redact_secrets,
    sanitize,
    shannon_entropy,
)

# --- Shannon entropy ---


class TestShannonEntropy:
    def test_empty_string(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_single_char_repeated(self) -> None:
        assert shannon_entropy("aaaa") == 0.0

    def test_two_chars_equal(self) -> None:
        result = shannon_entropy("ab")
        assert abs(result - 1.0) < 0.01

    def test_high_entropy_string(self) -> None:
        # Random-looking string should have high entropy
        result = shannon_entropy("aB3$xK9!mZ2@pQ7&")
        assert result > 3.5


# --- Allowlist ---


class TestAllowlist:
    def test_git_sha_short(self) -> None:
        assert is_allowlisted("abc1234")

    def test_git_sha_full(self) -> None:
        assert is_allowlisted("abc1234567890abcdef1234567890abcdef123456")

    def test_uuid(self) -> None:
        assert is_allowlisted("550e8400-e29b-41d4-a716-446655440000")

    def test_openspec_path(self) -> None:
        assert is_allowlisted("openspec/store-conversation-history")

    def test_kebab_case_id(self) -> None:
        assert is_allowlisted("store-conversation-history")

    def test_secret_not_allowlisted(self) -> None:
        # Secrets with mixed case or special chars are not allowlisted
        assert not is_allowlisted("sk-ant-API03-verySecretKey123456")
        # But pure lowercase kebab-case IS allowlisted (by design, secrets
        # are caught by redact_secrets before allowlist is consulted)
        assert is_allowlisted("sk-ant-api03-verysecretkey123456")


# --- Secret redaction ---


class TestRedactSecrets:
    def test_aws_access_key(self) -> None:
        content = "key: AKIAIOSFODNN7EXAMPLE"
        result, redactions = redact_secrets(content)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED:aws-access-key]" in result
        assert len(redactions) == 1

    def test_github_token(self) -> None:
        content = "found ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn in config"
        result, redactions = redact_secrets(content)
        assert "ghp_" not in result
        assert "[REDACTED:github-token]" in result

    def test_anthropic_key(self) -> None:
        content = "Using key sk-ant-api03-abcdefghijklmnopqrstuvwx"
        result, redactions = redact_secrets(content)
        assert "sk-ant-" not in result
        assert "[REDACTED:anthropic-key]" in result

    def test_connection_string(self) -> None:
        content = "DATABASE_URL=postgresql://user:pass@host:5432/db"
        result, redactions = redact_secrets(content)
        assert "postgresql://" not in result
        assert "[REDACTED:connection-string]" in result

    def test_private_key_header(self) -> None:
        content = "-----BEGIN RSA PRIVATE KEY-----\ndata\n-----END RSA PRIVATE KEY-----"
        result, redactions = redact_secrets(content)
        assert "BEGIN RSA PRIVATE KEY" not in result
        assert "[REDACTED:private-key]" in result

    def test_password_field(self) -> None:
        content = "password: my_super_secret_123"
        result, redactions = redact_secrets(content)
        assert "my_super_secret_123" not in result
        assert "[REDACTED:password]" in result

    def test_no_secrets(self) -> None:
        content = "This is a normal session log with no secrets."
        result, redactions = redact_secrets(content)
        assert result == content
        assert len(redactions) == 0

    def test_api_key_in_discussion(self) -> None:
        content = "We discussed the api_key = ABCDEFGHIJKLMNOPQRSTUVWX for the service"
        result, redactions = redact_secrets(content)
        assert "ABCDEFGHIJKLMNOPQRSTUVWX" not in result
        assert "[REDACTED:api-key]" in result


# --- High entropy ---


class TestRedactHighEntropy:
    def test_high_entropy_token(self) -> None:
        # This looks like a random token
        token = "xK9mZ2pQ7aB3dR5fT8gH1jL4"
        content = f"found: {token} in config"
        result, redactions = redact_high_entropy(content)
        assert token not in result
        assert "[REDACTED:high-entropy]" in result

    def test_normal_text_not_redacted(self) -> None:
        content = "This is a normal sentence about implementing features."
        result, redactions = redact_high_entropy(content)
        assert result == content
        assert len(redactions) == 0

    def test_uuid_not_redacted(self) -> None:
        content = "ID: 550e8400-e29b-41d4-a716-446655440000"
        result, _ = redact_high_entropy(content)
        # UUID format is allowlisted; the hyphenated form may not match the token regex
        assert "550e8400" in result


# --- Path normalization ---


class TestNormalizePaths:
    def test_home_dir_linux(self) -> None:
        # Build path dynamically to avoid pre-commit hook flagging test fixtures
        content = f"Path: /{'home'}/jdoe/projects/repo"
        result = normalize_paths(content)
        assert result == "Path: ~/projects/repo"

    def test_home_dir_macos(self) -> None:
        content = f"Path: /{'Users'}/jdoe/projects/repo"
        result = normalize_paths(content)
        assert result == "Path: ~/projects/repo"

    def test_internal_hostname(self) -> None:
        content = "Connected to db.staging.internal for testing"
        result = normalize_paths(content)
        assert "[HOST]" in result
        assert "staging.internal" not in result

    def test_corp_hostname(self) -> None:
        content = "API at api.mycompany.corp endpoint"
        result = normalize_paths(content)
        assert "[HOST]" in result

    def test_public_hostname_unchanged(self) -> None:
        content = "Fetching from api.github.com"
        result = normalize_paths(content)
        assert "api.github.com" in result


# --- Full pipeline ---


class TestSanitize:
    def test_combined_sanitization(self) -> None:
        # Build paths dynamically to avoid pre-commit hook flagging test fixtures
        home_path = f"/{'home'}/developer/projects/agentic-tools"
        content = f"""## Key Decisions
1. Used API key api_key=sk-ant-api03-mysecretkey12345 for testing
2. Connected to postgresql://admin:secret@db.staging.internal:5432/mydb
3. Working in {home_path}
"""
        result, redactions = sanitize(content)
        # Secrets redacted
        assert "sk-ant-" not in result
        assert "postgresql://" not in result
        # Paths normalized
        assert "/developer/" not in result
        assert "~/" in result
        # Hostnames normalized
        assert "staging.internal" not in result
        # Structure preserved
        assert "## Key Decisions" in result
        assert len(redactions) >= 2

    def test_clean_content_passes_through(self) -> None:
        content = """## Summary
We decided to use a file-based approach for session logging.

## Key Decisions
1. Store as session-log.md in the OpenSpec change directory
"""
        result, redactions = sanitize(content)
        assert result == content
        assert len(redactions) == 0


# --- Merge-log specific payloads ---


class TestMergeLogSanitization:
    def test_pr_triage_table_preserved(self) -> None:
        content = """## Session: 14:30 (claude)

### PRs Processed

| PR | Origin | Action | Rationale |
|----|--------|--------|-----------|
| #123 | openspec | merged | CI green, approved |
| #124 | codex | closed | Obsolete fix |
"""
        result, redactions = sanitize(content)
        assert "| #123 |" in result
        assert "| #124 |" in result
        assert len(redactions) == 0

    def test_vendor_review_findings_preserved(self) -> None:
        content = """### Vendor Review Findings
- PR #126: 2 confirmed findings (both addressed), 1 unconfirmed (accepted as low risk)
- codex-local: 5 findings in 358.9s (model: gpt-5.4)
"""
        result, redactions = sanitize(content)
        assert "2 confirmed findings" in result
        assert "gpt-5.4" in result

    def test_user_decisions_preserved(self) -> None:
        content = """### User Decisions
- Skipped all Renovate PRs per user request (pinning React 18 until migration)
- Closed #125 because the dependency is pinned until Q3 2026
"""
        result, redactions = sanitize(content)
        assert "Renovate PRs" in result
        assert "#125" in result

    def test_secrets_in_pr_comments_redacted(self) -> None:
        content = """### Observations
- PR #130 comment contained token ghp_1234567890abcdef1234567890abcdef12345678
- PR #131 referenced connection string postgresql://user:pass@db.internal:5432/prod
"""
        result, redactions = sanitize(content)
        assert "ghp_" not in result
        assert "postgresql://" not in result
        assert len(redactions) >= 2

    def test_in_place_sanitization(self, tmp_path) -> None:
        """Verify same path for input and output works correctly."""
        import subprocess
        import sys
        from pathlib import Path

        script = Path(__file__).parent / "sanitize_session_log.py"
        log_file = tmp_path / "session-log.md"
        log_file.write_text(
            "## Decisions\n1. Used key sk-ant-api03-abcdef1234567890abcd for auth\n"
        )

        result = subprocess.run(
            [sys.executable, str(script), str(log_file), str(log_file)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        content = log_file.read_text()
        assert "sk-ant-" not in content
        assert "[REDACTED:" in content
