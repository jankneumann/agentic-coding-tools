"""Tests for lock key policy — logical lock keys are accepted."""

from __future__ import annotations

import pytest

from src.locks import (
    FILE_PATH_PATTERN,
    LOGICAL_LOCK_KEY_PATTERN,
    LOGICAL_LOCK_KEY_PREFIXES,
    is_valid_lock_key,
)


class TestLogicalLockKeyPattern:
    """Verify that the regex accepts all documented namespace prefixes."""

    @pytest.mark.parametrize(
        "key",
        [
            "api:GET /v1/users",
            "api:POST /v1/users",
            "api:DELETE /v1/users/123",
            "db:migration-slot",
            "db:schema:users",
            "db:schema:orders",
            "event:user.created",
            "event:order.completed",
            "flag:billing/*",
            "flag:feature/dark-mode",
            "env:shared-fixtures",
            "contract:openapi/v1.yaml",
            "feature:FEAT-123:pause",
            "feature:FEAT-456:review",
        ],
    )
    def test_valid_logical_keys(self, key: str):
        assert LOGICAL_LOCK_KEY_PATTERN.match(key), f"Should accept: {key}"
        assert is_valid_lock_key(key), f"is_valid_lock_key should accept: {key}"

    @pytest.mark.parametrize(
        "key",
        [
            "unknown:something",
            "INVALID:key",
        ],
    )
    def test_unrecognized_namespace_still_matches_pattern(self, key: str):
        # The regex only checks for known prefixes
        assert not LOGICAL_LOCK_KEY_PATTERN.match(key)

    @pytest.mark.parametrize(
        "key",
        [
            "",
            "   ",
        ],
    )
    def test_invalid_keys_rejected(self, key: str):
        assert not is_valid_lock_key(key)

    def test_bare_prefix_not_a_logical_key(self):
        # "api:" has no content after the colon — doesn't match logical key pattern
        assert not LOGICAL_LOCK_KEY_PATTERN.match("api:")


class TestFilePathPattern:
    """Verify that file path patterns accept repo-relative paths."""

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "tests/api/test_users.py",
            "contracts/openapi/v1.yaml",
            ".github/workflows/ci.yml",
        ],
    )
    def test_valid_file_paths(self, path: str):
        assert FILE_PATH_PATTERN.match(path), f"Should accept: {path}"
        assert is_valid_lock_key(path), f"is_valid_lock_key should accept: {path}"

    @pytest.mark.parametrize(
        "path",
        [
            "/absolute/path.py",  # Leading slash
        ],
    )
    def test_absolute_paths_rejected(self, path: str):
        assert not FILE_PATH_PATTERN.match(path), f"Should reject: {path}"


class TestLogicalLockKeyPrefixes:
    """Verify the prefix set is complete."""

    def test_all_documented_prefixes_present(self):
        expected = {"api:", "db:", "event:", "flag:", "env:", "contract:", "feature:"}
        assert LOGICAL_LOCK_KEY_PREFIXES == expected

    def test_prefixes_are_frozen(self):
        assert isinstance(LOGICAL_LOCK_KEY_PREFIXES, frozenset)


class TestIsValidLockKey:
    """Integration tests for is_valid_lock_key()."""

    def test_accepts_file_paths(self):
        assert is_valid_lock_key("src/api/users.py")

    def test_accepts_logical_keys(self):
        assert is_valid_lock_key("api:GET /v1/users")
        assert is_valid_lock_key("db:schema:users")
        assert is_valid_lock_key("feature:FEAT-123:pause")

    def test_rejects_empty(self):
        assert not is_valid_lock_key("")

    def test_rejects_whitespace_only(self):
        assert not is_valid_lock_key("   ")
