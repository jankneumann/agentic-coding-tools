"""Structural guard for the complete local vendor-process boundary."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS_ROOT = REPO_ROOT / "skills"
if str(SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILLS_ROOT))

from shared.vendor_process_surfaces import (  # noqa: E402
    PRODUCTION_VENDOR_SURFACES,
    VendorProcessInvocation,
    run_vendor_process,
)


PROCESS_APIS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "os.system",
    "os.popen",
}
PRODUCTION_PROCESS_ROOTS = (
    "skills/autopilot/scripts",
    "skills/parallel-infrastructure/scripts",
    "skills/quick-task/scripts",
    "skills/shared",
    "agent-coordinator/evaluation/backends",
)
PROCESS_SINK_CLASSIFICATIONS = {
    ("skills/shared/local_process_backend.py", "_run_process"): "shared_vendor_backend",
    ("skills/shared/checkout_policy.py", "_git_toplevel"): "control_plane_git",
    ("skills/shared/sandbox_activation.py", "_git_path"): "control_plane_git",
    (
        "skills/shared/verify_sandbox_runtime_evidence.py",
        "_run_gh",
    ): "validation_probe",
    (
        "skills/parallel-infrastructure/scripts/review_dispatcher.py",
        "_main_repo_from_cwd",
    ): "control_plane_git",
    (
        "skills/parallel-infrastructure/scripts/review_dispatcher.py",
        "workspace_content_digest",
    ): "control_plane_git",
    (
        "skills/parallel-infrastructure/scripts/review_dispatcher.py",
        "create_review_snapshot",
    ): "control_plane_git",
    (
        "skills/parallel-infrastructure/scripts/review_dispatcher.py",
        "destroy_review_snapshot",
    ): "control_plane_git",
    (
        "skills/parallel-infrastructure/scripts/review_dispatcher.py",
        "ReviewOrchestrator.from_coordinator",
    ): "control_plane_probe",
    (
        "skills/parallel-infrastructure/scripts/review_packet.py",
        "_git_diff",
    ): "control_plane_git",
    (
        "skills/parallel-infrastructure/scripts/ocr_adapter.py",
        "run_ocr",
    ): "vendor_descendant_adapter",
    ("skills/autopilot/scripts/autopilot.py", "_default_apply_outcome_runner"): "control_plane_git",
    ("skills/autopilot/scripts/convergence_loop.py", "_git"): "control_plane_git",
    ("skills/autopilot/scripts/phase_outcome_shadow.py", "git_diff_stat"): "control_plane_git",
}


@dataclass(frozen=True)
class ProcessCall:
    api: str
    owner: str
    lineno: int


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    current = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _owner(stack: list[ast.AST]) -> str:
    names = [
        node.name
        for node in stack
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return ".".join(names)


def _process_calls(tree: ast.AST) -> list[ProcessCall]:
    module_aliases: dict[str, str] = {}
    function_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"subprocess", "asyncio", "os"}:
                    module_aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in {"subprocess", "asyncio", "os"}:
            for alias in node.names:
                canonical = f"{node.module}.{alias.name}"
                if canonical in PROCESS_APIS:
                    function_aliases[alias.asname or alias.name] = canonical

    calls: list[ProcessCall] = []
    stack: list[ast.AST] = []

    class Visitor(ast.NodeVisitor):
        def _visit_owner(self, node: ast.AST) -> None:
            stack.append(node)
            self.generic_visit(node)
            stack.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self._visit_owner(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._visit_owner(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._visit_owner(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            raw_name = _call_name(node)
            if raw_name in function_aliases:
                name = function_aliases[raw_name]
            else:
                head, separator, tail = raw_name.partition(".")
                name = f"{module_aliases.get(head, head)}{separator}{tail}"
            if name in PROCESS_APIS:
                calls.append(ProcessCall(api=name, owner=_owner(stack), lineno=node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return calls


def _production_python_files() -> list[Path]:
    paths: set[Path] = set()
    for relative in PRODUCTION_PROCESS_ROOTS:
        root = REPO_ROOT / relative
        candidates = [root] if root.is_file() else root.rglob("*.py")
        paths.update(
            path
            for path in candidates
            if "tests" not in path.parts
            and "__pycache__" not in path.parts
            and not path.name.startswith("test_")
        )
    return sorted(paths)


def test_process_call_discovery_resolves_imported_aliases() -> None:
    tree = ast.parse(
        """
import subprocess as sp
from asyncio import create_subprocess_exec as spawn

def first():
    sp.run(["vendor"])

async def second():
    await spawn("vendor")
"""
    )

    assert [
        (call.owner, call.api)
        for call in _process_calls(tree)
    ] == [
        ("first", "subprocess.run"),
        ("second", "asyncio.create_subprocess_exec"),
    ]


def test_registered_production_surfaces_have_no_vendor_process_bypass() -> None:
    violations: list[str] = []
    required = {
        "review",
        "fact_check",
        "autopilot_provider",
        "phase_fixer",
        "quick_task",
        "evaluation_claude_code",
        "evaluation_codex",
        "evaluation_antigravity",
        "evaluation_grok",
        "evaluation_pi",
        "ocr_descendant",
    }
    assert required <= set(PRODUCTION_VENDOR_SURFACES)

    registered_paths = {surface.path for surface in PRODUCTION_VENDOR_SURFACES.values()}
    for relative in registered_paths:
        assert (REPO_ROOT / relative).is_file(), f"registered production surface is missing: {relative}"

    discovered: set[tuple[str, str]] = set()
    for path in _production_python_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in _process_calls(tree):
            key = (relative, call.owner)
            discovered.add(key)
            if key not in PROCESS_SINK_CLASSIFICATIONS:
                violations.append(f"{relative}:{call.lineno}:{call.owner}:{call.api}")

    assert violations == []
    stale = set(PROCESS_SINK_CLASSIFICATIONS) - discovered
    assert stale == set(), f"stale process-sink classifications: {sorted(stale)}"


def test_vendor_surface_calls_shared_backend_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_backend(request):
        calls.append(request)
        return type(
            "Result",
            (),
            {
                "status": "completed",
                "returncode": 0,
                "stdout": "ok",
                "stderr": "",
                "timed_out": False,
                "sandbox_applied": False,
                "degradation_reason": None,
                "cleanup_status": "succeeded",
                "cleanup_residual_paths": (),
            },
        )()

    monkeypatch.setattr("shared.vendor_process_surfaces.run_local_process", fake_backend)
    result = run_vendor_process(
        VendorProcessInvocation(
            surface="fact_check",
            argv=(sys.executable, "-c", "pass"),
            cwd=tmp_path,
            env={"TOKEN": "value"},
            timeout_seconds=5,
            isolation="worktree",
            stdin_text="prompt",
        )
    )

    assert result.stdout == "ok"
    assert len(calls) == 1
    assert calls[0].stdin_text == "prompt"
