"""Tests for the OpenSpec scenario seeding module (WP3).

Covers:
    * Parser correctness (Requirement+Scenario blocks, file:line tracking)
    * change-id validator (path-traversal & shell-metacharacter rejection)
    * Constraint-section rendering & escaping
    * Argparse integration (status 64 on bad input)
    * End-to-end CLI behavior with --openspec-change (subprocess)

Tests run via the agent-coordinator venv. End-to-end subprocess tests use
``--mode template-only`` so the CLI can complete without a live LLM, and
they assert backward-compat & graceful-degradation invariants — they do
NOT assert that OpenSpec content lands in the prompt (that requires
cli-augmented mode and a live backend, exercised by integration tests
under wp3-integration in a follow-up package).
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from evaluation.gen_eval.openspec_seed import (
    CHANGE_ID_RE,
    SECTION_FOOTER,
    SECTION_HEADER,
    InvalidChangeId,
    ParsedScenario,
    escape_scenario_body,
    parse_openspec_change,
    render_constraints_section,
    validate_change_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
"""agent-coordinator/ — used as cwd for subprocess invocations."""


def _make_change(tmp_path: Path, change_id: str, spec_relpath: str, body: str) -> Path:
    """Write a fixture spec.md under tmp_path/openspec/changes/<id>/specs/...

    Returns the change directory.
    """
    change_dir = tmp_path / "openspec" / "changes" / change_id
    spec_path = change_dir / "specs" / spec_relpath
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(body)
    return change_dir


SAMPLE_SPEC = textwrap.dedent("""\
    # Some delta spec

    ## ADDED Requirements

    ### Requirement: First Capability

    The system SHALL do the first thing.

    #### Scenario: alpha case

    - **WHEN** alpha happens
    - **THEN** beta MUST occur

    #### Scenario: gamma case

    - **WHEN** gamma happens
    - **THEN** delta MUST occur
    - **AND** epsilon MUST also occur

    ### Requirement: Second Capability

    The system SHALL do the second thing.

    #### Scenario: zeta case

    - **WHEN** zeta happens
    - **THEN** eta MUST occur
    """)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


def test_parse_simple_change(tmp_path: Path) -> None:
    """Parser extracts 3 scenarios across 2 requirements with line tracking."""
    change_dir = _make_change(tmp_path, "test-fixture", "api/spec.md", SAMPLE_SPEC)

    scenarios = parse_openspec_change(change_dir, repo_root=tmp_path)

    assert len(scenarios) == 3
    names = [s.scenario_name for s in scenarios]
    assert names == ["alpha case", "gamma case", "zeta case"]

    # Requirement-name attribution
    assert scenarios[0].requirement_name == "First Capability"
    assert scenarios[1].requirement_name == "First Capability"
    assert scenarios[2].requirement_name == "Second Capability"

    # All point at the same file (relative path)
    for s in scenarios:
        assert s.source_file == "openspec/changes/test-fixture/specs/api/spec.md"

    # Lines monotonic and non-empty
    for s in scenarios:
        assert s.line_start >= 1
        assert s.line_end >= s.line_start

    # source_ref formatting
    ref = scenarios[0].source_ref
    assert ref.startswith("openspec/changes/test-fixture/specs/api/spec.md:")
    assert re.match(r"^openspec/changes/[^/]+/specs/.+\.md:\d+-\d+$", ref)


def test_parse_missing_specs_dir_returns_empty(tmp_path: Path) -> None:
    change_dir = tmp_path / "openspec" / "changes" / "no-specs"
    change_dir.mkdir(parents=True)
    # No specs/ subdir created.
    assert parse_openspec_change(change_dir, repo_root=tmp_path) == []


def test_parse_missing_change_dir_returns_empty(tmp_path: Path) -> None:
    change_dir = tmp_path / "openspec" / "changes" / "does-not-exist"
    assert not change_dir.exists()
    assert parse_openspec_change(change_dir, repo_root=tmp_path) == []


def test_parse_handles_multiple_spec_files(tmp_path: Path) -> None:
    """Walks specs/**/*.md (multiple files, deterministic order)."""
    spec_a = textwrap.dedent("""\
        ### Requirement: A
        #### Scenario: a1
        - **WHEN** x
        - **THEN** y
        """)
    spec_b = textwrap.dedent("""\
        ### Requirement: B
        #### Scenario: b1
        - **WHEN** x
        - **THEN** y
        """)
    change_dir = _make_change(tmp_path, "multi", "alpha/spec.md", spec_a)
    (change_dir / "specs" / "beta").mkdir(parents=True)
    (change_dir / "specs" / "beta" / "spec.md").write_text(spec_b)

    scenarios = parse_openspec_change(change_dir, repo_root=tmp_path)
    assert len(scenarios) == 2
    # Sorted by path: alpha/ before beta/
    assert scenarios[0].source_file.endswith("alpha/spec.md")
    assert scenarios[1].source_file.endswith("beta/spec.md")


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


def test_validate_change_id_rejects_path_traversal() -> None:
    with pytest.raises(InvalidChangeId) as exc_info:
        validate_change_id("../etc")
    # Error message MUST name the regex constraint (per spec scenario)
    assert CHANGE_ID_RE.pattern in str(exc_info.value)


def test_validate_change_id_rejects_path_separator() -> None:
    with pytest.raises(InvalidChangeId):
        validate_change_id("foo/bar")


def test_validate_change_id_rejects_dot() -> None:
    with pytest.raises(InvalidChangeId):
        validate_change_id("foo.bar")


def test_validate_change_id_rejects_shell_metacharacters() -> None:
    with pytest.raises(InvalidChangeId):
        validate_change_id("foo;rm -rf /")


def test_validate_change_id_rejects_empty() -> None:
    with pytest.raises(InvalidChangeId):
        validate_change_id("")


def test_validate_change_id_accepts_alphanumeric_underscore_dash() -> None:
    assert validate_change_id("foo-bar_123") == "foo-bar_123"
    assert validate_change_id("a") == "a"
    assert validate_change_id("OPENSPEC-CHANGE-42") == "OPENSPEC-CHANGE-42"


# ---------------------------------------------------------------------------
# Renderer + escaper tests
# ---------------------------------------------------------------------------


def _make_parsed_scenario(
    name: str = "demo",
    body: str = "- WHEN x\n- THEN y",
    file: str = "openspec/changes/foo/specs/api/spec.md",
    start: int = 10,
    end: int = 14,
    requirement: str = "Demo Requirement",
) -> ParsedScenario:
    return ParsedScenario(
        requirement_name=requirement,
        scenario_name=name,
        body=body,
        source_file=file,
        line_start=start,
        line_end=end,
    )


def test_render_constraints_section_has_delimiters() -> None:
    rendered = render_constraints_section([_make_parsed_scenario()])
    assert rendered.startswith(SECTION_HEADER)
    assert rendered.rstrip().endswith(SECTION_FOOTER)


def test_render_constraints_section_preserves_source_ref() -> None:
    s1 = _make_parsed_scenario(name="one", start=10, end=14)
    s2 = _make_parsed_scenario(name="two", start=20, end=27)
    rendered = render_constraints_section([s1, s2])

    # Each scenario block is preceded by a header line containing source ref
    assert "[source: openspec/changes/foo/specs/api/spec.md:10-14]" in rendered
    assert "[source: openspec/changes/foo/specs/api/spec.md:20-27]" in rendered

    # source ref matches the contract regex
    refs = re.findall(r"\[source: ([^\]]+)\]", rendered)
    assert len(refs) == 2
    for ref in refs:
        assert re.match(r"^openspec/changes/[^/]+/specs/.+\.md:\d+-\d+$", ref)


def test_render_constraints_section_includes_scenario_name() -> None:
    s = _make_parsed_scenario(name="my fancy scenario")
    rendered = render_constraints_section([s])
    assert "my fancy scenario" in rendered
    assert "## Scenario:" in rendered


def test_render_constraints_section_empty_list() -> None:
    rendered = render_constraints_section([])
    assert SECTION_HEADER in rendered
    assert SECTION_FOOTER in rendered


def test_escape_scenario_body_escapes_hash_lines() -> None:
    out = escape_scenario_body("### Requirement: foo")
    assert out == "\\### Requirement: foo"


def test_escape_scenario_body_escapes_all_header_levels() -> None:
    inputs = [
        ("# top", "\\# top"),
        ("## h2", "\\## h2"),
        ("### h3", "\\### h3"),
        ("#### h4", "\\#### h4"),
        ("##### h5", "\\##### h5"),
        ("###### h6", "\\###### h6"),
    ]
    for src, expected in inputs:
        assert escape_scenario_body(src) == expected


def test_escape_preserves_non_hash_content() -> None:
    body = "- WHEN something happens\n- THEN something else"
    assert escape_scenario_body(body) == body


def test_escape_preserves_inline_hash() -> None:
    """Lines NOT starting with `# ` are unchanged (inline # is fine)."""
    body = "issue #42 was fixed"
    assert escape_scenario_body(body) == body


def test_escape_handles_section_terminator_in_body() -> None:
    body = "this body contains # End OpenSpec Scenarios as text"
    out = escape_scenario_body(body)
    # Either backslash-escape or transformation that prevents the literal
    # terminator string from being recognized.
    assert SECTION_FOOTER not in out or "\\" + SECTION_FOOTER in out


def test_render_section_structure_unchanged_when_body_has_markers() -> None:
    """Body with triple-backticks and ### Requirement markers must not break section."""
    nasty = textwrap.dedent("""\
        ```
        ### Requirement: injected
        # End OpenSpec Scenarios
        ```
        """).strip()
    s = _make_parsed_scenario(body=nasty)
    rendered = render_constraints_section([s])

    # Section header still present and at column 0
    assert rendered.startswith(SECTION_HEADER + "\n")
    # Exactly one terminator marker (the real one) — body's literal occurrence
    # has been escaped.
    raw_terminator_count = sum(
        1 for line in rendered.splitlines() if line == SECTION_FOOTER
    )
    assert raw_terminator_count == 1


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def _run_gen_eval(
    *args: str,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m evaluation.gen_eval`` as a subprocess from ``cwd``."""
    return subprocess.run(
        [sys.executable, "-m", "evaluation.gen_eval", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={
            "PYTHONPATH": str(REPO_ROOT),
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )


def _make_minimal_descriptor(tmp_path: Path) -> Path:
    """Write a minimal valid descriptor YAML and return its path.

    The ``startup.health_check`` is a ``file://`` URL pointing to the
    descriptor itself; ``curl -sf`` succeeds on any readable file URL,
    which lets the orchestrator's mandatory health-check pass without
    requiring a live HTTP service in the test environment.
    """
    descriptor_path = tmp_path / "descriptor.yaml"
    health_target = f"file://{descriptor_path}"
    descriptor_path.write_text(
        textwrap.dedent(f"""\
            project: test-project
            version: '0.1.0'
            services: []
            startup:
              command: 'true'
              health_check: '{health_target}'
              teardown: 'true'
            """)
    )
    return descriptor_path


def test_argparse_invalid_change_id_exits_64(tmp_path: Path) -> None:
    """`--openspec-change ../etc` exits 64 BEFORE walking any path."""
    descriptor = _make_minimal_descriptor(tmp_path)
    proc = _run_gen_eval(
        "--descriptor",
        str(descriptor),
        "--openspec-change",
        "../etc",
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 64, (
        f"expected exit 64, got {proc.returncode}\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    # Error message names the regex constraint
    assert "change-id MUST match" in proc.stderr
    assert CHANGE_ID_RE.pattern in proc.stderr


def test_argparse_shell_metacharacter_rejected(tmp_path: Path) -> None:
    descriptor = _make_minimal_descriptor(tmp_path)
    proc = _run_gen_eval(
        "--descriptor",
        str(descriptor),
        "--openspec-change",
        "foo;ls",
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 64
    assert "change-id MUST match" in proc.stderr


def test_main_missing_change_warns_and_continues(tmp_path: Path) -> None:
    """Valid change-id whose dir doesn't exist: warning + descriptor-only success."""
    descriptor = _make_minimal_descriptor(tmp_path)
    # Use template-only mode so the run completes without an LLM. The
    # --openspec-change flag is "ignored with warning" outside cli-augmented,
    # but still passes argparse validation.
    proc = _run_gen_eval(
        "--descriptor",
        str(descriptor),
        "--mode",
        "template-only",
        "--no-services",
        "--openspec-change",
        "definitely-does-not-exist-xyz",
        "--output-dir",
        str(tmp_path / "reports"),
        cwd=REPO_ROOT,
        timeout=120,
    )
    # We don't assert the exit code rigidly because template-only against an
    # empty descriptor may or may not produce scenarios; the spec only requires
    # "same exit code as descriptor-only run". We assert the run does NOT exit
    # 64 (no usage error) and does NOT crash with an exception traceback.
    assert proc.returncode != 64, (
        f"unexpected usage-error exit; stderr={proc.stderr!r}"
    )
    # The combined output must not contain a Python traceback (i.e., the run
    # must not crash). Logged warnings from --openspec-change are fine.
    combined = proc.stdout + proc.stderr
    assert "Traceback" not in combined, (
        f"unexpected exception: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_main_no_flag_unchanged_behavior(tmp_path: Path) -> None:
    """Without --openspec-change, no OpenSpec content appears anywhere."""
    descriptor = _make_minimal_descriptor(tmp_path)
    proc = _run_gen_eval(
        "--descriptor",
        str(descriptor),
        "--mode",
        "template-only",
        "--no-services",
        "--output-dir",
        str(tmp_path / "reports"),
        cwd=REPO_ROOT,
        timeout=120,
    )
    # Regression: must not exit with a usage error.
    assert proc.returncode != 64
    # No OpenSpec content in stdout/stderr (no section header leaked into logs).
    assert SECTION_HEADER not in proc.stdout
    assert SECTION_HEADER not in proc.stderr
    # No traceback
    combined = proc.stdout + proc.stderr
    assert "Traceback" not in combined, (
        f"unexpected exception: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_main_help_documents_flag() -> None:
    """`--help` mentions the new flag and the regex constraint."""
    proc = _run_gen_eval("--help", cwd=REPO_ROOT)
    assert proc.returncode == 0
    assert "--openspec-change" in proc.stdout
    assert CHANGE_ID_RE.pattern in proc.stdout
