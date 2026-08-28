"""Step-four tests: the decision index is bound to the session-log write.

`PhaseRecord.write_both()` appends a session-log entry whose capability-tagged
decisions are the sole input to `docs/decisions/`. Until step four existed, the
append invalidated that index and nothing regenerated it, so every OpenSpec
change left `decisions.timeline` drift for a human to clear with one command.

Covers the three added spec scenarios for the persistence pipeline:
- Regeneration leaves the decision index current
- Regeneration failure does not lose the session log
- Regeneration is skipped when the generator is absent

plus the two invariants that make the binding safe rather than merely
convenient:
- No worker call site invokes the persistence pipeline (orchestrator scoping)
- A hand-edited session log still reports drift (the gate keeps checking)

**Isolation.** Step four regenerates a *repository's* `docs/decisions/`. Every
test here works inside a synthesized repository under `tmp_path`, and
`_real_decision_index_untouched` digests this repository's real
`docs/decisions/` around every test so a regression that escapes the sandbox
fails loudly instead of silently rewriting a committed artifact.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
for _scripts in (
    REPO_ROOT / "skills/session-log/scripts",
    REPO_ROOT / "skills/explore-feature/scripts",
    REPO_ROOT / "skills/project-context-refresh/scripts",
):
    if str(_scripts) not in sys.path:
        sys.path.insert(0, str(_scripts))

import phase_record  # noqa: E402
from phase_record import Decision, PhaseRecord  # noqa: E402

CAPABILITY = "skill-workflow"


# ─────────────────────────────────────────────────────────────────────────────
# Isolation guard
# ─────────────────────────────────────────────────────────────────────────────


def _digest_tree(root: Path) -> dict[str, str]:
    """Content digest of every file under *root*, keyed by relative path."""
    if not root.is_dir():
        return {}
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture(autouse=True)
def _real_decision_index_untouched() -> Any:
    """Fail any test that regenerates this repository's committed index.

    The sandbox is `monkeypatch.chdir` plus a synthesized repository, but a
    path-derivation bug would silently rewrite a tracked artifact. This turns
    that into a test failure rather than a dirty working tree.
    """
    real = REPO_ROOT / "docs" / "decisions"
    before = _digest_tree(real)
    yield
    assert _digest_tree(real) == before, (
        "a test rewrote the repository's real docs/decisions/ — step four "
        "escaped the tmp_path sandbox"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


class _StubWriter:
    """Stand-in coordinator writer; keeps the tests off the network."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"handoff_id": f"h-{len(self.calls)}"}


def _seed_repository(root: Path) -> Path:
    """Create the minimum tree the decision-index generator recognizes.

    `.git` marks the repository root, which is what the generator uses to
    render repository-relative back-references; `openspec/specs/<cap>/` is what
    makes a capability tag valid rather than skipped as unknown.
    """
    (root / ".git").mkdir(parents=True, exist_ok=True)
    spec_dir = root / "openspec" / "specs" / CAPABILITY
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text("# spec\n", encoding="utf-8")
    return root


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthesized repository that is also the working directory."""
    _seed_repository(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _record(change_id: str = "my-change", phase: str = "Plan") -> PhaseRecord:
    return PhaseRecord(
        change_id=change_id,
        phase_name=phase,
        agent_type="claude_code",
        summary="A representative phase summary.",
        decisions=[
            Decision(
                title="Bind the index to the write",
                rationale="The writer is the only thing that can prevent the drift.",
                capability=CAPABILITY,
            )
        ],
    )


def _fresh_render(repo_root: Path, output_dir: Path) -> None:
    """Render the index from scratch the way `make decisions` would."""
    from archive_index import emit_decisions_from_archive

    emit_decisions_from_archive(
        archive_root=repo_root / "openspec" / "changes",
        output_dir=output_dir,
        capabilities_root=repo_root / "openspec" / "specs",
        strict=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1.1 — Regeneration leaves the decision index current
# ─────────────────────────────────────────────────────────────────────────────


class TestRegenerationLeavesIndexCurrent:
    """Spec scenario: Regeneration leaves the decision index current."""

    def test_index_matches_a_fresh_regeneration(self, repo: Path, tmp_path: Path) -> None:
        result = _record().write_both(coordinator_writer=_StubWriter())
        assert result.markdown_path is not None

        written = _digest_tree(repo / "docs" / "decisions")
        assert written, "write_both() produced no decision index at all"

        expected_dir = tmp_path.parent / f"{tmp_path.name}-expected"
        expected_dir.mkdir()
        _fresh_render(repo, expected_dir)
        assert written == _digest_tree(expected_dir)

    def test_the_tagged_capability_file_carries_the_new_decision(self, repo: Path) -> None:
        _record().write_both(coordinator_writer=_StubWriter())
        cap_file = repo / "docs" / "decisions" / f"{CAPABILITY}.md"
        assert cap_file.exists(), f"no {CAPABILITY}.md emitted for the tagged decision"
        assert "Bind the index to the write" in cap_file.read_text(encoding="utf-8")

    def test_a_second_regeneration_produces_no_further_change(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Currency alone would pass for a generator that disagrees with itself.

        The property is *idempotent* currency: the index write_both() left
        behind must be a fixed point of the generator, not merely one of its
        possible outputs.
        """
        _record().write_both(coordinator_writer=_StubWriter())
        after_write = _digest_tree(repo / "docs" / "decisions")

        _fresh_render(repo, repo / "docs" / "decisions")
        assert _digest_tree(repo / "docs" / "decisions") == after_write

        # And through the pipeline itself, not only through a direct render.
        _record(phase="Implementation").write_both(coordinator_writer=_StubWriter())
        second_pass = _digest_tree(repo / "docs" / "decisions")
        expected_dir = tmp_path.parent / f"{tmp_path.name}-expected-2"
        expected_dir.mkdir()
        _fresh_render(repo, expected_dir)
        assert second_pass == _digest_tree(expected_dir)

    def test_no_warnings_on_the_happy_path(self, repo: Path) -> None:
        result = _record().write_both(coordinator_writer=_StubWriter())
        assert result.warnings == []


# ─────────────────────────────────────────────────────────────────────────────
# 1.2 — Regeneration failure does not lose the session log
# ─────────────────────────────────────────────────────────────────────────────


class TestRegenerationFailureDoesNotLoseSessionLog:
    """Spec scenario: Regeneration failure does not lose the session log."""

    def test_nonzero_exit_leaves_the_markdown_and_the_handoff(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exploding = repo / "exploding_generator.py"
        exploding.write_text(
            "import sys\n"
            "sys.stderr.write('generator blew up\\n')\n"
            "sys.exit(3)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            phase_record,
            "_decision_index_generator",
            lambda: exploding,
            raising=False,
        )

        writer = _StubWriter()
        result = _record().write_both(coordinator_writer=writer)

        assert result.markdown_path is not None and result.markdown_path.exists()
        body = result.markdown_path.read_text(encoding="utf-8")
        assert "## Phase: Plan" in body
        assert f"`architectural: {CAPABILITY}`" in body
        assert result.sanitized is True
        assert result.handoff_id == "h-1"
        assert any("step_4_decisions" in w for w in result.warnings), result.warnings
        assert any("3" in w for w in result.warnings if "step_4_decisions" in w)

    def test_markdown_is_byte_identical_after_a_failing_regeneration(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The append is durable: a later step cannot rewrite or truncate it."""
        log = repo / "openspec/changes/my-change/session-log.md"
        log.parent.mkdir(parents=True)
        log.write_text("# Session Log: my-change\n", encoding="utf-8")

        captured: dict[str, bytes] = {}

        def _boom() -> Path:
            captured["at_call_time"] = log.read_bytes()
            raise RuntimeError("generator could not be resolved")

        monkeypatch.setattr(
            phase_record, "_decision_index_generator", _boom, raising=False
        )
        result = _record().write_both(coordinator_writer=_StubWriter())

        assert captured["at_call_time"] == log.read_bytes()
        assert b"## Phase: Plan" in captured["at_call_time"], (
            "step four ran before the append — it must derive from what step "
            "one wrote, never from a log that does not yet contain this entry"
        )
        assert result.markdown_path is not None
        assert result.handoff_id == "h-1"
        assert any("step_4_decisions" in w for w in result.warnings), result.warnings

    def test_a_raising_generator_does_not_raise_out_of_write_both(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom() -> Path:
            raise OSError("disk gone")

        monkeypatch.setattr(
            phase_record, "_decision_index_generator", _boom, raising=False
        )
        # Four callers treat write_both() as infallible; step four must not be
        # the one that breaks that.
        result = _record().write_both(coordinator_writer=_StubWriter())
        assert any("OSError" in w for w in result.warnings), result.warnings

    def test_the_previous_index_survives_a_failing_regeneration(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty index that compares equal to itself is worse than a stale one."""
        decisions_dir = repo / "docs" / "decisions"
        decisions_dir.mkdir(parents=True)
        stale = decisions_dir / f"{CAPABILITY}.md"
        stale.write_text("# stale but real\n", encoding="utf-8")

        monkeypatch.setattr(
            phase_record,
            "_decision_index_generator",
            lambda: repo / "does-not-exist.py",
            raising=False,
        )
        _record().write_both(coordinator_writer=_StubWriter())
        assert stale.read_text(encoding="utf-8") == "# stale but real\n"


# ─────────────────────────────────────────────────────────────────────────────
# 1.3 — Regeneration is skipped when the generator is absent
# ─────────────────────────────────────────────────────────────────────────────


class TestGeneratorAbsent:
    """Spec scenario: Regeneration is skipped when the generator is absent."""

    def test_first_three_steps_complete_and_the_warning_names_the_generator(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = repo / "vendor" / "explore-feature" / "scripts" / "archive_index.py"
        monkeypatch.setattr(
            phase_record, "_decision_index_generator", lambda: missing, raising=False
        )

        writer = _StubWriter()
        result = _record().write_both(coordinator_writer=writer)

        # Steps one to three, unchanged.
        assert result.markdown_path is not None and result.markdown_path.exists()
        assert result.sanitized is True
        assert result.handoff_id == "h-1"
        assert result.handoff_local_path is None
        assert len(writer.calls) == 1

        named = [w for w in result.warnings if "step_4_decisions" in w]
        assert named, result.warnings
        assert "archive_index.py" in named[0], named[0]

    def test_generator_is_resolved_lazily_not_at_import(self) -> None:
        """A checkout without explore-feature must still import phase_record.

        Resolution is a call, so absence is a warning at write time rather than
        an ImportError at module load.
        """
        resolver = getattr(phase_record, "_decision_index_generator", None)
        assert callable(resolver), (
            "the generator must be resolved by a call at write time, not bound "
            "to a module-level constant at import"
        )
        assert isinstance(resolver(), Path)

    def test_the_default_resolution_points_at_the_make_decisions_owner(self) -> None:
        resolved = phase_record._decision_index_generator()
        assert resolved.name == "archive_index.py"
        assert resolved.parent.parent.name == "explore-feature"


# ─────────────────────────────────────────────────────────────────────────────
# 1.6 — No worker call site invokes the persistence pipeline
# ─────────────────────────────────────────────────────────────────────────────

#: Skills whose `write_both()` call sites are orchestrator phase-boundary steps.
#: `session-log` owns the pipeline and documents its API; `autopilot` is the
#: top-level driver that records a phase-failed entry at an escalation boundary.
#: Everything else here is one of the six phase-boundary skills.
ORCHESTRATOR_SKILLS = frozenset(
    {
        "autopilot",
        "cleanup-feature",
        "implement-feature",
        "iterate-on-implementation",
        "iterate-on-plan",
        "plan-feature",
        "session-log",
        "validate-feature",
    }
)

#: Headings that scope a section to a work-package worker rather than to the
#: orchestrator. A call site under any of these writes `docs/decisions/`, which
#: lies outside every package's `write_allow`, and would fail the scope check.
_WORKER_HEADING = re.compile(
    r"worker|package execution|work package|sub-agent dispatch", re.IGNORECASE
)

_FENCE = re.compile(r"^\s*```(?P<info>[^\n]*)$")
_PY_INFO = re.compile(r"^(python|py|python3)\b", re.IGNORECASE)

#: The repo's phase-boundary steps dispatch Python as a heredoc inside a bash
#: fence (``python3 - <<'EOF' … EOF``), so the Python has to be lifted out of
#: the shell block before it can be parsed.
_HEREDOC = re.compile(
    r"^[^\n]*\bpython3?\b[^\n]*<<-?\s*[\"']?(?P<tag>\w+)[\"']?\s*$\n"
    r"(?P<body>.*?)^(?P=tag)\s*$",
    re.MULTILINE | re.DOTALL,
)


def _python_fragments(info: str, block: str) -> list[str]:
    """Every executable Python fragment inside one fenced block.

    A ``python``-tagged fence is Python outright; a shell fence contributes the
    body of each Python heredoc it runs. Anything else contributes nothing,
    which is what keeps prose and shell plumbing out of the call-site set.
    """
    if _PY_INFO.match(info.strip()):
        return [block]
    return [m.group("body") for m in _HEREDOC.finditer(block)]


def _markdown_code_call_sites(text: str) -> list[tuple[tuple[str, ...], str]]:
    """Return (heading_path, code) for every executable block calling write_both.

    Structural rather than a prose grep: only executable code is considered,
    and each fragment is attributed to the heading path it sits under. Prose
    that merely *describes* the pipeline is invisible here, while a worker
    prompt that embedded a real call would be found.
    """
    sites: list[tuple[tuple[str, ...], str]] = []
    headings: dict[int, str] = {}
    in_block = False
    block_info = ""
    block: list[str] = []

    for line in text.splitlines():
        fence = _FENCE.match(line)
        if fence and not in_block:
            in_block = True
            block_info = fence.group("info")
            block = []
            continue
        if fence and in_block:
            in_block = False
            body = "\n".join(block) + "\n"
            path = tuple(headings[k] for k in sorted(headings))
            for fragment in _python_fragments(block_info, body):
                if _calls_write_both(fragment):
                    sites.append((path, fragment))
            continue
        if in_block:
            block.append(line)
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = line.lstrip("#").strip()

    return sites


def _calls_write_both(code: str) -> bool:
    """True when *code* contains a `write_both(...)` call.

    Parsed as Python when it parses — SKILL.md blocks carry `<change-id>`
    placeholders inside string literals, so they usually do. The textual
    fallback keeps a block with an unparseable placeholder from being silently
    treated as call-free, which would turn this guard into a no-op.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return bool(re.search(r"\bwrite_both\s*\(", code))
    return bool(_ast_call_lines(tree))


def _ast_call_lines(tree: ast.AST) -> list[int]:
    """Line numbers of every `write_both(...)` call node in *tree*."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name == "write_both":
            lines.append(node.lineno)
    return lines


def _skill_of(path: Path) -> str:
    return path.relative_to(REPO_ROOT / "skills").parts[0]


class TestPersistenceIsOrchestratorScoped:
    """Spec scenario: No worker call site invokes the persistence pipeline."""

    def test_every_python_call_site_belongs_to_an_orchestrator_skill(self) -> None:
        offenders: list[str] = []
        found: set[str] = set()
        for py in sorted((REPO_ROOT / "skills").rglob("*.py")):
            rel = py.relative_to(REPO_ROOT)
            if rel.parts[1] == "tests" or ".venv" in rel.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - defensive
                continue
            for lineno in _ast_call_lines(tree):
                skill = _skill_of(py)
                found.add(skill)
                if skill not in ORCHESTRATOR_SKILLS:
                    offenders.append(f"{rel}:{lineno}")
        assert not offenders, (
            "write_both() called outside an orchestrator skill — step four "
            f"writes docs/decisions/, outside every package's write_allow: {offenders}"
        )
        assert "autopilot" in found, (
            "the autopilot phase-failed call site disappeared; this guard is "
            "asserting over an empty set"
        )

    def test_every_skill_md_call_site_belongs_to_an_orchestrator_skill(self) -> None:
        offenders: list[str] = []
        skills_with_calls: set[str] = set()
        for skill_md in sorted((REPO_ROOT / "skills").rglob("SKILL.md")):
            for heading_path, _code in _markdown_code_call_sites(
                skill_md.read_text(encoding="utf-8")
            ):
                skill = _skill_of(skill_md)
                skills_with_calls.add(skill)
                if skill not in ORCHESTRATOR_SKILLS:
                    offenders.append(f"{_skill_of(skill_md)} :: {' / '.join(heading_path)}")
        assert not offenders, offenders
        # The six phase-boundary skills plus the pipeline's own API reference.
        assert skills_with_calls == {
            "plan-feature",
            "iterate-on-plan",
            "implement-feature",
            "iterate-on-implementation",
            "validate-feature",
            "cleanup-feature",
            "session-log",
        }, skills_with_calls

    def test_no_call_site_sits_under_a_worker_section(self) -> None:
        offenders: list[str] = []
        for skill_md in sorted((REPO_ROOT / "skills").rglob("SKILL.md")):
            for heading_path, _code in _markdown_code_call_sites(
                skill_md.read_text(encoding="utf-8")
            ):
                worker = [h for h in heading_path if _WORKER_HEADING.search(h)]
                if worker:
                    offenders.append(
                        f"{_skill_of(skill_md)} :: {' / '.join(heading_path)} "
                        f"(worker headings: {worker})"
                    )
        assert not offenders, (
            "write_both() reachable from a work-package worker section: "
            f"{offenders}"
        )

    def test_the_worker_heading_detector_is_not_vacuous(self) -> None:
        """The detector must actually match this repository's worker sections.

        Without this, a typo in the pattern would make the guard above pass by
        never matching anything.
        """
        implement = (REPO_ROOT / "skills/implement-feature/SKILL.md").read_text(
            encoding="utf-8"
        )
        worker_headings = [
            line
            for line in implement.splitlines()
            if line.startswith("#") and _WORKER_HEADING.search(line)
        ]
        assert worker_headings, "no worker section recognised in implement-feature"

    def test_a_synthetic_worker_prompt_would_be_caught(self) -> None:
        """Pin the guard's teeth: a worker section with a real call is detected."""
        payload = (
            "# Skill\n"
            "## Phase B: Package Execution Protocol (Every Worker Agent)\n"
            "```python\n"
            "record.write_both()\n"
            "```\n"
        )
        sites = _markdown_code_call_sites(payload)
        assert len(sites) == 1
        assert any(_WORKER_HEADING.search(h) for h in sites[0][0])

    def test_prose_mentioning_write_both_is_not_a_call_site(self) -> None:
        """Prose is not evidence; only executable blocks are."""
        payload = (
            "# Skill\n"
            "## Phase B: Package Execution Protocol (Every Worker Agent)\n"
            "Workers never call `write_both()` — the orchestrator does.\n"
        )
        assert _markdown_code_call_sites(payload) == []


# ─────────────────────────────────────────────────────────────────────────────
# 1.7 — A hand-edited session log still reports drift
# ─────────────────────────────────────────────────────────────────────────────


_HAND_EDIT = """
## Phase: Hand Edit (2026-08-28)

**Agent**: a-human | **Session**: N/A

### Decisions
1. **Edited straight into the file** `architectural: {cap}` — bypassing PhaseRecord entirely.
"""


class TestHandEditedLogStillReportsDrift:
    """Spec scenario: A hand-edited session log still reports drift.

    Binding regeneration to `write_both()` closes one cause. It must not become
    a way to stop checking: a log written by any path that bypasses
    `PhaseRecord` still stales the index and must still block.
    """

    @staticmethod
    def _repo_with_current_index(root: Path) -> Path:
        _seed_repository(root)
        log = root / "openspec/changes/seed-change/session-log.md"
        log.parent.mkdir(parents=True)
        log.write_text(
            "# Session Log: seed-change\n\n"
            "## Phase: Plan (2026-08-27)\n\n"
            "**Agent**: claude_code | **Session**: N/A\n\n"
            "### Decisions\n"
            f"1. **Seeded** `architectural: {CAPABILITY}` — the starting state.\n",
            encoding="utf-8",
        )
        _fresh_render(root, root / "docs" / "decisions")
        return root

    def test_producer_reports_drift_for_a_hand_edited_log(self, tmp_path: Path) -> None:
        from _runtime import ProducerStatus
        from producer_decisions import DecisionsTimelineProducer

        repo = self._repo_with_current_index(tmp_path)
        clean = DecisionsTimelineProducer().run("check", repo, "d" * 40)
        assert clean.status is ProducerStatus.FRESH, clean

        log = repo / "openspec/changes/seed-change/session-log.md"
        log.write_text(
            log.read_text(encoding="utf-8") + _HAND_EDIT.format(cap=CAPABILITY),
            encoding="utf-8",
        )

        drifted = DecisionsTimelineProducer().run("check", repo, "d" * 40)
        assert drifted.status is ProducerStatus.DEGRADED, drifted
        assert drifted.artifacts, "drift reported without naming a stale artifact"
        assert any(
            "docs/decisions" in a.path for a in drifted.artifacts
        ), drifted.artifacts

    @pytest.mark.parametrize("event", ["push", "merge_group", None])
    def test_that_drift_contributes_to_the_blocking_exit_code(
        self, tmp_path: Path, event: str | None
    ) -> None:
        import gate
        import orchestrator
        from producer_decisions import DecisionsTimelineProducer
        from registry import DECISIONS_TIMELINE

        repo = self._repo_with_current_index(tmp_path)
        log = repo / "openspec/changes/seed-change/session-log.md"
        log.write_text(
            log.read_text(encoding="utf-8") + _HAND_EDIT.format(cap=CAPABILITY),
            encoding="utf-8",
        )
        drifted = DecisionsTimelineProducer().run("check", repo, "d" * 40)

        outcome, _err = orchestrator.decide_outcome((drifted,), None)
        refresh = orchestrator.RefreshResult(
            operation_id=None,
            outcome=outcome,
            producer_results=(drifted,),
            semantic_index=None,
        )
        result = gate.run_gate(
            repo,
            revision="c" * 40,
            changed_files=(),
            event=event,
            check_runner=lambda repository, **_kw: refresh,
            context_impact_runner=lambda argv: (0, '{"packages": []}'),
        )
        blocking = [f["producer_id"] for f in result.report["blocking_drift"]]
        assert DECISIONS_TIMELINE in blocking, result.report["blocking_drift"]
        assert result.exit_code == gate.EXIT_DRIFT

    def test_the_finding_is_reported_on_a_pull_request_too(self, tmp_path: Path) -> None:
        """Attribution filters the *exit code*, never the report."""
        import gate
        import orchestrator
        from producer_decisions import DecisionsTimelineProducer
        from registry import DECISIONS_TIMELINE

        repo = self._repo_with_current_index(tmp_path)
        log = repo / "openspec/changes/seed-change/session-log.md"
        log.write_text(
            log.read_text(encoding="utf-8") + _HAND_EDIT.format(cap=CAPABILITY),
            encoding="utf-8",
        )
        drifted = DecisionsTimelineProducer().run("check", repo, "d" * 40)
        outcome, _err = orchestrator.decide_outcome((drifted,), None)
        refresh = orchestrator.RefreshResult(
            operation_id=None,
            outcome=outcome,
            producer_results=(drifted,),
            semantic_index=None,
        )
        result = gate.run_gate(
            repo,
            revision="c" * 40,
            changed_files=(),
            event="pull_request",
            check_runner=lambda repository, **_kw: refresh,
            context_impact_runner=lambda argv: (0, '{"packages": []}'),
        )
        assert DECISIONS_TIMELINE in [
            f["producer_id"] for f in result.report["blocking_drift"]
        ]


# ─────────────────────────────────────────────────────────────────────────────
# 1.8 — Acceptance criterion and the latency NFR
# ─────────────────────────────────────────────────────────────────────────────


class TestAcceptanceCriterion:
    """A branch whose only change is a `write_both()` session-log write is clean.

    Expressed against the same producer the gate runs, so it verifies the
    criterion rather than a paraphrase of it.
    """

    def test_write_both_leaves_the_decisions_producer_fresh(self, repo: Path) -> None:
        from _runtime import ProducerStatus
        from producer_decisions import DecisionsTimelineProducer

        _record().write_both(coordinator_writer=_StubWriter())
        checked = DecisionsTimelineProducer().run("check", repo, "d" * 40)
        assert checked.status is ProducerStatus.FRESH, checked

    def test_decisions_timeline_is_not_in_blocking_drift(self, repo: Path) -> None:
        import gate
        import orchestrator
        from producer_decisions import DecisionsTimelineProducer
        from registry import DECISIONS_TIMELINE

        _record().write_both(coordinator_writer=_StubWriter())
        checked = DecisionsTimelineProducer().run("check", repo, "d" * 40)
        outcome, _err = orchestrator.decide_outcome((checked,), None)
        refresh = orchestrator.RefreshResult(
            operation_id=None,
            outcome=outcome,
            producer_results=(checked,),
            semantic_index=None,
        )
        result = gate.run_gate(
            repo,
            revision="c" * 40,
            changed_files=(),
            event="push",
            check_runner=lambda repository, **_kw: refresh,
            context_impact_runner=lambda argv: (0, '{"packages": []}'),
        )
        assert DECISIONS_TIMELINE not in [
            f["producer_id"] for f in result.report["blocking_drift"]
        ]


#: NFR: added wall-clock per `write_both()`, measured at this repository's
#: real archive size rather than at a synthetic one.
_LATENCY_BUDGET_MS = 250.0


class TestRegenerationLatency:
    def test_step_four_stays_within_the_latency_budget(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Measure the real command against the real archive, into a tmp output.

        Reads this repository's `openspec/changes` (60 session logs across 168
        changes) so the number means something, and writes the rendered index
        to `tmp_path` so the committed one is never touched.
        """
        argv = phase_record._decision_index_command(
            generator=phase_record._decision_index_generator(),
            archive_root=REPO_ROOT / "openspec" / "changes",
            decisions_dir=tmp_path / "decisions",
            capabilities_root=REPO_ROOT / "openspec" / "specs",
        )
        samples: list[float] = []
        for _ in range(3):
            start = time.perf_counter()
            proc = subprocess.run(argv, capture_output=True, text=True, check=False)
            samples.append((time.perf_counter() - start) * 1000.0)
            assert proc.returncode == 0, proc.stderr

        best = min(samples)
        with capsys.disabled():
            print(
                f"\nstep four added wall-clock: best {best:.1f} ms of "
                f"{[f'{s:.1f}' for s in samples]} (budget {_LATENCY_BUDGET_MS:.0f} ms)"
            )
        assert best <= _LATENCY_BUDGET_MS, f"{best:.1f} ms exceeds the NFR budget"
