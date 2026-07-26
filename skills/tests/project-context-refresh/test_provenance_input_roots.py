"""Architecture provenance records the roots it actually analyzed (ri-10 follow-up).

The gate's first real CI run went red with ``architecture: unverifiable``, and the
committed provenance explained why:

    "input_roots": ["database/migrations", "src", "web"]

None of those three paths exist in this repository. They are the *fallback*
defaults in ``default_input_roots()``, reached because ``run_architecture.py``
built the ``--python-src-dir``/``--ts-src-dir``/``--migrations-dir`` overrides
into a **child** environment dict and never touched ``os.environ`` — while
``build_provenance`` read the ambient environment.

That is a fail-open defect, not a cosmetic one. ``compute_input_fingerprint``
hashes the files discovered under the recorded roots; over roots that do not
exist it hashes a constant. Every source edit in the repository would have left
the fingerprint untouched, so the input-change arm of the freshness check could
never fire — the exact "green signal for work never done" this change exists to
prevent.

Two invariants are pinned here:

1. ``default_input_roots`` honours an explicitly supplied environment, so the
   caller that owns the child env can hand over the real values.
2. Every root recorded in the committed provenance exists on disk. A fingerprint
   over a missing root is inert, so a missing root is a broken gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARCH_SCRIPTS = _REPO_ROOT / "skills" / "refresh-architecture" / "scripts"
if str(_ARCH_SCRIPTS) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(_ARCH_SCRIPTS))

from arch_utils import provenance as prov  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. Explicit environment wins over the ambient one
# --------------------------------------------------------------------------- #
def test_default_input_roots_honours_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A supplied mapping is authoritative; os.environ must not leak in."""
    # Ambient environment deliberately disagrees with the child environment.
    monkeypatch.setenv("PYTHON_SRC_DIR", "ambient-python")
    monkeypatch.setenv("TS_SRC_DIR", "ambient-ts")
    monkeypatch.setenv("MIGRATIONS_DIR", "ambient-migrations")

    child_env = {
        "PYTHON_SRC_DIR": "agent-coordinator/src",
        "TS_SRC_DIR": "apps",
        "MIGRATIONS_DIR": "agent-coordinator/database/migrations",
    }

    assert prov.default_input_roots(child_env) == [
        "agent-coordinator/src",
        "apps",
        "agent-coordinator/database/migrations",
    ]


def test_default_input_roots_still_reads_os_environ_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting the argument preserves the pre-existing behaviour (Rule 4)."""
    monkeypatch.setenv("PYTHON_SRC_DIR", "ambient-python")
    monkeypatch.delenv("TS_SRC_DIR", raising=False)
    monkeypatch.delenv("MIGRATIONS_DIR", raising=False)

    roots = prov.default_input_roots()

    assert roots[0] == "ambient-python"
    assert "web" in roots  # untouched fallback
    assert "database/migrations" in roots


# --------------------------------------------------------------------------- #
# 2. The call site actually hands the child env over
# --------------------------------------------------------------------------- #
def test_run_architecture_records_the_analyzed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--staged writes provenance whose input_roots match the CLI overrides.

    The analyzers are stubbed out: this test pins the *wiring* between
    ``build_env`` and ``build_provenance``, which is where the defect lived.
    """
    if str(_ARCH_SCRIPTS) not in sys.path:  # pragma: no cover - import wiring
        sys.path.insert(0, str(_ARCH_SCRIPTS))
    import run_architecture

    captured: dict[str, list[str]] = {}
    real_build = prov.build_provenance

    def _spy(repo_root, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["roots"] = list(kwargs.get("roots") or [])
        return real_build(repo_root, *args, **kwargs)

    # ``run_architecture`` imports ``provenance`` inside the staged function, so
    # the patch target is the module object, not a run_architecture attribute.
    monkeypatch.setattr(prov, "build_provenance", _spy)

    # Neutralise the parts that need a real analysis toolchain.
    monkeypatch.setattr(run_architecture, "_run_pipeline", lambda *a, **k: 0)
    monkeypatch.setattr(run_architecture, "_required_outputs_present", lambda *a, **k: True)
    monkeypatch.setattr(run_architecture, "_promote", lambda *a, **k: None)
    monkeypatch.setattr(prov, "analyzed_revision", lambda *a, **k: "0" * 40)
    monkeypatch.setattr(prov, "deterministic_epoch", lambda *a, **k: 0)
    monkeypatch.setattr(prov, "worktree_dirty", lambda *a, **k: False)

    for rel in ("pkg/src", "frontend", "db/migrations"):
        (tmp_path / rel).mkdir(parents=True)

    # _promote is stubbed, so stand in for its output: provenance refuses to
    # record an empty artifact set.
    arch_dir = tmp_path / prov.ARCH_DIR_DEFAULT
    arch_dir.mkdir(parents=True)
    for name in ("architecture.graph.json", "architecture.summary.json"):
        (arch_dir / name).write_text("{}\n", encoding="utf-8")

    run_architecture.main(
        [
            "--target-dir",
            str(tmp_path),
            "--python-src-dir",
            "pkg/src",
            "--ts-src-dir",
            "frontend",
            "--migrations-dir",
            "db/migrations",
            "--staged",
        ]
    )

    assert captured["roots"] == ["pkg/src", "frontend", "db/migrations"], (
        "build_provenance was not given the roots the analyzers were pointed at"
    )


# --------------------------------------------------------------------------- #
# 3. Repository invariant: no recorded root may be missing
# --------------------------------------------------------------------------- #
def test_committed_provenance_roots_all_exist() -> None:
    """A fingerprint over a nonexistent root is inert, so the gate is blind."""
    prov_path = (
        _REPO_ROOT / "docs" / "architecture-analysis" / "architecture.provenance.json"
    )
    if not prov_path.is_file():
        pytest.skip("no committed architecture provenance in this checkout")

    doc = json.loads(prov_path.read_text(encoding="utf-8"))
    roots = doc.get("input_roots", [])

    assert roots, "provenance records no input roots at all"

    missing = [r for r in roots if not (_REPO_ROOT / r).exists()]
    assert not missing, (
        f"architecture.provenance.json records input roots that do not exist: {missing}. "
        "compute_input_fingerprint hashes a constant over a missing root, so the "
        "input-change arm of the freshness check can never fire. Regenerate with "
        "`make architecture-refresh`."
    )
