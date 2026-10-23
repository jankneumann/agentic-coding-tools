"""``exclude_vendor`` accepts one vendor or a collection of them.

The merge skill excludes both the orchestrating vendor and the PR author's
vendor from review dispatch, so ``discover_reviewers`` (and everything that
forwards to it) takes a collection as well as the historical single string.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from review_dispatcher import CliConfig, CliVendorAdapter, ModeConfig, ReviewOrchestrator


def _adapter(agent_id: str, vendor: str, command: str) -> CliVendorAdapter:
    return CliVendorAdapter(
        agent_id=agent_id,
        vendor=vendor,
        cli_config=CliConfig(
            command=command,
            dispatch_modes={"review": ModeConfig(args=["review"])},
            model_flag="-m",
            model=None,
            model_fallbacks=[],
            api_key_env="",
        ),
    )


@pytest.fixture
def orch() -> ReviewOrchestrator:
    return ReviewOrchestrator({
        "codex-local": _adapter("codex-local", "codex", "codex"),
        "grok-local": _adapter("grok-local", "grok", "grok"),
        "gemini-local": _adapter("gemini-local", "gemini", "gemini"),
    })


def _vendors(orch: ReviewOrchestrator, exclude) -> list[str]:
    with patch("shutil.which", return_value="/usr/bin/mock"):
        return sorted(r.vendor for r in orch.discover_reviewers(exclude_vendor=exclude))


def test_string_excludes_one_vendor(orch: ReviewOrchestrator) -> None:
    assert _vendors(orch, "codex") == ["gemini", "grok"]


@pytest.mark.parametrize("exclude", [{"codex", "grok"}, frozenset({"codex", "grok"}), ["grok", "codex"], ("codex", "grok")])
def test_collection_excludes_each_member(orch: ReviewOrchestrator, exclude) -> None:
    assert _vendors(orch, exclude) == ["gemini"]


@pytest.mark.parametrize("exclude", [None, set(), ""])
def test_empty_exclusion_excludes_nothing(orch: ReviewOrchestrator, exclude) -> None:
    assert _vendors(orch, exclude) == ["codex", "gemini", "grok"]


def test_string_is_not_treated_as_a_character_set(orch: ReviewOrchestrator) -> None:
    # "grok" must not exclude a vendor named "g" or "r"; it names one vendor.
    assert _vendors(orch, "grokcodex") == ["codex", "gemini", "grok"]


def test_dispatch_and_wait_forwards_the_collection(orch: ReviewOrchestrator, tmp_path) -> None:
    seen: dict = {}

    def fake_discover(exclude_vendor=None, dispatch_mode="review"):
        seen["exclude_vendor"] = exclude_vendor
        return []

    with patch.object(orch, "discover_reviewers", side_effect=fake_discover):
        orch.dispatch_and_wait(
            review_type="pr", dispatch_mode="review", prompt="p", cwd=tmp_path,
            exclude_vendor={"claude_code", "codex"},
        )
    assert seen["exclude_vendor"] == {"claude_code", "codex"}
