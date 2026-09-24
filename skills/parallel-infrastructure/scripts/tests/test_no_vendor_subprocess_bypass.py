"""Structural guard for the complete local vendor-process boundary."""

from __future__ import annotations

import ast
import sys
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
EXEMPTIONS = {
    ("skills/shared/local_process_backend.py", "_run_process"),
    ("skills/parallel-infrastructure/scripts/review_dispatcher.py", "_main_repo_from_cwd"),
    ("skills/parallel-infrastructure/scripts/review_dispatcher.py", "workspace_content_digest"),
    ("skills/parallel-infrastructure/scripts/review_dispatcher.py", "create_review_snapshot"),
    ("skills/parallel-infrastructure/scripts/review_dispatcher.py", "destroy_review_snapshot"),
    ("skills/parallel-infrastructure/scripts/review_dispatcher.py", "ReviewOrchestrator.from_coordinator"),
    ("skills/parallel-infrastructure/scripts/ocr_adapter.py", "run_ocr"),
}


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

    for surface in PRODUCTION_VENDOR_SURFACES.values():
        relative = surface.path
        path = REPO_ROOT / relative
        assert path.is_file(), f"registered production surface is missing: {relative}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        stack: list[ast.AST] = []

        class Visitor(ast.NodeVisitor):
            def generic_visit(self, node: ast.AST) -> None:
                stack.append(node)
                super().generic_visit(node)
                stack.pop()

            def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
                name = _call_name(node)
                owner = _owner(stack)
                if name in PROCESS_APIS and (relative, owner) not in EXEMPTIONS:
                    violations.append(f"{relative}:{node.lineno}:{owner}:{name}")
                self.generic_visit(node)

        Visitor().visit(tree)

    assert violations == []


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
