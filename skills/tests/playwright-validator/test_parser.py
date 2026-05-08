"""Tests for skills/playwright-validator/scripts/parser.py."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from parser import (
    PlaywrightAction,
    PlaywrightAssertion,
    TranslatedScenario,
    translate_openspec_scenario,
)


@dataclass
class _FakeScenario:
    """Duck-typed stand-in for ParsedScenario."""

    scenario_name: str
    requirement_name: str
    body: str
    source_ref: str = "spec.md:1-10"


SELECTORS = {
    "username_field": "#username",
    "password_field": "#password",
    "login_button": "#login-button",
    "welcome_message": "#welcome",
}


def test_translates_basic_login_flow():
    body = (
        "- **WHEN** the user navigates to the home page\n"
        "- **AND** the user fills username_field with \"alice\"\n"
        "- **AND** the user fills password_field with \"password\"\n"
        "- **AND** the user clicks login_button\n"
        "- **THEN** welcome_message is visible\n"
        "- **AND** welcome_message contains \"Welcome, alice\"\n"
    )
    scn = _FakeScenario("User logs in", "Login Flow", body, "spec.md:5-20")
    out = translate_openspec_scenario(scn, SELECTORS)
    assert isinstance(out, TranslatedScenario)
    assert out.name == "User logs in"
    assert out.source_ref == "spec.md:5-20"
    # 4 actions (1 goto + 2 fills + 1 click)
    assert [a.kind for a in out.actions] == ["goto", "fill", "fill", "click"]
    # Selectors expanded.
    assert out.actions[1].selector == "#username"
    assert out.actions[1].value == "alice"
    assert out.actions[2].selector == "#password"
    assert out.actions[3].selector == "#login-button"
    # 2 assertions (1 visible + 1 contains)
    assert [a.matcher for a in out.assertions] == ["toBeVisible", "toContainText"]
    assert out.assertions[0].selector == "#welcome"
    assert out.assertions[1].selector == "#welcome"
    assert out.assertions[1].expected == "Welcome, alice"


def test_unknown_selector_falls_through_verbatim():
    body = "- **WHEN** the user clicks unknown_alias\n"
    scn = _FakeScenario("x", "r", body)
    out = translate_openspec_scenario(scn, SELECTORS)
    assert out.actions[0].kind == "click"
    assert out.actions[0].selector == "unknown_alias"


def test_then_with_no_pattern_falls_back_to_text_locator():
    body = (
        "- **THEN** something interesting happens\n"
    )
    scn = _FakeScenario("x", "r", body)
    out = translate_openspec_scenario(scn, SELECTORS)
    assert len(out.assertions) == 1
    assert out.assertions[0].matcher == "toBeVisible"
    assert out.assertions[0].selector.startswith("text=")


def test_given_lines_produce_no_actions():
    body = (
        "- **GIVEN** a precondition\n"
        "- **WHEN** the user clicks login_button\n"
    )
    scn = _FakeScenario("x", "r", body)
    out = translate_openspec_scenario(scn, SELECTORS)
    assert len(out.actions) == 1
    assert out.actions[0].kind == "click"


def test_typescript_emission_for_action():
    a = PlaywrightAction(kind="fill", selector="#u", value="alice")
    line = a.to_typescript()
    assert "page.fill" in line
    assert '"#u"' in line
    assert '"alice"' in line


def test_typescript_emission_for_assertion():
    asn = PlaywrightAssertion(selector="#w", matcher="toContainText", expected="Hello")
    line = asn.to_typescript()
    assert "expect" in line
    assert "toContainText" in line
    assert '"Hello"' in line


def test_visible_assertion_typescript():
    asn = PlaywrightAssertion(selector="#x", matcher="toBeVisible")
    line = asn.to_typescript()
    assert "toBeVisible()" in line


def test_quoted_value_in_fill():
    body = '- **WHEN** the user fills username_field with "alice o\'malley"\n'
    scn = _FakeScenario("x", "r", body)
    out = translate_openspec_scenario(scn, SELECTORS)
    assert out.actions[0].value == "alice o'malley"


def test_navigates_to_home_page_becomes_root():
    body = "- **WHEN** the user navigates to the home page\n"
    scn = _FakeScenario("x", "r", body)
    out = translate_openspec_scenario(scn, SELECTORS)
    assert out.actions[0].kind == "goto"
    assert out.actions[0].url == "/"


def test_navigates_to_explicit_path():
    body = '- **WHEN** the user navigates to "/login"\n'
    scn = _FakeScenario("x", "r", body)
    out = translate_openspec_scenario(scn, SELECTORS)
    assert out.actions[0].kind == "goto"
    assert out.actions[0].url == "/login"


def test_dangling_and_with_no_preceding_when_or_then():
    body = "- **AND** dangling line\n"
    scn = _FakeScenario("x", "r", body)
    out = translate_openspec_scenario(scn, SELECTORS)
    assert out.actions == []
    assert out.assertions == []
