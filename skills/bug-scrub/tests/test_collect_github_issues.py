"""GitHub issue inventory and bug triage tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import CompletedProcess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import collect_github_issues
from aggregate import aggregate
from bug_candidate_work import project_candidate_work
from render_report import render_markdown


def test_lists_all_open_issues_without_creating_findings(monkeypatch, tmp_path):
    issues = [
        {
            "number": 12,
            "title": "Fix broken test",
            "url": "https://github.com/o/r/issues/12",
            "labels": [{"name": "bug"}],
            "createdAt": "2026-09-01T00:00:00Z",
        },
        {
            "number": 13,
            "title": "Add a feature",
            "url": "https://github.com/o/r/issues/13",
            "labels": [{"name": "enhancement"}],
            "createdAt": "2026-09-02T00:00:00Z",
        },
    ]
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return CompletedProcess(cmd, 0, json.dumps(issues), "")

    monkeypatch.setattr(collect_github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(collect_github_issues.subprocess, "run", fake_run)
    result = collect_github_issues.collect(str(tmp_path))

    assert result.status == "ok"
    assert [item["number"] for item in result.inventory] == [12, 13]
    assert result.findings == []
    assert calls[0][0][:4] == ["gh", "issue", "list", "--state"]
    assert calls[0][1]["cwd"] == str(tmp_path)

    report = aggregate([result], severity_filter="low")
    rendered = render_markdown(report)
    assert "https://github.com/o/r/issues/12" in rendered
    assert "Add a feature" in rendered
    assert project_candidate_work(report, "report.json") == []
    assert report.to_dict()["source_results"][0]["inventory"] == result.inventory


def test_empty_issue_inventory_is_visible(monkeypatch, tmp_path):
    monkeypatch.setattr(collect_github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(
        collect_github_issues.subprocess,
        "run",
        lambda cmd, **kw: CompletedProcess(cmd, 0, "[]", ""),
    )
    result = collect_github_issues.collect(str(tmp_path))
    assert "No open issues." in render_markdown(aggregate([result]))


def test_missing_gh_skips_and_failed_command_reports_error(monkeypatch, tmp_path):
    monkeypatch.setattr(collect_github_issues.shutil, "which", lambda _: None)
    assert collect_github_issues.collect(str(tmp_path)).status == "skipped"

    monkeypatch.setattr(collect_github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(
        collect_github_issues.subprocess,
        "run",
        lambda cmd, **kw: CompletedProcess(cmd, 1, "", "authentication required"),
    )
    failed = collect_github_issues.collect(str(tmp_path))
    assert failed.status == "error"
    assert "authentication required" in failed.messages[0]
    assert "Listing unavailable" in render_markdown(aggregate([failed]))


def test_limit_and_bad_json_are_errors_not_partial_inventories(monkeypatch, tmp_path):
    monkeypatch.setattr(collect_github_issues.shutil, "which", lambda _: "/usr/bin/gh")
    issue = {"number": 1, "title": "Issue", "url": "https://github.com/o/r/issues/1", "labels": []}
    monkeypatch.setattr(collect_github_issues, "_LIMIT", 1)
    monkeypatch.setattr(
        collect_github_issues.subprocess,
        "run",
        lambda cmd, **kw: CompletedProcess(cmd, 0, json.dumps([issue]), ""),
    )
    capped = collect_github_issues.collect(str(tmp_path))
    assert capped.status == "error"
    assert capped.inventory == []

    monkeypatch.setattr(
        collect_github_issues.subprocess,
        "run",
        lambda cmd, **kw: CompletedProcess(cmd, 0, "not json", ""),
    )
    assert collect_github_issues.collect(str(tmp_path)).status == "error"
