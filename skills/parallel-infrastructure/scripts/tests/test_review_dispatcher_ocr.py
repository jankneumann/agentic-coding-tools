"""Discovery behavior for the optional `ocr-local` reviewer vendor.

An absent `ocr` binary must leave dispatch identical to today: the vendor is
Tier-3 skipped, and the rest of the roster is unaffected (skill-workflow
"Optional OCR Reviewer Vendor" / "OCR absent leaves dispatch unchanged").
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from review_dispatcher import (  # noqa: E402
    CliVendorAdapter,
    ReviewOrchestrator,
    _ocr_adapter_can_dispatch,
)


def _ocr_and_codex_config() -> dict:
    return {
        "agents": [
            {
                "agent_id": "ocr-local",
                "type": "ocr",
                "cli": {
                    "command": "ocr_adapter.py",
                    "model_flag": "",
                    "dispatch_modes": {"review": {"args": []}},
                    "prompt_via_stdin": True,
                },
            },
            {
                "agent_id": "codex-local",
                "type": "codex",
                "cli": {
                    "command": "codex",
                    "model_flag": "--model",
                    "dispatch_modes": {"review": {"args": ["-p"]}},
                },
            },
        ]
    }


class TestOcrDiscovery:
    def test_ocr_absent_is_tier3_skipped(self) -> None:
        orch = ReviewOrchestrator.from_config_dict(_ocr_and_codex_config())

        def fake_which(cmd: str) -> str | None:
            # Only codex is "installed" in this simulated environment.
            return "/usr/bin/codex" if cmd == "codex" else None

        with patch("shutil.which", side_effect=fake_which):
            reviewers = orch.discover_reviewers()

        vendors = {r.vendor for r in reviewers}
        assert vendors == {"codex"}
        assert "ocr" not in vendors

    def test_dispatch_roster_unchanged_by_ocr_presence_or_absence(self) -> None:
        """The set of non-OCR vendors dispatched is identical whether or not
        the ocr-local agent is declared and available."""
        without_ocr = ReviewOrchestrator.from_config_dict(
            {"agents": [_ocr_and_codex_config()["agents"][1]]}
        )
        with_ocr_absent = ReviewOrchestrator.from_config_dict(_ocr_and_codex_config())

        def fake_which(cmd: str) -> str | None:
            return "/usr/bin/codex" if cmd == "codex" else None

        with patch("shutil.which", side_effect=fake_which):
            a = {r.vendor for r in without_ocr.discover_reviewers()}
            b = {r.vendor for r in with_ocr_absent.discover_reviewers()}
        assert a == b == {"codex"}

    def test_ocr_present_and_configured_is_tier1(self) -> None:
        orch = ReviewOrchestrator.from_config_dict(_ocr_and_codex_config())

        def fake_which(cmd: str) -> str | None:
            if cmd in ("ocr_adapter.py", "codex"):
                return f"/usr/bin/{cmd}"
            return None

        adapter = orch.adapters["ocr-local"]
        assert isinstance(adapter, CliVendorAdapter)
        # The generic command-on-PATH check (ocr_adapter.py, faked above)
        # is not enough for the ocr vendor: can_dispatch also delegates to
        # ocr_adapter.can_dispatch() for the real `ocr` binary + LLM
        # endpoint check, which this test's simulated environment does not
        # otherwise have (no real `ocr` on PATH in CI/sandbox), so it is
        # patched directly here to simulate a fully-configured install.
        with (
            patch("shutil.which", side_effect=fake_which),
            patch("review_dispatcher._ocr_adapter_can_dispatch", return_value=True),
        ):
            reviewers = orch.discover_reviewers()
        vendors = {r.vendor: r for r in reviewers}
        assert vendors["ocr"].dispatch_tier == "cli"

    def test_ocr_command_present_but_binary_unconfigured_is_tier3(self) -> None:
        """The wrapper script's interpreter (python3) is always on PATH —
        that alone must not advertise ocr as available when the real `ocr`
        binary or its LLM endpoint is missing (regression coverage for the
        gap where discovery only checked the configured `command`)."""
        orch = ReviewOrchestrator.from_config_dict(_ocr_and_codex_config())

        def fake_which(cmd: str) -> str | None:
            if cmd in ("ocr_adapter.py", "codex"):
                return f"/usr/bin/{cmd}"
            return None

        with (
            patch("shutil.which", side_effect=fake_which),
            patch("review_dispatcher._ocr_adapter_can_dispatch", return_value=False),
        ):
            reviewers = orch.discover_reviewers()
        vendors = {r.vendor for r in reviewers}
        assert "ocr" not in vendors


class TestOcrAdapterCanDispatchDelegate:
    def test_delegates_to_ocr_adapter_module(self) -> None:
        with patch("ocr_adapter.can_dispatch", return_value=True):
            assert _ocr_adapter_can_dispatch() is True
        with patch("ocr_adapter.can_dispatch", return_value=False):
            assert _ocr_adapter_can_dispatch() is False

    def test_fails_closed_when_ocr_adapter_cannot_be_imported(self) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "ocr_adapter":
                raise ImportError("simulated missing module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert _ocr_adapter_can_dispatch() is False
