"""The observation script reports credential metadata and never content.

Every test runs against a temporary home directory, so no test touches a real
credential path (design D6).
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "skills" / "vendor-status" / "scripts" / "observe_vendor_auth.py"
_TABLE = _REPO / "docs" / "guides" / "vendor-auth-audit.yaml"

_spec = importlib.util.spec_from_file_location("observe_vendor_auth", _SCRIPT)
assert _spec and _spec.loader, "skills/vendor-status/scripts/observe_vendor_auth.py is missing"
observe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = observe
_spec.loader.exec_module(observe)

SECRET = "TOP-SECRET-TOKEN-DO-NOT-PRINT"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A fake home holding a Codex credential file with a known secret."""
    root = tmp_path / "home"
    (root / ".codex").mkdir(parents=True)
    credential = root / ".codex" / "auth.json"
    credential.write_text(SECRET, encoding="utf-8")
    credential.chmod(0o600)
    os.utime(credential, (1_700_000_000, 1_700_000_000))
    return root


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = observe.main(argv)
    captured = capsys.readouterr()
    return code, captured.out + captured.err


# --- Scenario: Metadata is reported without content ---


def test_metadata_is_reported(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(["codex", "--home", str(home)], capsys)

    assert code == 0
    assert str(home / ".codex" / "auth.json") in out
    assert "0600" in out
    assert "2023-11-14T22:13:20Z" in out


def test_content_is_never_printed(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out = _run(["codex", "--home", str(home)], capsys)

    assert SECRET not in out
    assert not any(SECRET[i : i + 6] in out for i in range(len(SECRET) - 5))


def test_script_never_opens_a_file(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata comes from stat alone, so an unreadable file is still reported."""

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"the script opened a file: {args[0]!r}")

    monkeypatch.setattr("builtins.open", _refuse)
    monkeypatch.setattr(os, "open", _refuse)
    monkeypatch.setattr(Path, "read_text", _refuse)
    monkeypatch.setattr(Path, "read_bytes", _refuse)

    code = observe.main(["codex", "--home", str(home)])

    assert code == 0
    assert "auth.json" in capsys.readouterr().out


def test_a_missing_path_is_reported_as_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(["codex", "--home", str(tmp_path)], capsys)

    assert code == 0
    assert "absent" in out


def test_a_symlink_is_reported_and_not_followed(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    credential = home / ".codex" / "auth.json"
    target = home / "elsewhere.json"
    credential.rename(target)
    credential.symlink_to(target)

    _, out = _run(["codex", "--home", str(home)], capsys)

    assert "symlink" in out
    assert SECRET not in out


def test_config_directory_variable_relocates_the_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    relocated = tmp_path / "relocated"
    relocated.mkdir()
    (relocated / "auth.json").write_text(SECRET, encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(relocated))

    _, out = _run(["codex", "--home", str(tmp_path / "home")], capsys)

    assert str(relocated / "auth.json") in out


# --- Scenario: A refresh write is detected ---


def test_watch_reports_a_modified_path(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    credential = home / ".codex" / "auth.json"
    rewrite = (
        "import os, sys; p = sys.argv[1]; "
        "f = open(p, 'w'); f.write('rotated-token-value'); f.close(); "
        "os.utime(p, (1_800_000_000, 1_800_000_000))"
    )

    code, out = _run(
        ["codex", "--home", str(home), "--watch", "--", sys.executable, "-c", rewrite,
         str(credential)],
        capsys,
    )

    assert code == 0
    assert f"changed: {credential}" in out
    assert "rotated-token-value" not in out


def test_watch_reports_a_created_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    credential = home / ".codex" / "auth.json"
    create = "import sys; f = open(sys.argv[1], 'w'); f.write('x'); f.close()"

    _, out = _run(
        ["codex", "--home", str(home), "--watch", "--", sys.executable, "-c", create,
         str(credential)],
        capsys,
    )

    assert f"changed: {credential}" in out


def test_watch_reports_no_change_when_nothing_is_written(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(
        ["codex", "--home", str(home), "--watch", "--", sys.executable, "-c", "pass"],
        capsys,
    )

    assert code == 0
    assert "changed: none" in out


def test_watch_returns_the_command_exit_status(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run(
        ["codex", "--home", str(home), "--watch", "--", sys.executable, "-c",
         "raise SystemExit(3)"],
        capsys,
    )

    assert code == 3


def test_watch_without_a_command_is_refused(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(["codex", "--home", str(home), "--watch"], capsys)

    assert code != 0
    assert "command" in out


# --- Scenario: An unknown vendor is refused ---


def test_an_unknown_vendor_is_refused(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(["copilot", "--home", str(home)], capsys)

    assert code != 0
    assert "copilot" in out


def test_script_vendors_match_the_audit_table() -> None:
    table = yaml.safe_load(_TABLE.read_text(encoding="utf-8"))

    assert sorted(observe.CANDIDATE_PATHS) == sorted(table["vendors"])


def test_mode_formatting_keeps_only_permission_bits() -> None:
    assert observe.format_mode(stat.S_IFREG | 0o600) == "0600"
    assert observe.format_mode(stat.S_IFDIR | 0o755) == "0755"
