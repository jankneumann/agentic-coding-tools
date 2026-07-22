"""Tests for the fix-scrub CLI contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_main_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "main.py"
    spec = importlib.util.spec_from_file_location("fix_scrub_main_cli", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_report_path_uses_latest_bug_scrub_json() -> None:
    module = _load_main_module()

    args = module.build_parser().parse_args([])

    assert args.report == "docs/bug-scrub/latest.json"
