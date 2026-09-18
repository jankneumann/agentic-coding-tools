"""Tests for the package's public surface and import hygiene.

Spec: specs/system-one-decisions/spec.md
  "Package exports and dependency-free import"
  "The package is importable from every declared consumer" (import-succeeds part;
  the multi-environment scenarios are covered by work-packages.yaml verification
  steps, not by this in-process test).
"""

from __future__ import annotations

import subprocess
import sys

import system_one_decisions


def test_module_exports_decision_decide_and_decide_intent() -> None:
    assert hasattr(system_one_decisions, "Decision")
    assert hasattr(system_one_decisions, "decide")
    assert hasattr(system_one_decisions, "decide_intent")


def test_no_vendor_sdk_imported_at_load_time() -> None:
    """Run in a fresh subprocess, not this test process's `sys.modules`.

    In-process, sibling test files (`test_decide_live.py`,
    `test_decide_event_sink.py`) import `typesafe_sdk` at their own top
    level to build real SDK fixtures (design D5) -- that's a property of
    this test *session*, not of `system_one_decisions` importing it eagerly.
    A subprocess that imports nothing else is the only way to check what
    this assertion actually means: that `import system_one_decisions` alone
    never pulls in the vendor SDK.
    """
    probe = (
        "import system_one_decisions, sys, json; "
        "print(json.dumps('typesafe_sdk' in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "false"
