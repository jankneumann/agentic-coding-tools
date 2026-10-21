"""Stale runtime mirror detection: mirror vs canonical skills/ payload."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_ROOT))

from shared.mirror_freshness import SYNC_COMMAND, stale_mirror  # noqa: E402

MANIFEST = {"skills": {"alpha": {"distribution": "portable"}}, "shared_libraries": ["shared"]}


def _repo(tmp_path: Path) -> Path:
    skills = tmp_path / "skills"
    (skills / "alpha" / "scripts").mkdir(parents=True)
    (skills / "alpha" / "scripts" / "run.py").write_text("print(1)\n")
    (skills / "shared").mkdir()
    (skills / "shared" / "lib.py").write_text("X = 1\n")
    (skills / "install.sh").write_text("#!/bin/sh\n")
    (skills / "install-manifest.json").write_text(json.dumps(MANIFEST))
    for parent in (".claude", ".agents"):
        mirror = tmp_path / parent / "skills"
        mirror.mkdir(parents=True)
        for name in ("alpha", "shared"):
            shutil.copytree(skills / name, mirror / name)
        shutil.copy(skills / "install-manifest.json", mirror / "install-manifest.json")
    return tmp_path


def _script(repo: Path, parent: str = ".claude") -> Path:
    return repo / parent / "skills" / "alpha" / "scripts" / "run.py"


def test_synced_mirror_is_not_stale(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert stale_mirror(_script(repo)) is None
    assert stale_mirror(_script(repo, ".agents")) is None


def test_mirror_behind_canonical_is_stale(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "skills" / "shared" / "lib.py").write_text("X = 2\n")

    drift = stale_mirror(_script(repo))

    assert drift is not None
    assert drift.mirror == (repo / ".claude" / "skills").resolve()
    assert drift.canonical_hash != drift.mirror_hash
    assert SYNC_COMMAND in drift.message()


def test_script_in_canonical_tree_is_never_stale(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".claude" / "skills" / "shared" / "lib.py").write_text("X = 2\n")
    assert stale_mirror(repo / "skills" / "alpha" / "scripts" / "run.py") is None


def test_consumer_install_without_canonical_source_is_not_checked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "skills" / "install.sh").unlink()
    (repo / "skills" / "shared" / "lib.py").write_text("X = 2\n")
    assert stale_mirror(_script(repo)) is None


def test_unreadable_manifest_is_not_reported(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "skills" / "install-manifest.json").write_text("not json")
    assert stale_mirror(_script(repo)) is None


def test_malformed_manifest_shape_is_not_reported(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for bad in ({"skills": [], "shared_libraries": []}, {"skills": {"alpha": None}}):
        (repo / "skills" / "install-manifest.json").write_text(json.dumps(bad))
        assert stale_mirror(_script(repo)) is None


def test_runner_warning_never_aborts(capsys, monkeypatch) -> None:
    sys.path.insert(0, str(SKILLS_ROOT / "autopilot" / "scripts"))
    import runner  # type: ignore[import-not-found]

    def boom(_path):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(runner, "stale_mirror", boom)
    runner._warn_if_stale_mirror()
    assert capsys.readouterr().err == ""


def test_runner_warns_from_a_stale_mirror(tmp_path: Path, capsys, monkeypatch) -> None:
    sys.path.insert(0, str(SKILLS_ROOT / "autopilot" / "scripts"))
    import runner  # type: ignore[import-not-found]

    repo = _repo(tmp_path)
    (repo / "skills" / "shared" / "lib.py").write_text("X = 2\n")
    monkeypatch.setattr(runner, "__file__", str(_script(repo)))

    runner._warn_if_stale_mirror()

    err = capsys.readouterr().err
    assert "autopilot: WARNING: runtime skill mirror" in err
    assert SYNC_COMMAND in err
