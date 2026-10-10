"""install.sh writes .agentic-toolkit/stamp.json for consumer installs only."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from payload_hash import hash_payload, payload_names  # noqa: E402

INSTALL_SH = SKILLS_ROOT / "install.sh"
MANIFEST = SKILLS_ROOT / "install-manifest.json"
VERSION_FILE = SKILLS_ROOT.parent / "VERSION"

QUIET = [
    "--deps", "none", "--openspec-assets", "none", "--openspec-cli", "none",
    "--python-tools", "none",
]


def _run(
    args: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        capture_output=True, text=True, env=env,
    )


def _source_hash() -> str:
    skills, libs = payload_names(MANIFEST)
    return hash_payload(SKILLS_ROOT, skills, libs)


def test_consumer_install_writes_stamp(tmp_path: Path) -> None:
    result = _run(["--target", str(tmp_path), "--mode", "copy", "--agents", "claude,agents", *QUIET])
    assert result.returncode == 0, result.stderr
    stamp = json.loads((tmp_path / ".agentic-toolkit" / "stamp.json").read_text())
    assert stamp["schema_version"] == 1
    assert stamp["payload_hash"] == _source_hash()
    assert stamp["agents"] == ["agents", "claude"]
    assert stamp["mode"] == "copy"
    assert stamp["toolkit_version"] == VERSION_FILE.read_text().strip()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp["installed_at"])
    head = subprocess.run(
        ["git", "-C", str(SKILLS_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    expected = head.stdout.strip() if head.returncode == 0 else None
    assert stamp["source_commit"] == expected
    # No temp files left behind in the stamp directory.
    assert sorted(p.name for p in (tmp_path / ".agentic-toolkit").iterdir()) == ["stamp.json"]


def test_single_agent_stamp_lists_only_that_agent(tmp_path: Path) -> None:
    result = _run(["--target", str(tmp_path), "--mode", "copy", "--agents", "claude", *QUIET])
    assert result.returncode == 0, result.stderr
    stamp = json.loads((tmp_path / ".agentic-toolkit" / "stamp.json").read_text())
    assert stamp["agents"] == ["claude"]


def test_self_install_writes_no_stamp(tmp_path: Path) -> None:
    # A target whose ./skills resolves to this skills tree is a self-install.
    (tmp_path / "skills").symlink_to(SKILLS_ROOT)
    result = _run(["--target", str(tmp_path), "--mode", "copy", *QUIET])
    assert result.returncode == 0, result.stderr
    assert "self-install" in result.stdout
    assert not (tmp_path / ".agentic-toolkit").exists()


def test_check_mode_does_not_stamp(tmp_path: Path) -> None:
    result = _run(["--target", str(tmp_path), "--check"])
    assert result.returncode != 0  # nothing installed: mirrors missing
    assert not (tmp_path / ".agentic-toolkit" / "stamp.json").exists()


def test_aborted_install_leaves_previous_stamp_intact(tmp_path: Path) -> None:
    first = _run(["--target", str(tmp_path), "--mode", "copy", *QUIET])
    assert first.returncode == 0, first.stderr
    stamp_path = tmp_path / ".agentic-toolkit" / "stamp.json"
    # Make the prior stamp distinguishable from anything a rewrite could
    # produce: same payload, agents and mode within the same UTC second would
    # otherwise be byte-identical and mask a stamp written too early.
    marked = json.loads(stamp_path.read_text())
    marked["marker"] = "prior-install"
    stamp_path.write_text(json.dumps(marked))
    prior = stamp_path.read_bytes()

    # `--openspec-cli required` fails when the CLI is absent; build a PATH
    # without any `openspec` binary so the install aborts after its sync steps.
    fake_bin = tmp_path / "no_openspec_bin"
    fake_bin.mkdir()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        src_dir = Path(entry)
        if not src_dir.is_dir():
            continue
        try:
            children = list(src_dir.iterdir())
        except OSError:
            continue
        for child in children:
            link = fake_bin / child.name
            if child.name != "openspec" and not link.exists():
                try:
                    link.symlink_to(child)
                except OSError:
                    pass
    env = dict(os.environ, PATH=str(fake_bin))
    second = _run(
        ["--target", str(tmp_path), "--mode", "copy", "--force", "--deps", "none",
         "--openspec-assets", "none", "--openspec-cli", "required", "--python-tools", "none"],
        env=env,
    )
    assert second.returncode != 0
    assert stamp_path.read_bytes() == prior
