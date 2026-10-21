"""Supervisor execution-profile ranking (D8) and apply-time spend replay (D4).

openrouter-review-lane, task group 6.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SUITE = Path(__file__).resolve().parent
if str(_SUITE) not in sys.path:
    sys.path.insert(0, str(_SUITE))

from test_execution import (  # noqa: E402
    FakeClock,
    _REPO_ROOT,
    _adapter,
    _attempt,
    _launch,
    _prepare,
    _result,
    _workspace,
)

import execution  # noqa: E402
from execution import resolve_execution_profile  # noqa: E402

_LADDER = ["vendor-cli", "vendor-sdk", "openrouter"]


def _report(review: dict[str, Any]) -> tuple[int, str]:
    return 0, json.dumps(
        {
            "modes": {"review": review},
            "probe_command": "review_dispatcher.py --check-vendors --json",
        }
    )


@pytest.fixture(autouse=True)
def _fixed_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution, "_tier_order", lambda: list(_LADDER))


# --------------------------------------------------------------------------- #
# 6.1 / 6.2 — ranking reads lane_kinds (design D8)
# --------------------------------------------------------------------------- #


def test_a_verified_openrouter_lane_is_ranked_as_metered() -> None:
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["claude_code", "openrouter"],
                "unverified": [],
                "lane_kinds": {"claude_code": "vendor-cli", "openrouter": "openrouter"},
            }
        )
    )
    assert requirements["counting_lanes"] == ["claude_code", "openrouter"]
    assert set(requirements["min_quorum"].values()) == {2}


def test_lane_kinds_rank_openrouter_after_an_unverified_vendor_cli_lane() -> None:
    # The old inference treats every lane without ``probe_unsupported`` as
    # vendor-cli, so a verified openrouter lane would outrank an unverified CLI
    # lane. With lane_kinds the cost ladder decides.
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["openrouter"],
                "unverified": [{"vendor": "codex", "reason": "cli_not_found"}],
                "lane_kinds": {"openrouter": "openrouter", "codex": "vendor-cli"},
            }
        )
    )
    assert requirements["counting_lanes"] == ["codex", "openrouter"]


def test_lane_kinds_order_follows_the_whole_ladder() -> None:
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["openrouter", "local", "gemini", "claude_code"],
                "unverified": [],
                "lane_kinds": {
                    "openrouter": "openrouter",
                    "local": "local",
                    "gemini": "vendor-sdk",
                    "claude_code": "vendor-cli",
                },
            }
        )
    )
    # ``local`` is not on the ladder, so it sorts after every rung.
    assert requirements["counting_lanes"] == ["claude_code", "gemini", "openrouter", "local"]


def test_a_report_without_lane_kinds_still_ranks_by_the_old_inference() -> None:
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["openrouter"],
                "unverified": [
                    {"vendor": "codex", "reason": "cli_not_found"},
                    {"vendor": "gemini", "reason": "probe_unsupported"},
                ],
            }
        )
    )
    # vendor-cli verified, vendor-cli unverified, then the vendor-sdk lane.
    assert requirements["counting_lanes"] == ["openrouter", "codex", "gemini"]


def test_prepare_succeeds_with_a_report_without_lane_kinds(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    adapter.profile_probe = lambda _repo: _report(
        {"verified": ["claude_code", "codex"], "unverified": []}
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    assert request["review_requirements"]["counting_lanes"] == ["claude_code", "codex"]


# --------------------------------------------------------------------------- #
# 6.3 — apply replays unrecorded metered spend once (design D4)
# --------------------------------------------------------------------------- #

_UNRECORDED = {
    "code": "metered_spend_unrecorded",
    "phase": "PLAN_REVIEW",
    "detail": "openrouter spend spooled; coordinator write failed",
}


def _allow_unrecorded_code(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the result schema accept the code while task 5.3 is unmerged.

    The enum value lands with task 5.3. Until it is on this branch, the fixture
    repository carries a result-schema copy with the value, and every schema
    lookup (including the repo-less attempt validation) prefers that copy.
    Once the real schema has the value this is a no-op.
    """
    from shared import dispatch_contract

    source = _REPO_ROOT / "openspec" / "schemas" / "dispatch-result.schema.json"
    schema = json.loads(source.read_text(encoding="utf-8"))
    codes = schema["$defs"]["Degradation"]["properties"]["code"]["enum"]
    if _UNRECORDED["code"] in codes:
        return
    codes.append(_UNRECORDED["code"])
    (repo / "openspec" / "schemas" / "dispatch-result.schema.json").write_text(
        json.dumps(schema, indent=2) + "\n", encoding="utf-8"
    )
    original = dispatch_contract._openspec_roots
    fixture_root = repo / "openspec"

    def roots(repo_root: Any) -> list[Path]:
        return [fixture_root, *[r for r in original(repo_root) if r != fixture_root]]

    _clear_schema_caches_now()
    monkeypatch.setattr(dispatch_contract, "_openspec_roots", roots)


def _clear_schema_caches_now() -> None:
    from shared import dispatch_contract

    dispatch_contract._registry_for.cache_clear()
    dispatch_contract._validator_for.cache_clear()


@pytest.fixture(autouse=True)
def _clear_schema_caches() -> Any:
    # Validators cached under the patched roots must not leak into other tests.
    yield
    _clear_schema_caches_now()


def _apply_with(
    tmp_path: Path,
    degradations: list[dict[str, Any]],
    replayer: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    repo, workspace, managed_root = _workspace(tmp_path)
    _allow_unrecorded_code(repo, monkeypatch)
    adapter = _adapter(managed_root, FakeClock())
    adapter.spend_replayer = replayer
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    _launch(adapter, workspace, request)
    result = _result("success-result.json", request)
    result["degradations"] = degradations
    applied = adapter.apply(
        workspace,
        batch_id=request["dispatch_id"].split(":", 1)[0],
        results=[result],
        dispatch_fn=lambda _item, _phase, context: context["dispatch_result"],
        repo_root=repo,
    )
    return applied, workspace, request


def test_unrecorded_spend_is_replayed_once_on_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path]] = []

    def replayer(change_id: str, root: Path) -> dict[str, Any]:
        calls.append((change_id, root))
        return {"replayed": 2, "already_recorded": 0, "remaining": 0, "malformed": 0}

    # Two degradations of the code still mean one replay per change.
    second = {**_UNRECORDED, "phase": "IMPL_REVIEW"}
    applied, workspace, request = _apply_with(tmp_path, [_UNRECORDED, second], replayer, monkeypatch)

    assert len(calls) == 1
    change_id, root = calls[0]
    assert change_id == request["change_id"]
    # The spool lives in the child's worktree, where the review ran.
    assert root == (tmp_path / "repo" / ".git-worktrees" / "change-alpha").resolve()
    assert applied["spend_replay"] == {
        request["dispatch_id"]: {
            "change_id": request["change_id"],
            "replayed": 2,
            "already_recorded": 0,
            "remaining": 0,
            "malformed": 0,
        }
    }
    assert _attempt(workspace)["degradations"] == [_UNRECORDED, second]


def test_no_replay_without_the_degradation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    applied, _workspace_path, _request = _apply_with(
        tmp_path,
        [{"code": "single_vendor_review", "phase": "PLAN_REVIEW", "detail": "codex down"}],
        lambda change_id, _root: calls.append(change_id) or {},
        monkeypatch,
    )
    assert calls == []
    assert applied["spend_replay"] == {}


def test_a_replay_error_never_fails_the_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def replayer(_change_id: str, _root: Path) -> dict[str, Any]:
        raise RuntimeError("coordinator unreachable")

    applied, workspace, request = _apply_with(tmp_path, [_UNRECORDED], replayer, monkeypatch)

    outcome = applied["spend_replay"][request["dispatch_id"]]
    assert outcome["change_id"] == request["change_id"]
    assert "coordinator unreachable" in outcome["error"]
    assert _attempt(workspace)["degradations"] == [_UNRECORDED]
    assert applied["degradations"] == {request["dispatch_id"]: [_UNRECORDED]}


def test_the_default_replayer_runs_the_spend_recorder_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    seen: list[list[str]] = []

    class Completed:
        returncode = 1
        stdout = json.dumps({"replayed": 1, "already_recorded": 0, "remaining": 1, "malformed": 0})
        stderr = ""

    def fake_run(argv: list[str], **_kwargs: Any) -> Completed:
        seen.append(list(argv))
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    outcome = execution._run_spend_replay("change-alpha", tmp_path)

    assert seen and seen[0][1].endswith("parallel-infrastructure/scripts/spend_recorder.py")
    assert seen[0][2:] == [
        "replay",
        "--change-id",
        "change-alpha",
        "--repo-root",
        str(tmp_path),
        "--json",
    ]
    # Exit 1 means rows remain; that is an outcome, not an error.
    assert outcome == {"replayed": 1, "already_recorded": 0, "remaining": 1, "malformed": 0}


def test_the_default_replayer_reports_an_unparseable_run_as_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    class Completed:
        returncode = 2
        stdout = ""
        stderr = "spend_recorder: invalid change id"

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: Completed())
    with pytest.raises(RuntimeError, match="exit 2"):
        execution._run_spend_replay("change-alpha", tmp_path)
