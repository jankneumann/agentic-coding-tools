"""Tests for decide()'s unconditional stub behavior in this item.

Spec: specs/system-one-decisions/spec.md
  "decide() is an unconditional stub with a stable signature"
Design: design.md D3.
"""

from __future__ import annotations

import socket

import pytest
from system_one_decisions import decide


def _blocked_socket(*args: object, **kwargs: object) -> None:
    raise AssertionError("decide() must not open a network socket in this item")


@pytest.mark.parametrize(
    "state,questions,site",
    [
        ({}, {}, "test-site"),
        ({"k": "v" * 10_000}, {"q1": "Choice"}, "another-site"),
        ({"nested": {"a": [1, 2, 3]}}, {}, ""),
    ],
)
def test_decide_always_returns_none(
    state: dict, questions: dict, site: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "socket", _blocked_socket)
    assert decide(state, questions, site=site) is None
