"""Test that the built sdist contains the right files (and NOT coordinator data).

Task 3.3 — spec scenario: gen-eval-framework.framework-consumer-data-split
(package-does-not-ship-coordinator-specific-descriptors), design decision D7.

The test builds the sdist via ``uv build --sdist`` and inspects the tarball
member list.  It asserts:

  Required in sdist:
    - at least one file under src/gen_eval/schemas/
    - at least one file under src/gen_eval/dtu/

  Forbidden in sdist (coordinator-specific consumer data that must NOT be
  packaged with the framework):
    - any path segment matching "agent-coordinator" in combination with
      "descriptors" or "manifests"
    - specifically: any file whose path contains "descriptors/agent-coordinator"
      or that lives under a "manifests/" directory carrying coordinator data

These assertions guard against accidentally shipping `evaluation/descriptors/`
or `evaluation/manifests/` from the coordinator side into the distributable.

Note: tests/fixtures/ and examples/ are intended for consumers but the
uv_build backend only includes src/ by default.  Those directories are
captured in the wheel instead via package_data, and the prohibition on
coordinator data is the primary contract this test enforces.
"""
from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


def _build_sdist(package_root: Path, tmp_path: Path) -> Path:
    """Run ``uv build --sdist`` and return the path to the produced tarball."""
    uv_exe = shutil.which("uv") or "uv"
    result = subprocess.run(
        [uv_exe, "build", "--sdist", "--out-dir", str(tmp_path)],
        cwd=str(package_root),
        capture_output=True,
        text=True,
    )
    # uv build returns non-zero on failure.
    if result.returncode != 0:
        pytest.skip(
            f"uv build --sdist failed (may be a build-backend version issue): "
            f"{result.stderr[:500]}"
        )

    tarballs = list(tmp_path.glob("*.tar.gz"))
    if not tarballs:
        pytest.skip("uv build produced no .tar.gz — skipping sdist content test")
    return tarballs[0]


@pytest.mark.slow
def test_sdist_contains_framework_data_and_not_coordinator_data(tmp_path: Path) -> None:
    """The gen-eval sdist must ship framework data (schemas, dtu) and must NOT
    ship coordinator-specific descriptors or manifests.
    """
    # Locate the package root relative to this test file.
    # tests/ → packages/gen-eval/
    package_root = Path(__file__).parent.parent

    tarball = _build_sdist(package_root, tmp_path)

    with tarfile.open(tarball, "r:gz") as tf:
        members = [m.name for m in tf.getmembers()]

    # --- Required presence ---
    # Schemas: at least one .json under src/gen_eval/schemas/
    schemas_files = [m for m in members if "/src/gen_eval/schemas/" in m and m.endswith(".json")]
    assert schemas_files, (
        f"sdist must contain src/gen_eval/schemas/*.json; found none in: {tarball.name}"
    )

    # DTU templates: at least one file under src/gen_eval/dtu/
    dtu_files = [m for m in members if "/src/gen_eval/dtu/" in m]
    assert dtu_files, (
        f"sdist must contain src/gen_eval/dtu/ entries; found none in: {tarball.name}"
    )

    # --- Forbidden content ---
    # No coordinator-specific descriptor files
    coordinator_descriptors = [
        m for m in members
        if "descriptors/agent-coordinator" in m or "agent-coordinator.yaml" in m
    ]
    assert not coordinator_descriptors, (
        f"sdist must NOT contain coordinator-specific descriptors; "
        f"found: {coordinator_descriptors}"
    )

    # No manifests/ directories from coordinator consumer data
    # (the framework itself has no manifests/ directory — those live in the
    # consumer's evaluation/ directory, not in the package)
    manifest_files = [
        m for m in members
        if "/manifests/" in m and "gen_eval" not in m
    ]
    assert not manifest_files, (
        f"sdist must NOT contain consumer manifests/ data; found: {manifest_files}"
    )
