"""Wiring test for the requirement-to-contract traceability gate (WP-wiring, task 5.6).

The traceability gate in skills/validate-feature/SKILL.md section 7.0b detects
whether packages/gen-eval/scripts/check_traceability.py and openspec/contracts/
exist, and — when they do — invokes the gate bare at `--scope change --change
<id>`, failing validation on a non-zero exit and printing an explicit SKIP
when the gate is unavailable. We test that bash logic by extracting it into a
shell script fragment and driving it against a stub gate script whose exit
code and stdout we control, mirroring
skills/tests/validate-feature/test_gen_eval_mode_selection.py's approach for
the neighboring Gen-Eval phase.

Spec scenarios covered (openspec/changes/trace-requirements-to-contracts/specs/skill-workflow/spec.md,
"Validation-Time Requirement Traceability Gate"):
- "Gate runs during validation" (invoked at --scope change --change <id>, bare)
- "Gate failure fails validation" (non-zero exit -> TRACE_RESULT=fail, output captured)
- "Gate absent in a consumer repository" (missing script or missing
  openspec/contracts/ -> printed SKIP naming what is missing, exit 0)
- "Skill wiring is covered by skill tests" (this file)
"""
from __future__ import annotations

import stat
import subprocess
import textwrap
from pathlib import Path

# Bash fragment extracted from skills/validate-feature/SKILL.md section 7.0b.
# Kept byte-for-byte in sync with that section's code block.
TRACE_GATE_FRAGMENT = textwrap.dedent("""
    TRACE_GATE="$PROJECT_ROOT/packages/gen-eval/scripts/check_traceability.py"
    TRACE_CONTRACTS_DIR="$PROJECT_ROOT/openspec/contracts"

    if [ ! -f "$TRACE_GATE" ]; then
      echo "SKIP: requirement-traceability gate unavailable ($TRACE_GATE not found). Skipping."
      TRACE_RESULT="skip"
    elif [ ! -d "$TRACE_CONTRACTS_DIR" ]; then
      echo "SKIP: requirement-traceability gate unavailable ($TRACE_CONTRACTS_DIR not found). Skipping."
      TRACE_RESULT="skip"
    else
      TRACE_PYTHON="$PROJECT_ROOT/packages/gen-eval/.venv/bin/python"
      if [ ! -f "$TRACE_PYTHON" ]; then TRACE_PYTHON="python3"; fi
      # Bare, never piped — a pipeline's $? is the last stage's exit status, so
      # `check_traceability.py | tail` would report tail's 0 on a failing gate.
      TRACE_OUTPUT=$(cd "$PROJECT_ROOT/packages/gen-eval" && "$TRACE_PYTHON" scripts/check_traceability.py \\
        --scope change --change "$CHANGE_ID")
      TRACE_EXIT=$?
      echo "$TRACE_OUTPUT"
      if [ $TRACE_EXIT -ne 0 ]; then
        echo "FAIL: requirement-traceability gate exited $TRACE_EXIT"
        TRACE_RESULT="fail"
      else
        echo "PASS: requirement-traceability gate"
        TRACE_RESULT="pass"
      fi
    fi

    # Skip and pass both leave this sub-step at exit 0; fail propagates the
    # gate's own non-zero status so a caller chaining this fragment observes it
    # without re-deriving TRACE_RESULT.
    [ "$TRACE_RESULT" = "fail" ] && exit "$TRACE_EXIT"
    exit 0
""")


def _run(project_root: Path, change_id: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", TRACE_GATE_FRAGMENT],
        env={
            "PROJECT_ROOT": str(project_root),
            "CHANGE_ID": change_id,
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        timeout=10,
    )


def _make_contracts_dir(project_root: Path) -> None:
    (project_root / "openspec" / "contracts").mkdir(parents=True, exist_ok=True)


def _make_stub_gate(project_root: Path, *, exit_code: int, stdout_line: str) -> Path:
    """Write a fake check_traceability.py that ignores real gen_eval/pydantic/yaml
    dependencies and just records its argv + prints a controlled line, so this
    test stays hermetic (no real requirement/contract fixtures needed) while
    still exercising the real argv the skill builds.
    """
    scripts_dir = project_root / "packages" / "gen-eval" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    stub = scripts_dir / "check_traceability.py"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/usr/bin/env python3
            import sys
            print("argv: " + " ".join(sys.argv[1:]))
            print({stdout_line!r})
            sys.exit({exit_code})
            """)
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def test_gate_script_absent_produces_skip_and_passes(tmp_path: Path) -> None:
    """Spec: 'Gate absent in a consumer repository' (missing script) — printed
    SKIP naming the missing path, TRACE_RESULT=skip, exit 0 (not a failure)."""
    # Neither the gate script nor openspec/contracts/ exists.
    result = _run(tmp_path, "example")
    assert result.returncode == 0, result.stderr
    assert "SKIP: requirement-traceability gate unavailable" in result.stdout
    assert "check_traceability.py not found" in result.stdout
    assert "FAIL" not in result.stdout
    assert "PASS" not in result.stdout


def test_contracts_dir_absent_produces_skip_and_passes(tmp_path: Path) -> None:
    """Spec: 'Gate absent in a consumer repository' (missing openspec/contracts/)
    — the gate script alone is not sufficient; contracts/ absence also SKIPs."""
    _make_stub_gate(tmp_path, exit_code=0, stdout_line="unused")
    # Deliberately no openspec/contracts/ directory.
    result = _run(tmp_path, "example")
    assert result.returncode == 0, result.stderr
    assert "SKIP: requirement-traceability gate unavailable" in result.stdout
    assert "openspec/contracts not found" in result.stdout
    assert "FAIL" not in result.stdout
    assert "PASS" not in result.stdout


def test_gate_invoked_bare_at_change_scope(tmp_path: Path) -> None:
    """Spec: 'Gate runs during validation' — invoked with --scope change and
    the active change's identifier, bare (its own stdout/exit status observed
    directly, not through a pipeline)."""
    _make_contracts_dir(tmp_path)
    _make_stub_gate(tmp_path, exit_code=0, stdout_line="3 operations cite 2 requirements.")
    result = _run(tmp_path, "trace-requirements-to-contracts")
    assert result.returncode == 0, result.stderr
    assert "argv: --scope change --change trace-requirements-to-contracts" in result.stdout
    assert "PASS: requirement-traceability gate" in result.stdout
    assert "SKIP" not in result.stdout


def test_gate_failure_fails_validation(tmp_path: Path) -> None:
    """Spec: 'Gate failure fails validation' — a non-zero gate exit is recorded
    as TRACE_RESULT=fail, the gate's own output (naming the violation) is
    captured in stdout for the validation report, and the fragment's own exit
    status propagates the failure rather than swallowing it."""
    _make_contracts_dir(tmp_path)
    _make_stub_gate(
        tmp_path,
        exit_code=1,
        stdout_line="forward failures:\\n  - gen-eval.yaml: cli:--time-budget cites no requirement",
    )
    result = _run(tmp_path, "trace-requirements-to-contracts")
    assert result.returncode == 1, result.stderr
    assert "FAIL: requirement-traceability gate exited 1" in result.stdout
    assert "cites no requirement" in result.stdout  # gate's own violation-naming output is captured
    assert "PASS" not in result.stdout
    assert "SKIP" not in result.stdout
