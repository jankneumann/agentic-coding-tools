"""Unit tests for simplify/scripts/check_test_contract.py."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "simplify-implementation" / "scripts"


def _load():
    import sys

    path = SCRIPTS / "check_test_contract.py"
    name = "simplify_implementation_check_test_contract"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text(
        "from src.app import f\n\ndef test_f():\n    assert f() == 1\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

def test_prod_only_change_is_clean(git_repo: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    (git_repo / "src" / "app.py").write_text(
        "def f():\n    return 1  # same behavior\n", encoding="utf-8"
    )
    _commit(git_repo, "refactor")
    assert mod.main(["--base", base, "--repo", str(git_repo)]) == 0


def test_assertion_body_change_is_broken(git_repo: Path):
    mod = _load()
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True
    ).strip()
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import f\n\ndef test_f():\n    assert f() == 2\n",
        encoding="utf-8",
    )
    _commit(git_repo, "bad expectation edit")
    assert mod.main(["--base", base, "--repo", str(git_repo)]) == 2


def test_scan_unified_diff_detects_expect():
    mod = _load()
    diff = """\
diff --git a/src/foo.test.ts b/src/foo.test.ts
--- a/src/foo.test.ts
+++ b/src/foo.test.ts
@@ -1 +1 @@
-expect(value).toBe(1)
+expect(value).toBe(2)
"""
    findings, files = mod.scan_unified_diff(diff)
    assert "src/foo.test.ts" in files
    assert findings
    assert any("expect" in f.line for f in findings)


def test_deleted_test_file_assert_lines_are_flagged():
    """+++ /dev/null must still attribute -assert lines to the deleted test path."""
    mod = _load()
    diff = """\
diff --git a/tests/test_gone.py b/tests/test_gone.py
deleted file mode 100644
--- a/tests/test_gone.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def test_x():
-    assert 1 == 1
"""
    findings, files = mod.scan_unified_diff(diff)
    assert "tests/test_gone.py" in files
    assert findings
    assert any("assert" in f.line for f in findings)


def test_go_test_path_and_t_errorf():
    mod = _load()
    assert mod.is_test_path("pkg/foo_test.go")
    diff = """\
diff --git a/pkg/foo_test.go b/pkg/foo_test.go
--- a/pkg/foo_test.go
+++ b/pkg/foo_test.go
@@ -1 +1 @@
-    t.Errorf("got %v", got)
+    t.Errorf("got %v want %v", got, want)
"""
    findings, files = mod.scan_unified_diff(diff)
    assert "pkg/foo_test.go" in files
    assert findings


def test_rust_assert_eq_and_matcher_continuation():
    mod = _load()
    assert mod.is_test_path("src/lib_test.rs") or mod.is_test_path("tests/foo_test.rs")
    diff = """\
diff --git a/tests/foo_test.rs b/tests/foo_test.rs
--- a/tests/foo_test.rs
+++ b/tests/foo_test.rs
@@ -1,2 +1,2 @@
-    assert_eq!(x, 1);
+    assert_eq!(x, 2);
-    .toBe(1)
+    .toBe(2)
"""
    findings, _ = mod.scan_unified_diff(diff)
    assert any("assert_eq" in f.line for f in findings)


def test_new_characterization_test_without_mutating_assert_style():
    """Adding a brand-new assert line is still a +assert line; contract treats
    any assertion-line add/remove as a finding so simplify-range should exclude
    characterization commits (baseline after pin).

    Document expected strictness: characterization commit should be *before*
    --base, so this checker only sees simplify commits.
    """
    mod = _load()
    # Pure addition of a new test with assert still matches ASSERT_LINE_RE on '+'
    diff = """\
diff --git a/tests/test_new.py b/tests/test_new.py
--- /dev/null
+++ b/tests/test_new.py
@@ -0,0 +1,2 @@
+def test_new():
+    assert True
"""
    findings, files = mod.scan_unified_diff(diff)
    assert files
    # Strict: +assert lines count — baseline must be set after characterization
    assert findings


def test_mock_assertions_are_contract_lines(git_repo: Path):
    """A weakened mock assertion is an expectation edit like any other."""
    mod = _load()
    (git_repo / "tests" / "test_app.py").write_text(
        "from unittest.mock import Mock\n\n"
        "def test_f_calls_backend():\n"
        "    m = Mock()\n"
        "    m.run(1)\n"
        "    m.run.assert_called_once_with(1)\n",
        encoding="utf-8",
    )
    _commit(git_repo, "test: pin backend call")
    base = _sha(git_repo)
    (git_repo / "tests" / "test_app.py").write_text(
        "from unittest.mock import Mock\n\n"
        "def test_f_calls_backend():\n"
        "    m = Mock()\n"
        "    m.run(1)\n"
        "    m.run.assert_called()\n",
        encoding="utf-8",
    )
    _commit(git_repo, "refactor: weaken the mock assertion")
    result = mod.evaluate(git_repo, base, "HEAD")
    assert result.clean is False, "mock assertion edits must break the contract"


def test_non_assertion_lines_are_not_contract_lines(git_repo: Path):
    """Ordinary test setup must stay editable during a simplify."""
    mod = _load()
    base = _sha(git_repo)
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import f\n\n"
        "def test_f():\n    value = f()\n    assert f() == 1\n",
        encoding="utf-8",
    )
    _commit(git_repo, "refactor: rename a local in the test")
    result = mod.evaluate(git_repo, base, "HEAD")
    assert result.clean is True, result.findings
