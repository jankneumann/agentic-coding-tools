"""Test that gen_eval.mcp_service raises ImportError when fastmcp is absent.

Task 3.2 — spec scenario: gen-eval-framework.optional-mcp-service-extra
(base-install-lacks-mcp-dependencies), design decision D4.

Strategy: use unittest.mock to remove fastmcp from sys.modules and set it to
None (the stdlib import-blocker idiom), then force a fresh import of
gen_eval.mcp_service.  This avoids spawning a subprocess / creating a
separate venv, which would be slow and fragile in CI.
"""
from __future__ import annotations

import importlib
import sys


def test_mcp_service_raises_import_error_without_fastmcp() -> None:
    """Importing gen_eval.mcp_service must raise ImportError when fastmcp
    is not available.

    The module wraps its ``import fastmcp`` in a try/except per D4 and
    re-raises as ImportError with an ``[mcp]`` install hint.  We simulate
    the absence of fastmcp by temporarily blocking the import.
    """
    # Save references to any already-loaded modules we will disturb.
    mcp_service_key = "gen_eval.mcp_service"
    fastmcp_key = "fastmcp"

    saved_mcp_service = sys.modules.pop(mcp_service_key, None)
    saved_fastmcp = sys.modules.pop(fastmcp_key, None)

    try:
        # Setting a key to None tells the import machinery "this module
        # does not exist" (PEP 328 / importlib convention).
        sys.modules[fastmcp_key] = None  # type: ignore[assignment]

        try:
            importlib.import_module(mcp_service_key)
        except ImportError as exc:
            # The error message should contain the install hint.
            assert "[mcp]" in str(exc), (
                f"ImportError message should mention '[mcp]' extra, got: {exc}"
            )
        else:
            raise AssertionError(
                "gen_eval.mcp_service should have raised ImportError "
                "when fastmcp is not available, but it imported successfully."
            )
    finally:
        # Restore sys.modules to its original state so other tests are
        # not affected by our manipulation.
        sys.modules.pop(mcp_service_key, None)
        sys.modules.pop(fastmcp_key, None)

        if saved_mcp_service is not None:
            sys.modules[mcp_service_key] = saved_mcp_service
        if saved_fastmcp is not None:
            sys.modules[fastmcp_key] = saved_fastmcp
