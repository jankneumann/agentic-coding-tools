from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_VALIDATOR = _SKILLS_ROOT / "shared" / "validate_install_manifest.py"
_SPEC = importlib.util.spec_from_file_location("validate_install_manifest", _VALIDATOR)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _manifest(skills: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "shared_libraries": ["shared", "references"],
        "runtime_globs": ["*/SKILL.md", "*/scripts/**"],
        "installed_assets": [
            {"source_glob": "*/install_assets/openspec/**", "destination": "openspec/"}
        ],
        "cross_skill_dependencies": {},
        "skills": skills,
        "smoke_entrypoints": [],
    }


def _payload(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    for name in ("shared", "references"):
        (root / name).mkdir(parents=True)
    (root / "example").mkdir()
    (root / "example" / "SKILL.md").write_text("---\nname: example\n---\n")
    asset = root / "example" / "install_assets" / "openspec" / "schema.json"
    asset.parent.mkdir(parents=True)
    asset.write_text("{}\n")
    return root


def test_manifest_requires_every_discovered_skill_classification(tmp_path: Path) -> None:
    root = _payload(tmp_path)
    errors = _MODULE.validate_manifest(root, _manifest({}), scan=False)
    assert errors == ["skill has no distribution classification: example"]


def test_manifest_rejects_repo_escape_and_canonical_command(tmp_path: Path) -> None:
    root = _payload(tmp_path)
    (root / "example" / "SKILL.md").write_text(
        "[outside](../../docs/private.md)\n"
        "```bash\npython3 skills/example/scripts/run.py\n```\n"
    )
    errors = _MODULE.validate_manifest(
        root, _manifest({"example": {"distribution": "portable"}})
    )
    assert any("escapes installed payload" in error for error in errors)
    assert any("canonical skills runtime path" in error for error in errors)


def test_repository_manifest_catalog_is_complete() -> None:
    manifest = json.loads((_SKILLS_ROOT / "install-manifest.json").read_text())
    errors = _MODULE.validate_manifest(_SKILLS_ROOT, manifest, scan=False)
    assert errors == []


def test_explicit_source_contribution_command_is_not_consumer_runtime(tmp_path: Path) -> None:
    root = _payload(tmp_path)
    (root / "example" / "SKILL.md").write_text(
        "Source test (**source-contribution-only**): `skills/.venv/bin/python -m pytest`\n"
    )
    errors = _MODULE.validate_manifest(
        root, _manifest({"example": {"distribution": "portable"}})
    )
    assert errors == []


def test_python_path_to_canonical_skill_scripts_is_rejected(tmp_path: Path) -> None:
    root = _payload(tmp_path)
    (root / "example" / "SKILL.md").write_text(
        "```python\nimport sys\nsys.path.insert(0, \"skills/session-log/scripts\")\n```\n"
    )
    errors = _MODULE.validate_manifest(
        root, _manifest({"example": {"distribution": "portable"}})
    )
    assert any("canonical skills runtime path" in error for error in errors)


def test_variable_prefixed_venv_and_source_installer_are_rejected(tmp_path: Path) -> None:
    root = _payload(tmp_path)
    (root / "example" / "SKILL.md").write_text(
        "```bash\n$REPO_ROOT/skills/.venv/bin/python check.py\n"
        "bash skills/install.sh\npython3 skills/shared/active_agents.py\n```\n"
    )
    errors = _MODULE.validate_manifest(
        root, _manifest({"example": {"distribution": "portable"}})
    )
    assert len([error for error in errors if "canonical skills runtime path" in error]) == 3
