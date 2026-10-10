"""install.sh --check compares the stamp: checkout drift, runtime drift, unpinned."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
VERSION = (SKILLS_ROOT.parent / "VERSION").read_text().strip()

QUIET = [
    "--deps", "none", "--openspec-assets", "none", "--openspec-cli", "none",
    "--python-tools", "none",
]


def _run(install_sh: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(install_sh), *args], capture_output=True, text=True
    )


def _install(install_sh: Path, target: Path) -> None:
    result = _run(install_sh, ["--target", str(target), "--mode", "copy", *QUIET])
    assert result.returncode == 0, result.stderr


def _check(install_sh: Path, target: Path) -> subprocess.CompletedProcess[str]:
    return _run(install_sh, ["--target", str(target), "--check"])


@pytest.fixture()
def installed(tmp_path: Path) -> Path:
    target = tmp_path / "consumer"
    target.mkdir()
    _install(SKILLS_ROOT / "install.sh", target)
    return target


def _stamp_path(target: Path) -> Path:
    return target / ".agentic-toolkit" / "stamp.json"


def test_pinned_payload_matches(installed: Path) -> None:
    result = _check(SKILLS_ROOT / "install.sh", installed)
    assert result.returncode == 0, result.stderr
    assert "Pinned toolkit matches" in result.stdout
    assert VERSION in result.stdout
    stamp = json.loads(_stamp_path(installed).read_text())
    assert stamp["payload_hash"][:19] in result.stdout


def test_checkout_drift(tmp_path: Path) -> None:
    # Toolkit checkout A installs; checkout A then moves to a different payload (B).
    src = tmp_path / "skills"
    shutil.copytree(
        SKILLS_ROOT, src,
        ignore=shutil.ignore_patterns(".venv", "tests", "__pycache__", "node_modules", ".pytest_cache"),
    )
    (tmp_path / "VERSION").write_text(VERSION + "\n")
    target = tmp_path / "consumer"
    target.mkdir()
    _install(src / "install.sh", target)
    stamp = json.loads(_stamp_path(target).read_text())
    stamp["source_commit"] = "a" * 40
    _stamp_path(target).write_text(json.dumps(stamp))

    with (src / "SKILLS_DRIFT.md").open("w") as handle:
        handle.write("new file in checkout B\n")
    skill_md = next(src.glob("*/SKILL.md"))
    skill_md.write_text(skill_md.read_text() + "\nchanged in B\n")

    result = _check(src / "install.sh", target)
    assert result.returncode == 1
    assert "Checkout drift" in result.stderr
    assert VERSION in result.stderr
    assert "a" * 40 in result.stderr
    assert "Runtime drift" not in result.stderr


def test_checkout_drift_with_changed_skill_set_is_not_runtime_drift(tmp_path: Path) -> None:
    # Checkout A installs; checkout B then re-scopes a portable skill so B's
    # manifest no longer names it. The mirrors are still byte-identical to the
    # pinned payload (they hold the skill and A's manifest), so only checkout
    # drift may be reported: each mirror must be hashed against its own synced
    # manifest, not against checkout B's (ledger 35).
    src = tmp_path / "skills"
    shutil.copytree(
        SKILLS_ROOT, src,
        ignore=shutil.ignore_patterns(".venv", "tests", "__pycache__", "node_modules", ".pytest_cache"),
    )
    (tmp_path / "VERSION").write_text(VERSION + "\n")
    target = tmp_path / "consumer"
    target.mkdir()
    _install(src / "install.sh", target)

    manifest_path = src / "install-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["skills"]["json-canvas"] == {"distribution": "portable"}
    manifest["skills"]["json-canvas"] = {
        "distribution": "repository-scoped",
        "reason": "re-scoped in checkout B",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    result = _check(src / "install.sh", target)
    assert result.returncode == 1
    assert "Checkout drift" in result.stderr
    assert "Runtime drift" not in result.stderr
    # The mirrors must actually have been hashed (against their own synced
    # manifest); a missing mirror manifest would also suppress "Runtime drift".
    assert "Cannot compute mirror payload hash" not in result.stderr


def test_runtime_drift_names_the_agent(installed: Path) -> None:
    skill_md = next((installed / ".agents" / "skills").glob("*/SKILL.md"))
    skill_md.write_text(skill_md.read_text() + "\nlocal edit\n")

    result = _check(SKILLS_ROOT / "install.sh", installed)
    assert result.returncode == 1
    assert "Runtime drift" in result.stderr
    assert "installed agents copies" in result.stderr
    assert "installed claude copies" not in result.stderr
    assert "Checkout drift" not in result.stderr
    # Like checkout drift, the runtime-drift message names the pin: version and commit.
    stamp = json.loads(_stamp_path(installed).read_text())
    assert VERSION in result.stderr
    assert (stamp["source_commit"] or "unknown") in result.stderr


def test_unpinned_repository_is_advisory(installed: Path) -> None:
    _stamp_path(installed).unlink()
    result = _check(SKILLS_ROOT / "install.sh", installed)
    assert result.returncode == 0, result.stderr
    assert "Unpinned" in result.stdout
    assert "install.sh" in result.stdout
    assert not _stamp_path(installed).exists()


def test_unpinned_does_not_mask_mirror_parity_failure(installed: Path) -> None:
    _stamp_path(installed).unlink()
    skill_md = next((installed / ".claude" / "skills").glob("*/SKILL.md"))
    skill_md.write_text(skill_md.read_text() + "\nedit\n")
    result = _check(SKILLS_ROOT / "install.sh", installed)
    assert result.returncode == 1
    assert "Installed skill mirror differs" in result.stderr


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        json.dumps({"schema_version": 2, "payload_hash": "sha256:abc"}),
        json.dumps({"schema_version": 1}),
    ],
    ids=["bad-json", "not-object", "wrong-schema", "no-hash"],
)
def test_invalid_stamp_fails_loud_and_is_not_rewritten(installed: Path, content: str) -> None:
    _stamp_path(installed).write_text(content)
    result = _check(SKILLS_ROOT / "install.sh", installed)
    assert result.returncode == 1
    assert "Invalid toolkit stamp" in result.stderr
    assert str(_stamp_path(installed)) in result.stderr
    assert _stamp_path(installed).read_text() == content


def test_self_install_skips_stamp_comparison(tmp_path: Path) -> None:
    (tmp_path / "skills").symlink_to(SKILLS_ROOT)
    _install(SKILLS_ROOT / "install.sh", tmp_path)
    # A bogus stamp must be ignored on a self-install.
    _stamp_path(tmp_path).parent.mkdir(exist_ok=True)
    _stamp_path(tmp_path).write_text("{not json")
    result = _check(SKILLS_ROOT / "install.sh", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "source tree is the pin" in result.stdout
    assert "Invalid toolkit stamp" not in result.stderr


def test_usage_documents_stamp_comparison() -> None:
    result = _run(SKILLS_ROOT / "install.sh", ["--help"])
    assert result.returncode == 0
    assert "stamp.json" in result.stdout
    assert "checkout drift" in result.stdout
