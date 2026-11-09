"""Tests for generate_bindings.py and the bindings it checks in.

Spec: coordination-bridge "Contract-Generated Bindings" (design D2, D3).
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
GENERATOR = SCRIPTS_DIR / "generate_bindings.py"
GENERATED_DIR = SCRIPTS_DIR / "_generated"
REPO_ROOT = SCRIPTS_DIR.parents[2]
CONTRACT_REL = "openspec/contracts/agent-coordinator/openapi/features.yaml"
CONTRACT = REPO_ROOT / CONTRACT_REL
GENERATED_FILES = ("__init__.py", "features_models.py", "features_operations.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _generate_into(out_dir: Path) -> None:
    result = _run("--output-dir", str(out_dir))
    assert result.returncode == 0, result.stderr


def _contract_operations() -> dict[str, tuple[str, str, dict]]:
    doc = yaml.safe_load(CONTRACT.read_text())
    ops = {}
    for path, item in doc["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and "operationId" in op:
                ops[op["operationId"]] = (method.upper(), path, op)
    return ops


def _ref_name(schema: dict) -> str:
    return schema["$ref"].rsplit("/", 1)[-1]


def _load_operations(path: Path) -> dict:
    namespace: dict = {}
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    return namespace["OPERATIONS"]


def test_generator_writes_models_for_every_body_and_success_response(tmp_path: Path) -> None:
    _generate_into(tmp_path)
    models_src = (tmp_path / "features_models.py").read_text()
    typed_dicts = set(re.findall(r"^class (\w+)\(TypedDict\):", models_src, re.MULTILINE))

    expected = set()
    for _method, _path, op in _contract_operations().values():
        body = op.get("requestBody", {}).get("content", {}).get("application/json")
        if body:
            expected.add(_ref_name(body["schema"]))
        for code, response in op["responses"].items():
            if str(code).startswith("2"):
                expected.add(_ref_name(response["content"]["application/json"]["schema"]))

    assert expected, "contract declared no request or success-response schemas"
    assert expected <= typed_dicts


def test_generator_writes_operations_table_matching_contract(tmp_path: Path) -> None:
    _generate_into(tmp_path)
    operations = _load_operations(tmp_path / "features_operations.py")
    contract_ops = _contract_operations()

    assert set(operations) == set(contract_ops)
    for op_id, (method, path, op) in contract_ops.items():
        entry = operations[op_id]
        assert entry.method == method
        assert entry.path == path
        assert entry.path_params == tuple(re.findall(r"{(\w+)}", path))
        assert entry.requires_api_key is True
        body = op.get("requestBody", {}).get("content", {}).get("application/json")
        assert entry.request_model == (_ref_name(body["schema"]) if body else None)
        assert entry.response_model == _ref_name(
            op["responses"]["200"]["content"]["application/json"]["schema"]
        )

    assert operations["getFeature"].path_params == ("feature_id",)
    assert operations["listActiveFeatures"].request_model is None


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _generate_into(first)
    _generate_into(second)
    for name in GENERATED_FILES:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_checked_in_bindings_are_current() -> None:
    result = _run("--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_names_stale_file_and_regeneration_command(tmp_path: Path) -> None:
    contract_copy = tmp_path / CONTRACT_REL
    contract_copy.parent.mkdir(parents=True)
    doc = yaml.safe_load(CONTRACT.read_text())
    doc["components"]["schemas"]["ConflictReport"]["properties"]["added_field"] = {"type": "string"}
    contract_copy.write_text(yaml.safe_dump(doc, sort_keys=False))
    out_dir = tmp_path / "_generated"
    shutil.copytree(GENERATED_DIR, out_dir, ignore=shutil.ignore_patterns("__pycache__"))

    result = _run("--check", "--repo-root", str(tmp_path), "--output-dir", str(out_dir))

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "features_models.py" in output
    assert "features_operations.py" not in output
    assert "generate_bindings.py" in output
    assert "python" in output


def test_check_reports_missing_file(tmp_path: Path) -> None:
    result = _run("--check", "--output-dir", str(tmp_path / "empty"))
    assert result.returncode != 0
    assert "features_operations.py" in result.stdout + result.stderr


def test_generated_files_have_header_and_no_timestamps_or_absolute_paths() -> None:
    for name in GENERATED_FILES:
        text = (GENERATED_DIR / name).read_text()
        assert text.startswith(
            f"# GENERATED by generate_bindings.py from {CONTRACT_REL} — do not edit\n"
        ), name
        assert str(REPO_ROOT) not in text, name
        assert not re.search(r"/home/|/Users/|/tmp/|[A-Z]:\\\\", text), name
        assert not re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", text), name
        assert "timestamp" not in text.lower(), name


def test_operations_module_is_python39_compatible() -> None:
    """The operations table is imported at runtime by bare python3 (D3)."""
    source = (GENERATED_DIR / "features_operations.py").read_text()
    ast.parse(source, feature_version=(3, 9))
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported <= {"__future__", "typing"}


def test_models_module_imports_stdlib_only() -> None:
    tree = ast.parse((GENERATED_DIR / "features_models.py").read_text())
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}


# --------------------------------------------------------------------------- #
# Spec "Bindings stay standard-library only" (task 5.2)
# --------------------------------------------------------------------------- #

_IMPORT_PROBE = """
import sys
sys.path.insert(0, {scripts!r})
before = set(sys.modules)
import coordination_bridge
allowed_prefixes = ("coordination_bridge", "_generated")
foreign = sorted(
    name for name in set(sys.modules) - before
    if name.split(".")[0] not in sys.stdlib_module_names
    and not name.startswith(allowed_prefixes)
)
print("FOREIGN=" + ",".join(foreign))
print("MODELS_LOADED=" + str("_generated.features_models" in sys.modules))
"""


def test_bridge_import_loads_only_stdlib_and_bridge_modules() -> None:
    interpreter = shutil.which("python3") or sys.executable
    result = subprocess.run(
        [interpreter, "-I", "-c", _IMPORT_PROBE.format(scripts=str(SCRIPTS_DIR))],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "FOREIGN=\n" in result.stdout, result.stdout
    assert "MODELS_LOADED=False" in result.stdout, result.stdout


def _is_type_checking_test(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING") or (
        isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"
    )


def test_bridge_imports_models_only_under_type_checking() -> None:
    tree = ast.parse((SCRIPTS_DIR / "coordination_bridge.py").read_text())
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            for child in node.body:
                for inner in ast.walk(child):
                    guarded.add(id(inner))

    model_imports = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.ImportFrom) and node.module and "features_models" in node.module)
        or (
            isinstance(node, ast.Import)
            and any("features_models" in alias.name for alias in node.names)
        )
    ]
    assert model_imports, "bridge should type its helpers with the generated models"
    for node in model_imports:
        assert id(node) in guarded, f"features_models imported at runtime (line {node.lineno})"
