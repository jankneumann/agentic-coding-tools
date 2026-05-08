"""Tests for skills/playwright-validator/scripts/auth_flow.py."""

from __future__ import annotations

import pytest

from auth_flow import (
    MissingEnvVar,
    referenced_env_vars,
    resolve_value,
    validate_required_env_vars,
)


class TestReferencedEnvVars:
    def test_returns_distinct_vars_in_first_appearance_order(self):
        assert referenced_env_vars("a=${A} b=${B} a2=${A}") == ["A", "B"]

    def test_no_refs_returns_empty(self):
        assert referenced_env_vars("plain string") == []

    def test_lowercase_dollar_braces_are_ignored(self):
        # Schema regex is uppercase-only.
        assert referenced_env_vars("${lowercase}") == []

    def test_bare_dollar_var_is_ignored(self):
        assert referenced_env_vars("$VAR") == []


class TestResolveValue:
    def test_substitutes_present_var(self):
        assert resolve_value("hello ${USER}", {"USER": "alice"}) == "hello alice"

    def test_missing_var_raises_with_exact_name(self):
        with pytest.raises(MissingEnvVar) as exc:
            resolve_value("hello ${MISSING_VAR}", {})
        assert exc.value.var_name == "MISSING_VAR"
        assert "MISSING_VAR" in str(exc.value)
        assert "auth_flow" in str(exc.value)

    def test_no_refs_passes_through_unchanged(self):
        assert resolve_value("plain", {}) == "plain"

    def test_does_not_invoke_shell(self):
        # If the implementation shelled out, $(echo) would expand.
        # Verify it stays literal.
        out = resolve_value("$(echo unsafe)", {})
        assert out == "$(echo unsafe)"

    def test_bare_dollar_var_passes_through(self):
        out = resolve_value("$BARE_VAR", {"BARE_VAR": "x"})
        # ${VAR} substitution only — $BARE_VAR is left alone.
        assert out == "$BARE_VAR"


class TestValidateRequiredEnvVars:
    def test_all_required_present_passes(self):
        descriptor = {
            "env_vars_required": ["A", "B"],
            "auth_flow": [],
        }
        validate_required_env_vars(descriptor, env={"A": "1", "B": "2"})

    def test_missing_required_raises(self):
        descriptor = {"env_vars_required": ["MISSING_VAR"], "auth_flow": []}
        with pytest.raises(MissingEnvVar) as exc:
            validate_required_env_vars(descriptor, env={})
        assert exc.value.var_name == "MISSING_VAR"

    def test_auth_flow_value_missing_var_raises(self):
        descriptor = {
            "env_vars_required": [],
            "auth_flow": [
                {"action": "fill", "selector": "#u", "value": "${PW}"},
            ],
        }
        with pytest.raises(MissingEnvVar) as exc:
            validate_required_env_vars(descriptor, env={})
        assert exc.value.var_name == "PW"

    def test_auth_flow_with_resolved_var_passes(self):
        descriptor = {
            "env_vars_required": [],
            "auth_flow": [
                {"action": "fill", "selector": "#u", "value": "${PW}"},
            ],
        }
        validate_required_env_vars(descriptor, env={"PW": "secret"})

    def test_empty_descriptor_passes(self):
        validate_required_env_vars({}, env={})
