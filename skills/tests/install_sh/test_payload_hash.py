"""Payload hash: source/mirror equality, content sensitivity, exclusions."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from payload_hash import hash_payload, main, payload_names  # noqa: E402

INSTALL_SH = SKILLS_ROOT / "install.sh"
MANIFEST = SKILLS_ROOT / "install-manifest.json"


def _make_tree(root: Path) -> None:
    (root / "alpha" / "scripts").mkdir(parents=True)
    (root / "alpha" / "SKILL.md").write_text("alpha\n")
    (root / "alpha" / "scripts" / "run.py").write_text("print(1)\n")
    (root / "shared").mkdir()
    (root / "shared" / "lib.py").write_text("X = 1\n")
    (root / "install-manifest.json").write_text("{}\n")


def test_content_change_changes_hash(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    before = hash_payload(tmp_path, ["alpha"], ["shared"])
    assert before.startswith("sha256:")
    (tmp_path / "alpha" / "scripts" / "run.py").write_text("print(2)\n")
    assert hash_payload(tmp_path, ["alpha"], ["shared"]) != before


@pytest.mark.parametrize("excluded", ["tests", "__pycache__", "node_modules"])
def test_excluded_directories_do_not_affect_hash(tmp_path: Path, excluded: str) -> None:
    _make_tree(tmp_path)
    before = hash_payload(tmp_path, ["alpha"], ["shared"])
    for base in (tmp_path / "alpha", tmp_path / "shared", tmp_path / "alpha" / "scripts"):
        (base / excluded).mkdir()
        (base / excluded / "x.txt").write_text("noise")
    assert hash_payload(tmp_path, ["alpha"], ["shared"]) == before
    (tmp_path / "alpha" / excluded / "x.txt").write_text("changed")
    assert hash_payload(tmp_path, ["alpha"], ["shared"]) == before


def test_new_file_and_manifest_change_hash(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    before = hash_payload(tmp_path, ["alpha"], ["shared"])
    (tmp_path / "alpha" / "extra.md").write_text("e")
    added = hash_payload(tmp_path, ["alpha"], ["shared"])
    assert added != before
    (tmp_path / "install-manifest.json").write_text("{ }\n")
    assert hash_payload(tmp_path, ["alpha"], ["shared"]) != added


def test_symlinked_tree_hashes_identically(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _make_tree(src)
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "alpha").symlink_to(src / "alpha")
    (mirror / "shared").symlink_to(src / "shared")
    (mirror / "install-manifest.json").symlink_to(src / "install-manifest.json")
    assert hash_payload(mirror, ["alpha"], ["shared"]) == hash_payload(src, ["alpha"], ["shared"])


def test_cli_prints_hash_for_real_manifest(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(SKILLS_ROOT), "--manifest", str(MANIFEST)]) == 0
    out = capsys.readouterr().out.strip()
    skills, libs = payload_names(MANIFEST)
    assert out == hash_payload(SKILLS_ROOT, skills, libs)


def test_cli_reports_unreadable_manifest(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path)]) == 2


@pytest.mark.parametrize("mode", ["copy", "rsync"])
def test_source_and_mirror_hash_identically(tmp_path: Path, mode: str) -> None:
    if mode == "rsync" and shutil.which("rsync") is None:
        pytest.skip("rsync not installed; cp fallback covered by copy mode")
    subprocess.run(
        [
            "bash", str(INSTALL_SH), "--target", str(tmp_path), "--mode", mode,
            "--deps", "none", "--openspec-assets", "none", "--openspec-cli", "none",
            "--python-tools", "none",
        ],
        check=True, capture_output=True, text=True,
    )
    skills, libs = payload_names(MANIFEST)
    source = hash_payload(SKILLS_ROOT, skills, libs)
    for agent_dir in (".claude/skills", ".agents/skills"):
        mirror_root = tmp_path / agent_dir
        assert hash_payload(mirror_root, skills, libs) == source
        # The CLI run from the installed copy (consumer layout) agrees.
        cli = subprocess.run(
            [sys.executable, str(mirror_root / "shared" / "payload_hash.py"),
             "--root", str(mirror_root)],
            check=True, capture_output=True, text=True,
        )
        assert cli.stdout.strip() == source
