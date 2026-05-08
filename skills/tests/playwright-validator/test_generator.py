"""Tests for skills/playwright-validator/scripts/generator.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from generator import emit_playwright_config, emit_test_script
from parser import (
    PlaywrightAction,
    PlaywrightAssertion,
    TranslatedScenario,
)


def _scenario() -> TranslatedScenario:
    return TranslatedScenario(
        name="User logs in",
        requirement="Login Flow",
        actions=[
            PlaywrightAction(kind="goto", url="/"),
            PlaywrightAction(kind="fill", selector="#username", value="alice"),
            PlaywrightAction(kind="click", selector="#login-button"),
        ],
        assertions=[
            PlaywrightAssertion(selector="#welcome", matcher="toBeVisible"),
            PlaywrightAssertion(
                selector="#welcome",
                matcher="toContainText",
                expected="Welcome, alice",
            ),
        ],
        source_ref="spec.md:5-20",
    )


def test_emits_valid_typescript_structure(tmp_path: Path):
    descriptor = {
        "base_url": "http://127.0.0.1:8765",
        "selectors": {"username_field": "#username"},
        "auth_flow": [],
    }
    out = emit_test_script([_scenario()], descriptor, tmp_path / "x.spec.ts")
    text = out.read_text()
    assert "import { test, expect }" in text
    assert "@playwright/test" in text
    assert 'test("User logs in"' in text
    assert "page.goto" in text
    assert "page.fill" in text
    assert "page.click" in text
    assert "toBeVisible()" in text
    assert "toContainText" in text
    # Source ref preserved as comment for traceability.
    assert "// source: spec.md:5-20" in text


def test_no_scenarios_emits_skip_placeholder(tmp_path: Path):
    descriptor = {"selectors": {}, "auth_flow": []}
    out = emit_test_script([], descriptor, tmp_path / "x.spec.ts")
    text = out.read_text()
    assert "test.skip" in text


def test_auth_flow_resolves_env_vars(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("API_PASSWORD", "s3cret")
    descriptor = {
        "selectors": {},
        "auth_flow": [
            {"action": "goto", "url": "/login"},
            {"action": "fill", "selector": "#pw", "value": "${API_PASSWORD}"},
            {"action": "click", "selector": "#submit"},
        ],
    }
    out = emit_test_script([_scenario()], descriptor, tmp_path / "x.spec.ts")
    text = out.read_text()
    assert "test.beforeAll" in text
    # Resolved literal must be in the script; the ${...} placeholder must not.
    assert "s3cret" in text
    assert "${API_PASSWORD}" not in text


def test_emit_playwright_config(tmp_path: Path):
    descriptor = {
        "base_url": "http://127.0.0.1:8765",
        "viewport": {"width": 800, "height": 600},
    }
    cfg = emit_playwright_config(descriptor, tmp_path)
    text = cfg.read_text()
    assert "defineConfig" in text
    assert "baseURL" in text
    assert "127.0.0.1:8765" in text
    assert "800" in text
    assert "600" in text


def test_special_chars_in_test_name_are_escaped(tmp_path: Path):
    scenario = _scenario()
    scenario.name = "User \"clicks\" login"
    descriptor = {"selectors": {}, "auth_flow": []}
    out = emit_test_script([scenario], descriptor, tmp_path / "x.spec.ts")
    text = out.read_text()
    # Should be a valid JSON-encoded TypeScript string literal: the inner
    # double-quote becomes \" inside the surrounding "..." JSON literal.
    assert "test(" in text
    assert '\\"clicks\\"' in text
