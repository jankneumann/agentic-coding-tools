"""Required properties of the permissions allow-list write.

One test per defect the shell fragment carried. Each asserts the *property*
directly rather than comparing against a transcription of the old fragment:
the properties are the requirement, and the discarded fragment's behavior is
not.

Two of the defects are latent in the repository's own settings file — it has
only an ``allow`` list, and no ``deny`` key at all — so asserting against the
real file would pass vacuously. Every case is constructed in ``tmp_path``.
"""

from __future__ import annotations

import builtins
import difflib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

import setup_coordinator as sc


NON_CANONICAL = """{
    "permissions": {
        "allow": [
            "Bash(git status:*)"
        ]
    },
    "disabledMcpjsonServers": [
        "legacy"
    ]
}
"""


def _allow(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8"))["permissions"]["allow"]


def _diff_lines(before: str, after: str) -> list[str]:
    return [
        line
        for line in difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm="", n=0
        )
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


# --------------------------------------------------------------------------- #
# Defect 1 — the settings path must not depend on the working directory
# --------------------------------------------------------------------------- #


def test_root_is_resolved_absolutely(tmp_path):
    resolved = sc.settings_path_for_root(tmp_path / "repo")
    assert resolved.is_absolute()
    assert resolved == (tmp_path / "repo" / ".claude" / "settings.local.json").resolve()


def test_working_directory_independence(tmp_path, settings_json, monkeypatch):
    """Scenario: Working directory independence."""
    root, target = settings_json({"permissions": {"allow": []}})
    elsewhere = tmp_path / "elsewhere" / "deep"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)

    sc.add_coordination_permission(root)

    assert sc.WILDCARD in _allow(target)
    assert not (elsewhere / ".claude").exists()
    assert not (Path.cwd() / ".claude").exists()


def test_configure_from_a_subdirectory_writes_the_root_settings_file(
    tmp_path, settings_json, monkeypatch, capsys
):
    root, target = settings_json({"permissions": {"allow": []}})
    subdir = root / "nested"
    subdir.mkdir()
    monkeypatch.chdir(subdir)

    exit_code = sc.main(["configure", "--root", str(root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["path"] == str(target)
    assert not (subdir / ".claude").exists()


# --------------------------------------------------------------------------- #
# Defect 2 — sibling keys, key order, and indentation survive the write
# --------------------------------------------------------------------------- #


def test_wildcard_added_to_a_settings_file_with_unrelated_keys(settings_json):
    """Scenario: Wildcard added to a settings file with unrelated keys."""
    data = {
        "permissions": {"allow": ["Bash(git status:*)"], "deny": []},
        "disabledMcpjsonServers": ["legacy"],
        "enableAllProjectMcpServers": False,
    }
    root, target = settings_json(data)
    before = target.read_text(encoding="utf-8")

    result = sc.add_coordination_permission(root)

    assert result["changed"] is True
    after = json.loads(target.read_text(encoding="utf-8"))
    assert after["permissions"]["allow"] == ["Bash(git status:*)", sc.WILDCARD]
    for key in ("disabledMcpjsonServers", "enableAllProjectMcpServers"):
        assert after[key] == data[key]
    assert list(after.keys()) == list(data.keys())
    # The strongest available assertion: nothing outside the allow-list moved.
    changed = _diff_lines(before, target.read_text(encoding="utf-8"))
    assert changed == ['+      "mcp__coordination__*"'] or changed == [
        '-      "Bash(git status:*)"',
        '+      "Bash(git status:*)",',
        '+      "mcp__coordination__*"',
    ], changed


def test_non_canonical_input_keeps_its_key_order_and_indentation(settings_file):
    """Scenario: Settings file is not in canonical JSON form."""
    root, target = settings_file(NON_CANONICAL)

    sc.add_coordination_permission(root)

    after = target.read_text(encoding="utf-8")
    # Canonical form would sort `disabledMcpjsonServers` ahead of `permissions`
    # and reindent to two spaces. Neither may happen.
    assert list(json.loads(after).keys()) == ["permissions", "disabledMcpjsonServers"]
    assert '\n    "permissions"' in after
    assert '\n    "disabledMcpjsonServers"' in after
    assert after.endswith("\n")
    for line in _diff_lines(NON_CANONICAL, after):
        assert "mcp__coordination__" in line or "Bash(git status:*)" in line


def test_a_file_without_a_trailing_newline_does_not_gain_one(settings_file):
    root, target = settings_file(json.dumps({"permissions": {"allow": []}}, indent=2))

    sc.add_coordination_permission(root)

    assert not target.read_text(encoding="utf-8").endswith("\n")


# --------------------------------------------------------------------------- #
# Defect 3 — the write is atomic
# --------------------------------------------------------------------------- #


def _assert_atomic_write(module, target: Path, monkeypatch) -> None:
    """Assert *module*'s selected writer never mutates *target* in place.

    Records the state of the target at the moment ``os.replace`` is called. A
    writer that ends in ``target.write_bytes(payload)`` never calls
    ``os.replace`` at all, so ``calls`` stays empty and the assertion fires.
    """
    original = target.read_bytes() if target.exists() else None
    calls: list[tuple[Path, Path, bytes | None]] = []
    real_replace = os.replace

    def _record(src, dst, *args, **kwargs):
        dst_path = Path(dst)
        observed = dst_path.read_bytes() if dst_path.exists() else None
        calls.append((Path(src), dst_path, observed))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(module.os, "replace", _record)

    def _forbidden(self, *args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(f"in-place write to {self}")

    monkeypatch.setattr(Path, "write_bytes", _forbidden)
    monkeypatch.setattr(Path, "write_text", _forbidden)

    module.add_coordination_permission(target.parents[1])

    assert calls, "no os.replace: the write was not performed through a temp file"
    src, dst, observed = calls[-1]
    assert dst == target
    assert src != target
    assert src.parent == target.parent, "temp file must share the target filesystem"
    # A concurrent reader at that instant still saw the whole prior document.
    assert observed == original


def test_concurrent_reader_safety(settings_json, monkeypatch):
    """Scenario: Concurrent reader safety."""
    root, target = settings_json({"permissions": {"allow": ["Bash(ls:*)"]}})
    _assert_atomic_write(sc, target, monkeypatch)
    assert sc.WILDCARD in _allow(target)


# --------------------------------------------------------------------------- #
# Defect 4 — the "already present" check is scoped to the allow-list
# --------------------------------------------------------------------------- #


def test_wildcard_present_only_in_the_deny_list(settings_json, capsys):
    """Scenario: Wildcard present only in the deny list.

    Latent in the live settings file, which has no `deny` key — a textual scan
    of the file concludes the permission is already allowed and skips the add,
    reporting success while doing nothing.
    """
    root, target = settings_json(
        {"permissions": {"allow": ["Bash(ls:*)"], "deny": [sc.WILDCARD]}}
    )

    result = sc.add_coordination_permission(root)

    assert result["changed"] is True
    assert result["reason"] != "already-configured"
    after = json.loads(target.read_text(encoding="utf-8"))
    assert sc.WILDCARD in after["permissions"]["allow"]
    assert after["permissions"]["deny"] == [sc.WILDCARD]


def test_wildcard_in_an_unrelated_key_does_not_count_as_configured(settings_json):
    root, target = settings_json(
        {"permissions": {"allow": []}, "notes": f"remember {sc.WILDCARD}"}
    )

    result = sc.add_coordination_permission(root)

    assert result["changed"] is True
    assert sc.WILDCARD in _allow(target)


# --------------------------------------------------------------------------- #
# Idempotency and collapsing
# --------------------------------------------------------------------------- #


def test_idempotent_rerun_when_wildcard_is_not_last(settings_json, monkeypatch):
    """Scenario: Idempotent re-run — position must not matter.

    The sibling test below places the wildcard last, which is where the writer
    would put it anyway. That left a gap: an implementation comparing the
    allow-list against ``[*kept, WILDCARD]`` rewrote any file whose wildcard sat
    earlier, reordering an operator's list to satisfy an internal preference and
    violating "SHALL make no modification" for a file needing none.
    """
    root, target = settings_json(
        {"permissions": {"allow": [sc.WILDCARD, "Bash(ls:*)"]}, "other": 1}
    )
    before = target.read_bytes()

    def _forbidden(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("idempotent re-run attempted a write")

    monkeypatch.setattr(sc, "_atomic_write_bytes", _forbidden)

    result = sc.add_coordination_permission(root)

    assert result["changed"] is False
    assert result["reason"] == "already-configured"
    assert target.read_bytes() == before
    # Order preserved exactly as the operator wrote it.
    assert json.loads(before)["permissions"]["allow"][0] == sc.WILDCARD


def test_wildcard_present_but_individual_entries_still_collapse(settings_json):
    """The position fix must not disable collapsing.

    A file carrying both the wildcard and a redundant individual entry still
    needs a write — "already present" alone is not sufficient grounds to skip.
    """
    root, target = settings_json(
        {"permissions": {"allow": [sc.WILDCARD, "mcp__coordination__recall"]}}
    )

    result = sc.add_coordination_permission(root)

    assert result["changed"] is True
    assert json.loads(target.read_text())["permissions"]["allow"] == [sc.WILDCARD]


def test_idempotent_rerun_does_not_modify_the_file(settings_json, monkeypatch):
    """Scenario: Idempotent re-run."""
    root, target = settings_json(
        {"permissions": {"allow": ["Bash(ls:*)", sc.WILDCARD]}, "other": 1}
    )
    before = target.read_bytes()
    before_mtime = target.stat().st_mtime_ns

    def _forbidden(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("idempotent re-run attempted a write")

    monkeypatch.setattr(sc, "_atomic_write_bytes", _forbidden)

    result = sc.add_coordination_permission(root)

    assert result["changed"] is False
    assert result["reason"] == "already-configured"
    assert target.read_bytes() == before
    assert target.stat().st_mtime_ns == before_mtime


def test_idempotency_holds_for_a_non_canonical_file(settings_file, monkeypatch):
    """A re-run against an externally formatted file is still a no-op."""
    text = NON_CANONICAL.replace(
        '"Bash(git status:*)"', f'"Bash(git status:*)",\n            "{sc.WILDCARD}"'
    )
    root, target = settings_file(text)

    def _forbidden(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("idempotent re-run attempted a write")

    monkeypatch.setattr(sc, "_atomic_write_bytes", _forbidden)

    result = sc.add_coordination_permission(root)

    assert result["changed"] is False
    assert target.read_text(encoding="utf-8") == text


def test_double_apply_is_byte_stable(settings_json):
    root, target = settings_json({"permissions": {"allow": ["Bash(ls:*)"]}})

    sc.add_coordination_permission(root)
    once = target.read_bytes()
    sc.add_coordination_permission(root)

    assert target.read_bytes() == once


def test_individual_entries_are_collapsed_into_the_wildcard(settings_json):
    root, target = settings_json(
        {
            "permissions": {
                "allow": [
                    "Bash(ls:*)",
                    "mcp__coordination__submit_work",
                    "mcp__coordination__get_work",
                ]
            }
        }
    )

    result = sc.add_coordination_permission(root)

    assert _allow(target) == ["Bash(ls:*)", sc.WILDCARD]
    assert sorted(result["collapsed"]) == [
        "mcp__coordination__get_work",
        "mcp__coordination__submit_work",
    ]


def test_missing_settings_file_is_created_under_the_explicit_root(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()

    result = sc.add_coordination_permission(root)

    target = root / ".claude" / "settings.local.json"
    assert result["changed"] is True
    assert _allow(target) == [sc.WILDCARD]


# --------------------------------------------------------------------------- #
# Task 2.3a — the inline fallback must itself be atomic
# --------------------------------------------------------------------------- #


@pytest.fixture
def module_without_sibling(entrypoint_path, monkeypatch):
    """Load the entrypoint with the `atomic` sibling import forced to fail.

    The precedent this wiring is copied from ends its fallback in
    ``target.write_bytes(payload)`` — a plain in-place write under a name that
    promises atomicity. That passes every other test in this file, so this is
    the only fixture standing between the fallback and that regression.
    """
    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name == "atomic":
            raise ImportError("no module named 'atomic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "atomic", raising=False)
    monkeypatch.setattr(builtins, "__import__", _blocked)

    spec = importlib.util.spec_from_file_location(
        "setup_coordinator_no_sibling", entrypoint_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entrypoint_still_loads_without_the_sibling_skill(module_without_sibling):
    """Scenario: Sibling skill unavailable."""
    assert module_without_sibling._atomic_write_bytes is (
        module_without_sibling._inline_atomic_write_bytes
    )
    # The capability degrades to the inline writer; the process does not abort.
    assert callable(module_without_sibling.main)
    assert module_without_sibling.build_parser() is not None


def test_fallback_write_is_atomic(module_without_sibling, settings_json, monkeypatch):
    """Scenario: Fallback write is atomic."""
    root, target = settings_json({"permissions": {"allow": ["Bash(ls:*)"]}})
    _assert_atomic_write(module_without_sibling, target, monkeypatch)


def test_fallback_leaves_unrelated_keys_byte_identical(
    module_without_sibling, settings_file
):
    root, target = settings_file(NON_CANONICAL)
    before = NON_CANONICAL

    module_without_sibling.add_coordination_permission(root)

    after = target.read_text(encoding="utf-8")
    assert sc.WILDCARD in _allow(target)
    assert list(json.loads(after).keys()) == ["permissions", "disabledMcpjsonServers"]
    for line in _diff_lines(before, after):
        assert "mcp__coordination__" in line or "Bash(git status:*)" in line


def test_fallback_is_a_no_op_on_identical_bytes(module_without_sibling, tmp_path):
    target = tmp_path / "payload.bin"
    payload = b"same\n"
    assert module_without_sibling._inline_atomic_write_bytes(target, payload) is True
    assert module_without_sibling._inline_atomic_write_bytes(target, payload) is False
