"""Tests for the evidence collector's session-log cross-reference resolver
(skills/audit-choices/scripts/collect_evidence.py). Design D5.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "audit-choices" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import collect_evidence  # noqa: E402

# Same pattern the schema enforces for session_log_ref.
SESSION_LOG_REF_RE = re.compile(r"^[a-z0-9][a-z0-9-]*#([a-z0-9][a-z0-9-]*/)?D[0-9]+$")

SESSION_LOG_SINGLE_PHASE = """\
## Phase: Implementation (2026-08-20)

**Agent**: claude_code | **Session**: N/A

### Decisions

1. **Chose per-request retry budget of 3** — matches the conservative default used elsewhere.
2. **Chose synchronous validation** — keeps the request path simple.

### Context

Implemented the client.
"""

SESSION_LOG_MULTI_PHASE = """\
## Phase: Plan (2026-08-18)

**Agent**: claude_code | **Session**: N/A

### Decisions

1. **Chose per-request retry budget of 3** — matches the conservative default used elsewhere.

### Context

Planned the work.

## Phase: Implementation (2026-08-20)

**Agent**: claude_code | **Session**: N/A

### Decisions

1. **Chose synchronous validation** — keeps the request path simple.

### Context

Implemented the client.
"""


class TestParseSessionLogDecisions:
    def test_single_phase_produces_bare_refs(self):
        decisions = collect_evidence.parse_session_log_decisions(
            SESSION_LOG_SINGLE_PHASE, change_id="my-change"
        )
        refs = [d["ref"] for d in decisions]
        assert refs == ["my-change#D1", "my-change#D2"]
        for ref in refs:
            assert SESSION_LOG_REF_RE.match(ref)

    def test_multi_phase_produces_phase_qualified_refs(self):
        decisions = collect_evidence.parse_session_log_decisions(
            SESSION_LOG_MULTI_PHASE, change_id="my-change"
        )
        refs = [d["ref"] for d in decisions]
        assert refs == ["my-change#plan/D1", "my-change#implementation/D1"]
        for ref in refs:
            assert SESSION_LOG_REF_RE.match(ref)

    def test_empty_text_returns_empty_list(self):
        assert collect_evidence.parse_session_log_decisions("", change_id="my-change") == []

    def test_text_with_no_phase_headers_returns_empty_list(self):
        assert collect_evidence.parse_session_log_decisions(
            "Just some prose, no phase headers.", change_id="my-change"
        ) == []


class TestResolveSelfReported:
    def test_unreported_decision_flagged(self):
        known = collect_evidence.parse_session_log_decisions(
            SESSION_LOG_SINGLE_PHASE, change_id="my-change"
        )
        self_reported, ref = collect_evidence.resolve_self_reported(
            "Adopted an entirely unrelated caching strategy for the frontend", known
        )
        assert self_reported is False
        assert ref is None

    def test_matching_decision_gets_self_reported_true_and_ref(self):
        known = collect_evidence.parse_session_log_decisions(
            SESSION_LOG_SINGLE_PHASE, change_id="my-change"
        )
        self_reported, ref = collect_evidence.resolve_self_reported(
            "Chose per-request retry budget of 3", known
        )
        assert self_reported is True
        assert ref == "my-change#D1"
        assert SESSION_LOG_REF_RE.match(ref)

    def test_matching_decision_in_multi_phase_log_gets_phase_qualified_ref(self):
        known = collect_evidence.parse_session_log_decisions(
            SESSION_LOG_MULTI_PHASE, change_id="my-change"
        )
        self_reported, ref = collect_evidence.resolve_self_reported(
            "Chose synchronous validation", known
        )
        assert self_reported is True
        assert ref == "my-change#implementation/D1"

    def test_no_known_decisions_returns_unmatched(self):
        self_reported, ref = collect_evidence.resolve_self_reported("Any choice", [])
        assert self_reported is False
        assert ref is None


class TestCollectorWithoutSessionLog:
    def test_collector_works_when_session_log_absent(self, tmp_path):
        repo_root = tmp_path
        change_dir = repo_root / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        # No session-log.md written at all.
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
        subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo_root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, check=True)
        (repo_root / "f.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo_root, check=True)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.strip()
        (repo_root / "f.py").write_text("x = 2\n")
        subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=repo_root, check=True)
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.strip()

        bundle = collect_evidence.collect_evidence(
            repo_root, change_id="my-change", base_sha=base_sha, head_sha=head_sha
        )
        assert bundle.known_decisions == []
        # A candidate entry should come back unmatched, not crash.
        self_reported, ref = collect_evidence.resolve_self_reported(
            "Some decision", bundle.known_decisions
        )
        assert self_reported is False
        assert ref is None
