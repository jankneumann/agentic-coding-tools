"""The payload scanner must exclude exactly what install.sh excludes.

``validate_install_manifest`` checks the payload consumers actually receive. If
it scans a directory ``mirror_tree`` skips, it reports failures about files that
never ship; if it skips one ``mirror_tree`` copies, unshippable content reaches
consumers unchecked. Either way the two lists must agree.

They did not on 2026-08-24. ``skills/refresh-architecture/node_modules`` (51 MB,
gitignored, created by the skill's own on-demand ``npm install --no-save``) was
scanned but should never have been — its vendored upstream READMEs carry
repo-relative links like ``/BENCHMARKS.md`` that cannot resolve inside an
installed payload. Every ``install.sh`` run failed from the moment that
directory appeared. The failure also masked a second bug: because
``mirror_tree`` excluded only ``tests/`` and ``__pycache__/``, a successful run
would have copied all 51 MB into every runtime skill directory.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_DIR = REPO_ROOT / "skills" / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from validate_install_manifest import (  # noqa: E402
    _EXCLUDED_PAYLOAD_DIRS,
    _iter_payload_files,
)

INSTALL_SH = REPO_ROOT / "skills" / "install.sh"

#: `mirror_tree "$src" "$dest" --delete --exclude 'a/' --exclude 'b/'`
_MIRROR_CALL = re.compile(
    r"mirror_tree\s+\"\$(?:skill_path|lib_src)\".*?(?=\n\s*echo)", re.DOTALL
)
_EXCLUDE_FLAG = re.compile(r"--exclude\s+'([^']+)'")


def _installer_excludes() -> list[frozenset[str]]:
    """Exclusion sets from every skill/library mirror_tree call in install.sh."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    calls = _MIRROR_CALL.findall(text)
    assert calls, "no skill/library mirror_tree calls found — regex is stale"
    return [
        frozenset(e.rstrip("/") for e in _EXCLUDE_FLAG.findall(call))
        for call in calls
    ]


def test_installer_has_the_expected_mirror_calls():
    """Guards the regex above: both payload call sites must be found."""
    assert len(_installer_excludes()) == 2


@pytest.mark.parametrize("excludes", _installer_excludes())
def test_scanner_excludes_match_the_installer(excludes):
    """Neither list may carry a directory the other omits."""
    assert excludes == set(_EXCLUDED_PAYLOAD_DIRS), (
        "install.sh mirror_tree excludes and _EXCLUDED_PAYLOAD_DIRS disagree; "
        "the scanner would validate a payload the installer does not ship"
    )


def test_node_modules_is_excluded():
    """Pins the specific directory that broke install.sh on 2026-08-24."""
    assert "node_modules" in _EXCLUDED_PAYLOAD_DIRS


def test_scanner_skips_nested_excluded_directories(tmp_path):
    """Exclusion applies at any depth, not just the skill's top level."""
    skills_root = tmp_path / "skills"
    skill = skills_root / "demo"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# demo\n")
    (skill / "scripts" / "run.py").write_text("x = 1\n")

    buried = skill / "scripts" / "node_modules" / "pkg"
    buried.mkdir(parents=True)
    (buried / "README.md").write_text("[up](/escapes.md)\n")

    tests_dir = skill / "scripts" / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("x = 1\n")

    found = {p.name for p in _iter_payload_files(skills_root, ["demo"], [])}
    assert "SKILL.md" in found and "run.py" in found
    assert "README.md" not in found, "nested node_modules was scanned"
    assert "test_x.py" not in found, "nested tests dir was scanned"


def test_real_repo_scan_skips_vendored_node_modules():
    """End-to-end: the actual refresh-architecture payload excludes node_modules."""
    vendored = REPO_ROOT / "skills" / "refresh-architecture" / "node_modules"
    if not vendored.is_dir():
        pytest.skip("node_modules not present in this checkout")
    scanned = list(
        _iter_payload_files(REPO_ROOT / "skills", ["refresh-architecture"], [])
    )
    assert scanned, "expected the skill's own files to be scanned"
    assert not [p for p in scanned if "node_modules" in p.parts]
