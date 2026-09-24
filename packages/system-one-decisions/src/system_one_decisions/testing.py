"""Reusable pytest stubs for `decide`/`decide_intent`.

Design D2 of `add-the-adapter-backed-test-substitute-and-dry-run-policy`: a
thin, dependency-free layer over `monkeypatch.setattr` so every future
call-site migration unit-tests its own code against a controlled
`decide`/`decide_intent` result, without a real client, key, or network
access. `decide()` is the function that can genuinely return `None`
(the unavailable signal); `decide_intent()` never does -- it always wraps a
`Decision`, even in the fallback case -- so its stub returns a caller-chosen
`Decision` instead.

Importable with the package's default (no-extras) install: this module
depends only on `pytest`'s `MonkeyPatch` type for its signature, already a
`dev`-extra dependency of every consumer's own test suite.

**Usage caveat (a general monkeypatch limitation, not specific to this
module):** these helpers patch the attribute on the `system_one_decisions`
module object. Code under test must look the function up through that
module (`import system_one_decisions; system_one_decisions.decide(...)`) at
call time. Code that already did `from system_one_decisions import decide`
*before* the stub is applied keeps its own already-bound reference to the
original function — the patch never reaches it, because that name lookup
already happened. Import the module, not the name, in code you intend to
stub this way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

    from . import Decision


def stub_decide(monkeypatch: pytest.MonkeyPatch, *, returns: dict[str, Any] | None = None) -> None:
    """Patch `system_one_decisions.decide` to return `returns` (default `None`,
    the unavailable signal) for the duration of the current test."""
    import system_one_decisions

    monkeypatch.setattr(system_one_decisions, "decide", lambda *_a, **_kw: returns)


def stub_decide_intent(monkeypatch: pytest.MonkeyPatch, *, returns: Decision) -> None:
    """Patch `system_one_decisions.decide_intent` to return `returns`
    deterministically for the duration of the current test."""
    import system_one_decisions

    monkeypatch.setattr(system_one_decisions, "decide_intent", lambda *_a, **_kw: returns)
