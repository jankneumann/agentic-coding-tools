"""bootstrap-cloud.sh must survive a clone with no skill mirrors yet.

`verify_skills` counts SKILL.md files to decide whether to run the installer.
Counting them with a single `find` over both mirror directories looks harmless
and is not: `find` exits 1 when a path does not exist, `set -o pipefail` carries
that status through the pipe, and `set -e` then fails the assignment and aborts
the run.

The case that triggers it is a fresh clone where neither mirror exists -- which
is exactly the case verify_skills exists to repair.  It also fails silently: the
script's `trap ... ERR` does not fire inside a function without `set -E`, so the
bootstrap ends mid-pass with its last OK line printed and nothing else, which
reads as a clean run.

These tests pin the behavior at the seam that matters: verify_skills must reach
its decision and invoke the installer when no skills are present.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

BOOTSTRAP_CLOUD = (
    Path(__file__).resolve().parents[2]
    / "session-bootstrap/scripts/bootstrap-cloud.sh"
)

# Printed by the stub installer, so a test can tell "the installer ran" from
# "verify_skills returned early".
INSTALLER_MARKER = "STUB_INSTALLER_RAN"
# Printed after verify_skills returns.  Absent => the function aborted the run.
REACHED_MARKER = "REACHED_AFTER_VERIFY"


def _sourceable_prefix(tmp_path: Path) -> Path:
    """Copy bootstrap-cloud.sh up to its "# Main" block so it can be sourced.

    Everything above the invocation block is definitions plus the profile and
    argument setup, which is what these tests need; sourcing the whole file
    would run the full repair pass.
    """
    text = BOOTSTRAP_CLOUD.read_text()
    marker = "# Main\n"
    assert marker in text, "bootstrap-cloud.sh no longer has a '# Main' marker"
    path = tmp_path / "bootstrap_prefix.sh"
    path.write_text(text[: text.index(marker)])
    return path


def _make_project(tmp_path: Path, *, with_installer: bool = True) -> Path:
    root = tmp_path / "repo"
    (root / "skills").mkdir(parents=True)
    if with_installer:
        # Stand in for skills/install.sh: announce itself and produce one skill
        # in each mirror, the way a real install would.
        (root / "skills/install.sh").write_text(
            "#!/usr/bin/env bash\n"
            f'echo "{INSTALLER_MARKER}"\n'
            'mkdir -p "$(dirname "$0")/../.claude/skills/stub"\n'
            'mkdir -p "$(dirname "$0")/../.agents/skills/stub"\n'
            'echo "# stub" > "$(dirname "$0")/../.claude/skills/stub/SKILL.md"\n'
            'echo "# stub" > "$(dirname "$0")/../.agents/skills/stub/SKILL.md"\n'
        )
    return root


def _run_verify_skills(
    project: Path, tmp_path: Path
) -> subprocess.CompletedProcess:
    prefix = _sourceable_prefix(tmp_path)
    script = f'source "{prefix}"; verify_skills; echo "{REACHED_MARKER}"'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "CLAUDE_PROJECT_DIR": str(project),
        },
    )


def test_missing_mirrors_do_not_abort_the_run(tmp_path: Path) -> None:
    """The regression: neither mirror exists, as on any fresh clone."""
    project = _make_project(tmp_path)

    result = _run_verify_skills(project, tmp_path)

    combined = result.stdout + result.stderr
    assert REACHED_MARKER in combined, (
        "verify_skills aborted the run instead of returning. Under "
        "`set -euo pipefail` a find over a non-existent mirror directory "
        f"fails the count and kills the bootstrap.\n{combined}"
    )
    assert result.returncode == 0, combined


def test_missing_mirrors_trigger_the_installer(tmp_path: Path) -> None:
    """Aborting early would also skip the repair this function exists for."""
    project = _make_project(tmp_path)

    result = _run_verify_skills(project, tmp_path)

    combined = result.stdout + result.stderr
    assert INSTALLER_MARKER in combined, (
        f"the installer was never invoked with zero skills present\n{combined}"
    )
    assert (project / ".claude/skills/stub/SKILL.md").is_file()


@pytest.mark.parametrize("present", [".claude", ".agents"])
def test_one_mirror_present_is_enough_to_skip_install(
    tmp_path: Path, present: str
) -> None:
    """A populated mirror means no repair is needed, from either harness."""
    project = _make_project(tmp_path)
    skill = project / present / "skills/already/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# already\n")

    result = _run_verify_skills(project, tmp_path)

    combined = result.stdout + result.stderr
    assert REACHED_MARKER in combined, combined
    assert INSTALLER_MARKER not in combined, (
        f"reinstalled over an existing mirror\n{combined}"
    )


def test_empty_mirror_directory_still_triggers_install(
    tmp_path: Path,
) -> None:
    """A directory with no SKILL.md is a failed install, not a healthy one.

    This is why the check counts files instead of testing for the directory.
    """
    project = _make_project(tmp_path)
    (project / ".claude/skills").mkdir(parents=True)

    result = _run_verify_skills(project, tmp_path)

    combined = result.stdout + result.stderr
    assert INSTALLER_MARKER in combined, combined


def test_non_source_repo_returns_without_installing(tmp_path: Path) -> None:
    """A consumer repo has no skills/install.sh and must be left alone."""
    project = _make_project(tmp_path, with_installer=False)

    result = _run_verify_skills(project, tmp_path)

    combined = result.stdout + result.stderr
    assert REACHED_MARKER in combined, combined
    assert INSTALLER_MARKER not in combined, combined
