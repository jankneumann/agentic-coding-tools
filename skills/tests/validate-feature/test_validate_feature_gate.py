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

import re
import stat
import subprocess
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILL_MD = _REPO_ROOT / "skills" / "validate-feature" / "SKILL.md"


def _skill_md_gate_block() -> str:
    """Return the bash block of SKILL.md's section 7.0b, or raise.

    Reading the real file is the point: without this the suite could not
    observe section 7.0b at all.
    """
    md = _SKILL_MD.read_text()
    m = re.search(r"#### 7\.0b\..*?```bash\n(.*?)```", md, re.S)
    if m is None:
        raise AssertionError(
            f"no '#### 7.0b.' section with a bash block found in {_SKILL_MD} — "
            "the traceability gate wiring this suite exists to cover is gone"
        )
    return m.group(1)


# Bash fragment extracted from skills/validate-feature/SKILL.md section 7.0b.
# Kept byte-for-byte in sync with that section's code block;
# test_fragment_matches_skill_md (below) enforces it.
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
  #
  # errexit is suspended across the capture. This fragment is pasted into
  # whatever shell the running agent has, and a failing gate under `set -e`
  # aborts on the assignment itself: the shell dies before `echo "$TRACE_OUTPUT"`
  # ever runs, so the violation text the report is supposed to quote is lost and
  # the operator sees a bare non-zero exit. The gate failing is the case this
  # phase exists to report, so it is precisely the case that must not kill the
  # reporter. Saved and restored rather than left off, so nothing after this
  # block silently loses errexit.
  case $- in *e*) _TRACE_HAD_ERREXIT=1;; *) _TRACE_HAD_ERREXIT=0;; esac
  set +e
  TRACE_OUTPUT=$(cd "$PROJECT_ROOT/packages/gen-eval" && "$TRACE_PYTHON" scripts/check_traceability.py \\
    --scope change --change "$CHANGE_ID")
  TRACE_EXIT=$?
  [ "$_TRACE_HAD_ERREXIT" = "1" ] && set -e
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
[ "${TRACE_RESULT:-}" = "fail" ] && exit "$TRACE_EXIT"
exit 0
""")


def test_fragment_matches_skill_md() -> None:
    """TRACE_GATE_FRAGMENT must be byte-for-byte the bash block in SKILL.md
    section 7.0b.

    Until this existed the suite never opened SKILL.md: every test drove a copy
    of the bash held in this module, so deleting section 7.0b outright left all
    of them green. A wiring test that cannot observe the wiring is testing its
    own fixture. `test_ci_sweep_wiring.test_fragment_matches_ci_yml` is the same
    guard for the CI half; this is its counterpart for the skill half."""
    assert TRACE_GATE_FRAGMENT.strip("\n") == _skill_md_gate_block().strip("\n"), (
        "TRACE_GATE_FRAGMENT has drifted from section 7.0b of "
        f"{_SKILL_MD} — update the constant in this test file to match."
    )


def _run(
    project_root: Path, change_id: str, *, errexit: bool = False,
) -> subprocess.CompletedProcess:
    """Drive the fragment, optionally with errexit on.

    ``errexit=True`` is not hypothetical: this block is pasted into whatever
    shell the running agent has, and `set -e` is a common default in the
    wrapper scripts that drive validation phases."""
    script = project_root / ".trace-gate-under-test.sh"
    script.write_text(TRACE_GATE_FRAGMENT)
    cmd = ["bash", "-e", str(script)] if errexit else ["bash", str(script)]
    return subprocess.run(
        cmd,
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
            # `--help` exits 0 whatever the gate would go on to find — argparse
            # prints usage and stops before any contract is read. The skill uses
            # that as its runnability probe, so a stub that returned the
            # violation exit code here would model an interpreter that cannot
            # run the gate rather than a gate that found violations, and the
            # two have deliberately different outcomes.
            if "--help" in sys.argv[1:]:
                print("usage: check_traceability.py [-h] --scope {{change,capability}}")
                sys.exit(0)
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


def test_gate_failure_still_reports_under_errexit(tmp_path: Path) -> None:
    """Same scenario, driven under `set -e`.

    'Gate failure fails validation' requires the violation text to reach the
    validation report, not merely a non-zero exit. Capturing the gate into
    `TRACE_OUTPUT=$(...)` makes the assignment itself the failing command, so
    under errexit the shell dies there and `echo "$TRACE_OUTPUT"` never runs:
    the exit code survives but every line naming a violation is lost, which is
    the half of the scenario a bare returncode assertion cannot see. The
    fragment therefore suspends errexit across the capture, and this test is
    what holds it to that."""
    _make_contracts_dir(tmp_path)
    _make_stub_gate(
        tmp_path,
        exit_code=1,
        stdout_line="forward failures:\\n  - gen-eval.yaml: cli:--time-budget cites no requirement",
    )
    result = _run(tmp_path, "trace-requirements-to-contracts", errexit=True)
    assert result.returncode == 1, result.stderr
    assert "cites no requirement" in result.stdout, (
        "the gate's violation output was lost under errexit — the validation "
        "report would name no violation"
    )
    assert "FAIL: requirement-traceability gate exited 1" in result.stdout
