"""Tests for the OCR (alibaba/open-code-review) reviewer vendor adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ocr_adapter  # noqa: E402


class TestRewriteComment:
    def test_full_comment_rewrite(self) -> None:
        comment = {
            "path": "src/foo.py",
            "content": "Off-by-one in the loop bound.",
            "start_line": 10,
            "end_line": 12,
            "category": "bug",
            "severity": "high",
            "suggestion_code": "for i in range(n):",
            "existing_code": "for i in range(n + 1):",
        }
        finding = ocr_adapter._rewrite_comment(comment, 1)
        assert finding["id"] == 1
        assert finding["type"] == "bug"
        assert finding["axis"] == "bug"
        assert finding["criticality"] == "high"
        assert "severity" not in finding
        assert finding["description"] == "Off-by-one in the loop bound."
        assert finding["file_path"] == "src/foo.py"
        assert finding["line_range"] == {"start": 10, "end": 12}
        assert finding["existing_code"] == "for i in range(n + 1):"
        assert finding["resolution"].startswith("Suggested change:")
        assert finding["disposition"] == "fix"

    def test_zero_line_range_is_omitted(self) -> None:
        comment = {
            "path": "src/foo.py", "content": "text", "category": "style",
            "severity": "low", "start_line": 0, "end_line": 0,
        }
        finding = ocr_adapter._rewrite_comment(comment, 1)
        assert "line_range" not in finding

    def test_missing_category_defaults_to_other(self) -> None:
        comment = {"path": "src/foo.py", "content": "text", "severity": "low"}
        finding = ocr_adapter._rewrite_comment(comment, 1)
        assert finding["type"] == "other"
        assert finding["axis"] == "other"

    def test_no_existing_code_or_suggestion(self) -> None:
        comment = {
            "path": "src/foo.py", "content": "text", "category": "style",
            "severity": "low",
        }
        finding = ocr_adapter._rewrite_comment(comment, 1)
        assert "existing_code" not in finding
        assert "resolution" not in finding


class TestRewriteOutput:
    def test_rewrites_every_comment(self) -> None:
        ocr_result = {
            "comments": [
                {"path": "a.py", "content": "x", "category": "bug", "severity": "high"},
                {"path": "b.py", "content": "y", "category": "style", "severity": "low"},
            ]
        }
        payload = ocr_adapter.rewrite_output(
            ocr_result, change_id="my-change", review_type="implementation",
        )
        assert payload["review_type"] == "implementation"
        assert payload["target"] == "my-change"
        assert payload["reviewer_vendor"] == "ocr"
        assert len(payload["findings"]) == 2
        assert payload["findings"][0]["id"] == 1
        assert payload["findings"][1]["id"] == 2

    def test_empty_comments_is_empty_findings(self) -> None:
        payload = ocr_adapter.rewrite_output(
            {"comments": []}, change_id="c", review_type="plan",
        )
        assert payload["findings"] == []

    def test_missing_comments_key_is_empty_findings(self) -> None:
        payload = ocr_adapter.rewrite_output({}, change_id="c", review_type="plan")
        assert payload["findings"] == []


class TestOcrCoercionThroughSchema:
    """The full rewrite → coercion → validation pipeline, end to end."""

    def test_ocr_finding_validates_after_coercion(self) -> None:
        from review_findings_schema import coerce_findings_payload, validate_findings_payload

        comment = {
            "path": "src/foo.py",
            "content": "The `ctx` parameter is never used.",
            "start_line": 5,
            "end_line": 5,
            "category": "maintainability",
            "severity": "medium",
        }
        finding = ocr_adapter._rewrite_comment(comment, 1)
        payload = {"findings": [finding]}
        coerced, notes = coerce_findings_payload(payload)
        assert coerced["findings"][0]["type"] == "architecture"
        assert coerced["findings"][0]["axis"] == "architecture"
        assert coerced["findings"][0]["severity"] == "nit"
        assert any("severity" in n for n in notes)
        errors = validate_findings_payload(coerced)
        assert errors == []

    def test_ocr_test_category_maps_to_correctness(self) -> None:
        from review_findings_schema import coerce_findings_payload

        finding = ocr_adapter._rewrite_comment(
            {"path": "a.py", "content": "x", "category": "test", "severity": "low"}, 1,
        )
        coerced, _notes = coerce_findings_payload({"findings": [finding]})
        assert coerced["findings"][0]["type"] == "correctness"
        assert coerced["findings"][0]["axis"] == "correctness"

    def test_ocr_documentation_category_maps(self) -> None:
        from review_findings_schema import coerce_findings_payload

        finding = ocr_adapter._rewrite_comment(
            {"path": "a.py", "content": "x", "category": "documentation", "severity": "low"}, 1,
        )
        coerced, _notes = coerce_findings_payload({"findings": [finding]})
        assert coerced["findings"][0]["type"] == "style"
        assert coerced["findings"][0]["axis"] == "readability"

    def test_ocr_security_and_performance_pass_through_unaliased(self) -> None:
        from review_findings_schema import coerce_findings_payload, validate_findings_payload

        for category in ("security", "performance"):
            finding = ocr_adapter._rewrite_comment(
                {"path": "a.py", "content": "x", "category": category, "severity": "critical"}, 1,
            )
            coerced, _notes = coerce_findings_payload({"findings": [finding]})
            assert coerced["findings"][0]["type"] == category
            assert coerced["findings"][0]["axis"] == category
            assert validate_findings_payload(coerced) == []


class TestCanDispatch:
    def test_false_when_binary_missing(self, monkeypatch) -> None:
        monkeypatch.setattr(ocr_adapter.shutil, "which", lambda _cmd: None)
        assert ocr_adapter.can_dispatch() is False

    def test_false_when_binary_present_but_not_configured(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(ocr_adapter.shutil, "which", lambda _cmd: "/usr/bin/ocr")
        monkeypatch.delenv("OCR_LLM_URL", raising=False)
        monkeypatch.delenv("OCR_LLM_TOKEN", raising=False)
        monkeypatch.setattr(ocr_adapter.Path, "home", lambda: tmp_path)
        assert ocr_adapter.can_dispatch() is False

    def test_true_when_binary_present_and_env_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(ocr_adapter.shutil, "which", lambda _cmd: "/usr/bin/ocr")
        monkeypatch.setenv("OCR_LLM_URL", "https://example.test/v1")
        assert ocr_adapter.can_dispatch() is True

    def test_true_when_binary_present_and_config_file_exists(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(ocr_adapter.shutil, "which", lambda _cmd: "/usr/bin/ocr")
        monkeypatch.delenv("OCR_LLM_URL", raising=False)
        monkeypatch.delenv("OCR_LLM_TOKEN", raising=False)
        (tmp_path / ".opencodereview").mkdir()
        (tmp_path / ".opencodereview" / "config.json").write_text("{}")
        monkeypatch.setattr(ocr_adapter.Path, "home", lambda: tmp_path)
        assert ocr_adapter.can_dispatch() is True


class TestRunOcr:
    def test_run_ocr_reads_output_file(self, tmp_path) -> None:
        expected = {"comments": []}

        def fake_run(cmd, **kwargs):
            output_path = Path(cmd[cmd.index("--output") + 1])
            output_path.write_text(json.dumps(expected))
            return type("R", (), {"returncode": 0, "stderr": ""})()

        with patch.object(ocr_adapter.subprocess, "run", side_effect=fake_run):
            result = ocr_adapter.run_ocr(tmp_path)
        assert result == expected

    def test_run_ocr_raises_on_nonzero_exit_without_output(self, tmp_path) -> None:
        def fake_run(cmd, **kwargs):
            return type("R", (), {"returncode": 1, "stderr": "boom"})()

        with patch.object(ocr_adapter.subprocess, "run", side_effect=fake_run):
            try:
                ocr_adapter.run_ocr(tmp_path)
                assert False, "expected OcrRunError"
            except ocr_adapter.OcrRunError as exc:
                assert "boom" in str(exc)

    def test_run_ocr_range_mode_from_env(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("REVIEW_BASE_REF", "main")
        monkeypatch.setenv("REVIEW_HEAD_REF", "HEAD")
        seen_cmd = {}

        def fake_run(cmd, **kwargs):
            seen_cmd["cmd"] = cmd
            output_path = Path(cmd[cmd.index("--output") + 1])
            output_path.write_text(json.dumps({"comments": []}))
            return type("R", (), {"returncode": 0, "stderr": ""})()

        with patch.object(ocr_adapter.subprocess, "run", side_effect=fake_run):
            ocr_adapter.run_ocr(tmp_path)
        assert "--from" in seen_cmd["cmd"]
        assert seen_cmd["cmd"][seen_cmd["cmd"].index("--from") + 1] == "main"
        assert seen_cmd["cmd"][seen_cmd["cmd"].index("--to") + 1] == "HEAD"


class TestMain:
    def test_exits_2_when_binary_missing(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(ocr_adapter.shutil, "which", lambda _cmd: None)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        code = ocr_adapter.main([])
        assert code == 2
        assert "not found on PATH" in capsys.readouterr().err

    def test_exits_2_when_not_configured(self, monkeypatch, capsys, tmp_path) -> None:
        monkeypatch.setattr(ocr_adapter.shutil, "which", lambda _cmd: "/usr/bin/ocr")
        monkeypatch.delenv("OCR_LLM_URL", raising=False)
        monkeypatch.delenv("OCR_LLM_TOKEN", raising=False)
        monkeypatch.setattr(ocr_adapter.Path, "home", lambda: tmp_path)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        code = ocr_adapter.main([])
        assert code == 2
        assert "no LLM endpoint configured" in capsys.readouterr().err

    def test_success_prints_findings_json(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(ocr_adapter.shutil, "which", lambda _cmd: "/usr/bin/ocr")
        monkeypatch.setenv("OCR_LLM_URL", "https://example.test/v1")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(
            ocr_adapter, "run_ocr",
            lambda cwd, **kw: {"comments": [{"path": "a.py", "content": "x", "category": "bug", "severity": "high"}]},
        )
        code = ocr_adapter.main(["--change-id", "my-change", "--review-type", "implementation"])
        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["target"] == "my-change"
        assert out["review_type"] == "implementation"
        assert len(out["findings"]) == 1
