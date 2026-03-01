"""Tests for scope_checker module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from scope_checker import check_scope_compliance, get_modified_files_from_diff


class TestCheckScopeCompliance:
    def test_all_files_in_scope(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/api/users.py", "src/api/routes.py"],
            write_allow=["src/api/**"],
        )
        assert result["compliant"] is True
        assert result["violations"] == []
        assert result["files_checked"] == 2

    def test_file_outside_scope(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/api/users.py", "src/frontend/App.tsx"],
            write_allow=["src/api/**"],
        )
        assert result["compliant"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["file"] == "src/frontend/App.tsx"
        assert result["violations"][0]["reason"] == "not_in_write_allow"

    def test_file_in_deny_list(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/frontend/App.tsx"],
            write_allow=["src/**"],
            deny=["src/frontend/**"],
        )
        assert result["compliant"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["reason"] == "denied"
        assert result["violations"][0]["pattern"] == "src/frontend/**"

    def test_deny_overrides_allow(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/api/secrets.py"],
            write_allow=["src/api/**"],
            deny=["src/api/secrets.py"],
        )
        assert result["compliant"] is False
        assert result["violations"][0]["reason"] == "denied"

    def test_empty_files_modified(self) -> None:
        result = check_scope_compliance(
            files_modified=[],
            write_allow=["src/**"],
        )
        assert result["compliant"] is True
        assert result["files_checked"] == 0

    def test_multiple_write_allow_patterns(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/api/users.py", "tests/api/test_users.py"],
            write_allow=["src/api/**", "tests/api/**"],
        )
        assert result["compliant"] is True

    def test_wildcard_scope(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/anything.py", "tests/whatever.py"],
            write_allow=["**"],
        )
        assert result["compliant"] is True

    def test_mixed_violations(self) -> None:
        result = check_scope_compliance(
            files_modified=[
                "src/api/users.py",  # allowed
                "src/frontend/App.tsx",  # denied
                "config/secrets.env",  # outside scope
            ],
            write_allow=["src/api/**"],
            deny=["src/frontend/**"],
        )
        assert result["compliant"] is False
        assert len(result["violations"]) == 2
        reasons = {v["reason"] for v in result["violations"]}
        assert reasons == {"denied", "not_in_write_allow"}

    def test_summary_on_pass(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/api/users.py"],
            write_allow=["src/api/**"],
        )
        assert "passed" in result["summary"].lower()

    def test_summary_on_violation(self) -> None:
        result = check_scope_compliance(
            files_modified=["bad/file.py"],
            write_allow=["src/**"],
        )
        assert "violation" in result["summary"].lower()

    def test_no_deny_defaults_to_empty(self) -> None:
        result = check_scope_compliance(
            files_modified=["src/api/users.py"],
            write_allow=["src/api/**"],
        )
        assert result["compliant"] is True


class TestGetModifiedFilesFromDiff:
    def test_parses_multiline_output(self) -> None:
        diff_output = "src/api/users.py\nsrc/api/routes.py\ntests/test_users.py\n"
        files = get_modified_files_from_diff(diff_output)
        assert files == ["src/api/users.py", "src/api/routes.py", "tests/test_users.py"]

    def test_strips_whitespace(self) -> None:
        diff_output = "  src/api/users.py  \n  src/api/routes.py  \n"
        files = get_modified_files_from_diff(diff_output)
        assert files == ["src/api/users.py", "src/api/routes.py"]

    def test_empty_output(self) -> None:
        assert get_modified_files_from_diff("") == []
        assert get_modified_files_from_diff("  \n  \n") == []

    def test_single_file(self) -> None:
        files = get_modified_files_from_diff("src/main.py\n")
        assert files == ["src/main.py"]
