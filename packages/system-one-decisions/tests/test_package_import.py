"""Tests for the package's public surface and import hygiene.

Spec: specs/system-one-decisions/spec.md
  "Package exports and dependency-free import"
  "The package is importable from every declared consumer" (import-succeeds part;
  the multi-environment scenarios are covered by work-packages.yaml verification
  steps, not by this in-process test).
"""

from __future__ import annotations

import sys

import system_one_decisions


def test_module_exports_decision_decide_and_decide_intent() -> None:
    assert hasattr(system_one_decisions, "Decision")
    assert hasattr(system_one_decisions, "decide")
    assert hasattr(system_one_decisions, "decide_intent")


def test_no_vendor_sdk_imported_at_load_time() -> None:
    assert "typesafe_sdk" not in sys.modules
