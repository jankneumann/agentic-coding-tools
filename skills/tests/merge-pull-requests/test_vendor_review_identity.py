"""Vendor review summaries carry reviewer identity; the author's vendor is excluded.

Binding a verdict records who reviewed it, so each per-vendor summary must keep
the dispatcher's ``agent_id`` and ``model_used``. Independence starts at
dispatch: the PR author's vendor is excluded alongside the orchestrating
``claude_code`` lane.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-b", "main"], ["commit", "--allow-empty", "-m", "c1"]):
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
            capture_output=True, text=True, check=True,
        )
    monkeypatch.chdir(repo)
    monkeypatch.setenv("MERGE_VENDOR_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    return repo


def _install_fake(monkeypatch: pytest.MonkeyPatch, results: list) -> dict:
    import vendor_review

    seen: dict = {}

    class FakeOrchestrator:
        adapters = {"fake": object()}

        @classmethod
        def from_coordinator(cls) -> "FakeOrchestrator":
            return cls()

        def discover_reviewers(self, exclude_vendor=None):
            seen["discover"] = exclude_vendor
            return [SimpleNamespace(available=True)]

        def dispatch_and_wait(self, *, exclude_vendor=None, **_kwargs):
            seen["dispatch"] = exclude_vendor
            return results

    fake = ModuleType("review_dispatcher")
    fake.ReviewOrchestrator = FakeOrchestrator
    fake.ReviewResult = object
    monkeypatch.setitem(sys.modules, "review_dispatcher", fake)
    monkeypatch.setattr(vendor_review, "build_review_prompt", lambda *_a: "prompt")
    return seen


def _result(vendor: str, agent_id: str, model: str | None, success: bool = True):
    return SimpleNamespace(
        vendor=vendor, agent_id=agent_id, success=success, model_used=model,
        elapsed_seconds=1.0, error=None if success else "boom",
        findings={"findings": []} if success else None,
    )


def test_summaries_keep_agent_id_and_model(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import vendor_review

    _install_fake(monkeypatch, [
        _result("codex", "codex-local", "gpt-5"),
        _result("gemini", "gemini-local", None, success=False),
    ])

    review = vendor_review.dispatch_vendor_reviews(5, {"changed_lines": 100})

    by_vendor = {s["vendor"]: s for s in review["vendors"]}
    assert by_vendor["codex"]["agent_id"] == "codex-local"
    assert by_vendor["codex"]["model_used"] == "gpt-5"
    assert by_vendor["gemini"]["agent_id"] == "gemini-local"


def test_without_author_vendor_only_claude_code_is_excluded(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import vendor_review

    seen = _install_fake(monkeypatch, [])
    vendor_review.dispatch_vendor_reviews(5, {"changed_lines": 100})

    assert set(seen["discover"]) == {"claude_code"}
    assert set(seen["dispatch"]) == {"claude_code"}


def test_author_vendor_is_excluded_alongside_claude_code(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import vendor_review

    seen = _install_fake(monkeypatch, [])
    vendor_review.dispatch_vendor_reviews(5, {"changed_lines": 100}, author_vendor="codex")

    assert set(seen["discover"]) == {"claude_code", "codex"}
    assert set(seen["dispatch"]) == {"claude_code", "codex"}
