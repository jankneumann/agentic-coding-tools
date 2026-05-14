"""OpenSpec scenario -> Playwright action/assertion translator.

Reads ``ParsedScenario`` objects produced by
``agent-coordinator/evaluation/gen_eval/openspec_seed.py`` and maps the
WHEN/AND/THEN bullet structure to Playwright actions and assertions.

The translator is intentionally pattern-based (not LLM-driven) so the
generated test scripts are reproducible and reviewable. Recognized patterns
match the spec scenario "Sample frontend exercise validates the full path":

* ``When the user navigates to <url>`` -> ``page.goto(<url>)``
* ``When the user clicks <selector>`` -> ``page.click(<selector>)``
* ``When the user fills <selector> with <value>`` -> ``page.fill(<selector>, <value>)``
* ``Then <selector> is visible`` -> ``expect(page.locator(<selector>)).toBeVisible()``
* ``Then <selector> contains <text>`` -> ``expect(page.locator(<selector>)).toContainText(<text>)``

Selector aliases from the descriptor's ``selectors`` map are expanded to
their literal CSS form before script emission so that descriptor edits do
not require rewriting scenarios.

This module deliberately avoids importing from agent-coordinator; the
``ParsedScenario`` dataclass is duck-typed (we only need ``.scenario_name``,
``.requirement_name``, ``.body``, and ``.source_ref``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Result data model
# ---------------------------------------------------------------------------


@dataclass
class PlaywrightAction:
    """A single Playwright page action (goto / click / fill / wait)."""

    kind: str  # goto | click | fill | wait_for_selector
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    raw: str = ""

    def to_typescript(self) -> str:
        """Emit the action as a Playwright TypeScript line."""
        if self.kind == "goto":
            return f"  await page.goto({_ts_str(self.url or '/')});"
        if self.kind == "click":
            return f"  await page.click({_ts_str(self.selector or '')});"
        if self.kind == "fill":
            return (
                f"  await page.fill({_ts_str(self.selector or '')},"
                f" {_ts_str(self.value or '')});"
            )
        if self.kind == "wait_for_selector":
            return (
                f"  await page.waitForSelector({_ts_str(self.selector or '')});"
            )
        # Defensive: unknown kind -> emit a comment so the generated script
        # remains syntactically valid.
        return f"  // unhandled action: {_ts_str(self.raw)}"


@dataclass
class PlaywrightAssertion:
    """A single Playwright expect-assertion."""

    selector: str
    matcher: str  # toBeVisible | toContainText | toHaveText | toBeHidden
    expected: str | None = None
    raw: str = ""

    def to_typescript(self) -> str:
        loc = f"page.locator({_ts_str(self.selector)})"
        if self.matcher in {"toBeVisible", "toBeHidden"}:
            return f"  await expect({loc}).{self.matcher}();"
        if self.matcher in {"toContainText", "toHaveText"}:
            return (
                f"  await expect({loc}).{self.matcher}"
                f"({_ts_str(self.expected or '')});"
            )
        return f"  // unhandled assertion: {_ts_str(self.raw)}"


@dataclass
class TranslatedScenario:
    """A Playwright-ready translation of a single OpenSpec scenario."""

    name: str
    requirement: str
    actions: list[PlaywrightAction] = field(default_factory=list)
    assertions: list[PlaywrightAssertion] = field(default_factory=list)
    source_ref: str = ""  # "<file>:<start>-<end>" for findings.location

    @property
    def test_name(self) -> str:
        """Stable Playwright test name (used by the generator).

        Replaces characters that are awkward inside a string literal.
        """
        return self.name.replace("'", "\\'")


# ---------------------------------------------------------------------------
# Pattern matchers
# ---------------------------------------------------------------------------


_BULLET_RE = re.compile(
    r"^\s*-\s+\*\*(?P<keyword>WHEN|AND|THEN|GIVEN)\*\*\s+(?P<text>.+?)\s*$",
    re.IGNORECASE,
)

_GOTO_RE = re.compile(
    r"the user navigates to (?:the )?(?P<target>.+?)\s*$", re.IGNORECASE
)
# "fills X with Y" — Y is captured verbatim (may be quoted)
_FILL_RE = re.compile(
    r"the user fills (?P<sel>\S+) with (?P<val>.+?)\s*$", re.IGNORECASE
)
_CLICK_RE = re.compile(
    r"the user clicks (?:on )?(?P<sel>\S+)\s*$", re.IGNORECASE
)
_WAIT_RE = re.compile(
    r"the user waits for (?P<sel>\S+)\s*$", re.IGNORECASE
)
_VISIBLE_RE = re.compile(
    r"(?P<sel>\S+) (?:is|should be) visible\s*$", re.IGNORECASE
)
_HIDDEN_RE = re.compile(
    r"(?P<sel>\S+) (?:is|should be) hidden\s*$", re.IGNORECASE
)
_CONTAINS_RE = re.compile(
    r"(?P<sel>\S+) contains (?P<text>.+?)\s*$", re.IGNORECASE
)
_HAS_TEXT_RE = re.compile(
    r"(?P<sel>\S+) has text (?P<text>.+?)\s*$", re.IGNORECASE
)


def _strip_quotes(value: str) -> str:
    """Remove a surrounding pair of single or double quotes if present."""
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', "'"}:
        return s[1:-1]
    return s


def _expand_selector(token: str, selectors: Mapping[str, str]) -> str:
    """Resolve a selector token through the descriptor's selectors map.

    Strips a single layer of surrounding quotes (so scenarios MAY quote
    aliases for clarity). Falls back to the token verbatim if no alias
    matches -- this lets scenarios use literal CSS as well.
    """
    raw = _strip_quotes(token)
    return selectors.get(raw, raw)


def _ts_str(value: str) -> str:
    """JSON-escape a Python string for safe embedding in TypeScript source.

    Using JSON encoding gives us the right escapes for quotes, backslashes,
    and control characters; TypeScript accepts JSON-style double-quoted
    strings.
    """
    import json as _json

    return _json.dumps(value)


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------


def translate_openspec_scenario(
    scenario: Any,
    selectors: Mapping[str, str] | None = None,
) -> TranslatedScenario:
    """Translate one ``ParsedScenario`` into a :class:`TranslatedScenario`.

    Recognized patterns are listed in the module docstring. Any bullet that
    doesn't match falls back to a comment in the action stream (preserving
    the source for human review without breaking the generator).

    Args:
        scenario: A duck-typed object exposing ``scenario_name``,
            ``requirement_name``, ``body`` (str), and ``source_ref`` (str).
            ``ParsedScenario`` from ``openspec_seed.py`` matches.
        selectors: Optional descriptor ``selectors`` map for alias expansion.

    Returns:
        A :class:`TranslatedScenario` with separated actions/assertions.
    """
    selectors = selectors or {}

    name = getattr(scenario, "scenario_name", None) or getattr(
        scenario, "name", "unnamed"
    )
    requirement = getattr(scenario, "requirement_name", "")
    body = getattr(scenario, "body", "") or ""
    source_ref = getattr(scenario, "source_ref", "")

    actions: list[PlaywrightAction] = []
    assertions: list[PlaywrightAssertion] = []

    # Track the most-recent keyword so AND lines can inherit context.
    current_kind: str | None = None  # "action" | "assertion"

    for raw_line in body.splitlines():
        bullet = _BULLET_RE.match(raw_line)
        if not bullet:
            continue
        keyword = bullet.group("keyword").upper()
        text = bullet.group("text").strip()

        if keyword == "GIVEN":
            # GIVEN lines describe preconditions; they do not become
            # actions or assertions in the generated script.
            current_kind = None
            continue

        if keyword == "WHEN":
            current_kind = "action"
            _emit_action(text, selectors, actions)
            continue

        if keyword == "THEN":
            current_kind = "assertion"
            _emit_assertion(text, selectors, assertions)
            continue

        if keyword == "AND":
            # AND inherits the immediately preceding keyword's bucket.
            if current_kind == "action":
                _emit_action(text, selectors, actions)
            elif current_kind == "assertion":
                _emit_assertion(text, selectors, assertions)
            # else: dangling AND with no preceding WHEN/THEN — skip.
            continue

    return TranslatedScenario(
        name=name,
        requirement=requirement,
        actions=actions,
        assertions=assertions,
        source_ref=source_ref,
    )


def _emit_action(
    text: str,
    selectors: Mapping[str, str],
    out: list[PlaywrightAction],
) -> None:
    """Match ``text`` against the WHEN-pattern set and append to ``out``."""
    if (m := _GOTO_RE.match(text)):
        url = _strip_quotes(m.group("target"))
        # "home page" / "the home page" -> "/"
        if url.lower() in {"home page", "the home page", "/"}:
            url = "/"
        out.append(PlaywrightAction(kind="goto", url=url, raw=text))
        return

    if (m := _FILL_RE.match(text)):
        sel = _expand_selector(m.group("sel"), selectors)
        val = _strip_quotes(m.group("val"))
        out.append(
            PlaywrightAction(kind="fill", selector=sel, value=val, raw=text)
        )
        return

    if (m := _CLICK_RE.match(text)):
        sel = _expand_selector(m.group("sel"), selectors)
        out.append(PlaywrightAction(kind="click", selector=sel, raw=text))
        return

    if (m := _WAIT_RE.match(text)):
        sel = _expand_selector(m.group("sel"), selectors)
        out.append(
            PlaywrightAction(
                kind="wait_for_selector", selector=sel, raw=text
            )
        )
        return

    # Unknown WHEN — record as a comment-style action.
    out.append(PlaywrightAction(kind="unknown", raw=text))


def _emit_assertion(
    text: str,
    selectors: Mapping[str, str],
    out: list[PlaywrightAssertion],
) -> None:
    """Match ``text`` against the THEN-pattern set and append to ``out``."""
    if (m := _VISIBLE_RE.match(text)):
        sel = _expand_selector(m.group("sel"), selectors)
        out.append(
            PlaywrightAssertion(
                selector=sel, matcher="toBeVisible", raw=text
            )
        )
        return

    if (m := _HIDDEN_RE.match(text)):
        sel = _expand_selector(m.group("sel"), selectors)
        out.append(
            PlaywrightAssertion(
                selector=sel, matcher="toBeHidden", raw=text
            )
        )
        return

    if (m := _CONTAINS_RE.match(text)):
        sel = _expand_selector(m.group("sel"), selectors)
        expected = _strip_quotes(m.group("text"))
        out.append(
            PlaywrightAssertion(
                selector=sel,
                matcher="toContainText",
                expected=expected,
                raw=text,
            )
        )
        return

    if (m := _HAS_TEXT_RE.match(text)):
        sel = _expand_selector(m.group("sel"), selectors)
        expected = _strip_quotes(m.group("text"))
        out.append(
            PlaywrightAssertion(
                selector=sel,
                matcher="toHaveText",
                expected=expected,
                raw=text,
            )
        )
        return

    # Unknown THEN — fall back to a presence check on a text selector so
    # the generated test still expresses *some* assertion.
    out.append(
        PlaywrightAssertion(
            selector=f"text={_strip_quotes(text)}",
            matcher="toBeVisible",
            raw=text,
        )
    )


__all__ = [
    "PlaywrightAction",
    "PlaywrightAssertion",
    "TranslatedScenario",
    "translate_openspec_scenario",
]
