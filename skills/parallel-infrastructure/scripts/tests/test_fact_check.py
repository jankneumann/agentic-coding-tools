"""Tests for the diff-grounded fact-check pass (fact_check.py)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import fact_check  # noqa: E402


def _finding(**overrides) -> dict:
    doc = {
        "id": "f-1",
        "type": "correctness",
        "criticality": "high",
        "description": "Variable `used_variable` is declared but never used.",
        "disposition": "fix",
        "axis": "correctness",
        "severity": "critical",
        "file_path": "src/foo.py",
    }
    doc.update(overrides)
    return doc


class TestProtectedSubject:
    def test_memory_safety_is_protected(self) -> None:
        f = _finding(description="Possible buffer overflow when writing past the array bound.")
        assert fact_check.protected_subject(f) == "memory_safety"

    def test_concurrency_is_protected(self) -> None:
        f = _finding(description="This introduces a data race on the shared counter.")
        assert fact_check.protected_subject(f) == "concurrency"

    def test_unused_parameter_is_protected(self) -> None:
        f = _finding(description="The `ctx` parameter is never used in this function.")
        assert fact_check.protected_subject(f) == "unused_parameter"

    def test_ordinary_finding_is_not_protected(self) -> None:
        f = _finding(description="Prefer a list comprehension here for readability.")
        assert fact_check.protected_subject(f) is None


class TestParseVerdict:
    def test_approve_all(self) -> None:
        tool, items = fact_check.parse_verdict('{"tool": "approve_all_comments"}')
        assert tool == "approve_all_comments"
        assert items == []

    def test_report_incorrect_comments(self) -> None:
        raw = json.dumps(
            {
                "tool": "report_incorrect_comments",
                "items": [
                    {
                        "finding_id": "f-1",
                        "ground": "B_contradicted_by_diff_line",
                        "evidence_line": "+used_variable = compute()",
                    }
                ],
            }
        )
        tool, items = fact_check.parse_verdict(raw)
        assert tool == "report_incorrect_comments"
        assert items[0]["finding_id"] == "f-1"

    def test_strips_markdown_fence(self) -> None:
        raw = '```json\n{"tool": "approve_all_comments"}\n```'
        tool, _items = fact_check.parse_verdict(raw)
        assert tool == "approve_all_comments"

    def test_prose_before_json_is_tolerated(self) -> None:
        raw = 'Here is my answer:\n{"tool": "approve_all_comments"}'
        tool, _items = fact_check.parse_verdict(raw)
        assert tool == "approve_all_comments"

    def test_unrecognized_tool_raises(self) -> None:
        with pytest.raises(ValueError):
            fact_check.parse_verdict('{"tool": "something_else"}')

    def test_no_json_raises(self) -> None:
        with pytest.raises(ValueError):
            fact_check.parse_verdict("I don't know.")

    def test_missing_items_raises(self) -> None:
        with pytest.raises(ValueError):
            fact_check.parse_verdict('{"tool": "report_incorrect_comments"}')


class TestRun:
    def test_provably_wrong_finding_is_removed_with_evidence(self) -> None:
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {
                            "finding_id": "f-1",
                            "ground": "B_contradicted_by_diff_line",
                            "evidence_line": "+used_variable = compute()",
                        }
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="+used_variable = compute()", caller=caller,
        )
        assert outcome.status == "ran"
        assert outcome.kept_findings == []
        assert outcome.removed_count == 1
        assert outcome.decisions[0].verdict == "removed"
        assert outcome.decisions[0].ground == "B_contradicted_by_diff_line"
        assert outcome.decisions[0].evidence_line == "+used_variable = compute()"

    def test_protected_subject_survives_a_wrong_verdict(self) -> None:
        findings = [
            _finding(
                id="f-1",
                description="This introduces a data race on the shared counter.",
            )
        ]

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {
                            "finding_id": "f-1",
                            "ground": "A_absent_from_subject_diff",
                            "evidence_line": "n/a",
                        }
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=caller,
        )
        assert outcome.status == "ran"
        assert outcome.removed_count == 0
        assert outcome.kept_findings == findings
        assert outcome.decisions[0].verdict == "vetoed"
        assert outcome.decisions[0].vetoed == "protected_subject"

    def test_caller_failure_removes_nothing(self) -> None:
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            raise TimeoutError("model call timed out")

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=caller,
        )
        assert outcome.status == "skipped"
        assert outcome.kept_findings == findings
        assert "TimeoutError" in (outcome.skip_reason or "")

    def test_unparsable_response_removes_nothing(self) -> None:
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            return "not json at all"

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=caller,
        )
        assert outcome.status == "skipped"
        assert outcome.kept_findings == findings
        assert "unparsable_response" in (outcome.skip_reason or "")

    def test_no_caller_available_skips(self) -> None:
        findings = [_finding(id="f-1")]
        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=None,
        )
        assert outcome.status == "skipped"
        assert outcome.skip_reason == "no_caller_available"
        assert outcome.kept_findings == findings

    def test_disabled_keeps_everything_without_calling(self) -> None:
        calls = []

        def caller(_system: str, _user: str) -> str:
            calls.append(1)
            return json.dumps({"tool": "approve_all_comments"})

        findings = [_finding(id="f-1")]
        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=caller, enabled=False,
        )
        assert outcome.status == "disabled"
        assert outcome.kept_findings == findings
        assert calls == []

    def test_no_findings_short_circuits(self) -> None:
        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=[],
            packet_diff="irrelevant", caller=lambda s, u: "unused",
        )
        assert outcome.status == "skipped"
        assert outcome.skip_reason == "no_findings"

    def test_approve_all_keeps_everything(self) -> None:
        findings = [_finding(id="f-1"), _finding(id="f-2")]

        def caller(_system: str, _user: str) -> str:
            return json.dumps({"tool": "approve_all_comments"})

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=caller,
        )
        assert outcome.status == "ran"
        assert outcome.kept_findings == findings
        assert outcome.removed_count == 0
        assert all(d.verdict == "kept" for d in outcome.decisions)

    def test_removal_is_never_silent_decision_file_records_it(self, tmp_path) -> None:
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {
                            "finding_id": "f-1",
                            "ground": "B_contradicted_by_diff_line",
                            "evidence_line": "+used_variable = compute()",
                        }
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=2, findings=findings,
            packet_diff="+used_variable = compute()", caller=caller,
        )
        path = fact_check.write_decision_file(tmp_path, outcome)
        assert path.name == "fact-check-codex.json"
        doc = json.loads(path.read_text())
        assert doc["schema_version"] == 1
        assert doc["vendor"] == "codex"
        assert doc["round"] == 2
        assert doc["status"] == "ran"
        assert doc["decisions"][0]["finding_id"] == "f-1"
        assert doc["decisions"][0]["verdict"] == "removed"
        assert doc["decisions"][0]["evidence_line"] == "+used_variable = compute()"

    def test_ground_b_removal_requires_evidence_line(self) -> None:
        """A Ground B item with no evidence_line at all must not remove
        anything — the contracted evidence field is what makes the verdict
        falsifiable in the first place."""
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {"finding_id": "f-1", "ground": "B_contradicted_by_diff_line"}
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="+used_variable = compute()", caller=caller,
        )
        assert outcome.removed_count == 0
        assert outcome.kept_findings == findings
        assert outcome.decisions[0].verdict == "kept"

    def test_ground_b_removal_rejects_fabricated_evidence_line(self) -> None:
        """A Ground B item whose evidence_line does not actually appear in
        the diff must not remove the finding — a hallucinated citation
        cannot be allowed to discard a valid finding."""
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {
                            "finding_id": "f-1",
                            "ground": "B_contradicted_by_diff_line",
                            "evidence_line": "this line does not exist anywhere",
                        }
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="+used_variable = compute()", caller=caller,
        )
        assert outcome.removed_count == 0
        assert outcome.kept_findings == findings
        assert outcome.decisions[0].verdict == "kept"

    def test_ground_b_removal_verifies_evidence_scoped_to_subject_file(self) -> None:
        """The cited line must appear in the finding's own subject file's
        diff hunk, not merely somewhere in the whole multi-file packet —
        citing a line from an unrelated file must not remove a finding."""
        findings = [_finding(id="f-1", file_path="src/foo.py")]
        packet_diff = (
            "diff --git a/src/foo.py b/src/foo.py\n"
            "--- a/src/foo.py\n+++ b/src/foo.py\n"
            "@@ -1,1 +1,1 @@\n-old_line()\n+new_line()\n"
            "diff --git a/src/other.py b/src/other.py\n"
            "--- a/src/other.py\n+++ b/src/other.py\n"
            "@@ -1,1 +1,1 @@\n-used_variable = compute()\n+used_variable = compute(2)\n"
        )

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {
                            "finding_id": "f-1",
                            "ground": "B_contradicted_by_diff_line",
                            "evidence_line": "-used_variable = compute()",
                        }
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff=packet_diff, caller=caller,
        )
        assert outcome.removed_count == 0
        assert outcome.kept_findings == findings

    def test_ground_a_removal_does_not_require_evidence_line(self) -> None:
        """Ground A (code absent from the diff) has no line to cite by
        nature — it must not be held to Ground B's evidence requirement."""
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {"finding_id": "f-1", "ground": "A_absent_from_subject_diff"}
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="totally unrelated diff content", caller=caller,
        )
        assert outcome.removed_count == 1
        assert outcome.decisions[0].verdict == "removed"

    def test_unknown_finding_id_in_verdict_is_ignored(self) -> None:
        findings = [_finding(id="f-1")]

        def caller(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "tool": "report_incorrect_comments",
                    "items": [
                        {
                            "finding_id": "f-does-not-exist",
                            "ground": "B_contradicted_by_diff_line",
                            "evidence_line": "n/a",
                        }
                    ],
                }
            )

        outcome = fact_check.run(
            vendor="codex", round_num=1, findings=findings,
            packet_diff="irrelevant", caller=caller,
        )
        assert outcome.kept_findings == findings
        assert outcome.decisions[0].verdict == "kept"


class TestBuildDefaultCaller:
    def test_returns_none_when_binary_missing(self, tmp_path) -> None:
        class FakeCliConfig:
            command = "definitely-not-a-real-binary-xyz"
            model_flag = "--model"
            prompt_via_stdin = True

        caller = fact_check.build_default_caller(
            FakeCliConfig(), "nowhere-vendor", cwd=tmp_path,
        )
        assert caller is None


class _ModeConfig:
    def __init__(self, args, async_dispatch=False, isolation=None) -> None:
        self.args = args
        self.async_dispatch = async_dispatch
        self.isolation = isolation


class _FakeCliConfig:
    def __init__(
        self, command, dispatch_modes, model_flag="--model", prompt_via_stdin=True,
    ) -> None:
        self.command = command
        self.dispatch_modes = dispatch_modes
        self.model_flag = model_flag
        self.prompt_via_stdin = prompt_via_stdin


class TestBuildDefaultCallerVendorFlags:
    """Each vendor's own alternative/quick mode drives the caller's flags —
    not a single Claude-shaped hard-coded command (regression coverage for
    the fact-check pass silently no-opping on every non-Claude vendor)."""

    def test_sandbox_mode_prepares_exact_agent_activation_context(
        self, tmp_path, monkeypatch,
    ) -> None:
        activation_context = object()
        captured: dict = {}
        cli_config = _FakeCliConfig(
            command=sys.executable,
            dispatch_modes={
                "alternative": _ModeConfig(["--plain"], isolation="sandbox"),
            },
        )

        def resolve(**kwargs):
            captured["resolved"] = kwargs
            return activation_context

        monkeypatch.setattr(fact_check, "resolve_activation_context", resolve)

        def record(invocation):
            captured["invocation"] = invocation
            return type("Result", (), {
                "status": "completed", "returncode": 0, "stdout": "ok",
                "stderr": "", "timed_out": False, "sandbox_applied": True,
                "degradation_reason": None, "cleanup_status": "succeeded",
                "cleanup_residual_paths": (),
            })()

        monkeypatch.setattr(fact_check, "run_vendor_process", record)
        caller = fact_check.build_default_caller(
            cli_config, "some-vendor", agent_id="codex-local", cwd=tmp_path,
        )
        assert caller is not None

        caller("system", "user")

        assert captured["resolved"]["agent_id"] == "codex-local"
        assert captured["resolved"]["dispatch_mode"] == "alternative"
        assert captured["invocation"].activation_context is activation_context

    def test_uses_alternative_mode_args_not_claude_flags(
        self, tmp_path, monkeypatch,
    ) -> None:
        captured: dict = {}
        cli_config = _FakeCliConfig(
            command=sys.executable,
            dispatch_modes={
                "review": _ModeConfig(["--schema-mode", "@review-findings-schema"]),
                "alternative": _ModeConfig(["--plain", "--flag"]),
            },
        )
        caller = fact_check.build_default_caller(cli_config, "some-vendor", cwd=tmp_path)
        assert caller is not None

        def record(invocation):
            captured["cmd"] = list(invocation.argv)
            return type("Result", (), {
                "status": "completed", "returncode": 0, "stdout": "ok",
                "stderr": "", "timed_out": False, "sandbox_applied": False,
                "degradation_reason": None, "cleanup_status": "succeeded",
                "cleanup_residual_paths": (),
            })()
        monkeypatch.setattr(fact_check, "run_vendor_process", record)
        caller("system", "user")
        cmd = captured["cmd"]
        assert cmd[0] == sys.executable
        assert "--plain" in cmd and "--flag" in cmd
        assert "--schema-mode" not in cmd
        assert "--print" not in cmd
        assert "--allowedTools" not in cmd

    def test_falls_back_to_quick_mode_when_no_alternative(
        self, tmp_path, monkeypatch,
    ) -> None:
        captured: dict = {}

        def record(invocation):
            captured["cmd"] = list(invocation.argv)
            return type("Result", (), {
                "status": "completed", "returncode": 0, "stdout": "ok",
                "stderr": "", "timed_out": False, "sandbox_applied": False,
                "degradation_reason": None, "cleanup_status": "succeeded",
                "cleanup_residual_paths": (),
            })()
        monkeypatch.setattr(fact_check, "run_vendor_process", record)
        cli_config = _FakeCliConfig(
            command=sys.executable,
            dispatch_modes={"quick": _ModeConfig(["--quick-only"])},
        )
        caller = fact_check.build_default_caller(cli_config, "some-vendor", cwd=tmp_path)
        assert caller is not None
        caller("system", "user")
        assert "--quick-only" in captured["cmd"]

    def test_returns_none_without_alternative_or_quick_mode(self, tmp_path) -> None:
        cli_config = _FakeCliConfig(
            command=sys.executable,
            dispatch_modes={"review": _ModeConfig(["--schema-mode"])},
        )
        assert fact_check.build_default_caller(cli_config, "v", cwd=tmp_path) is None

    def test_returns_none_when_alternative_mode_is_async(self, tmp_path) -> None:
        cli_config = _FakeCliConfig(
            command=sys.executable,
            dispatch_modes={"alternative": _ModeConfig(["--x"], async_dispatch=True)},
        )
        assert fact_check.build_default_caller(cli_config, "v", cwd=tmp_path) is None
