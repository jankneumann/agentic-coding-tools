"""Byte parity between the published dispatch schemas and their install_assets mirror.

dispatch-contract (Published Dispatch Contract Schemas): consumer repositories may
only have the ``skills/roadmap-runtime/install_assets/openspec/`` copy, and
``skills/shared/dispatch_contract.py`` falls back to it. A drifted mirror would
validate dispatches against a different contract than the one this repository
publishes, so every mirrored file must be byte-identical to its source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OPENSPEC = _REPO_ROOT / "openspec"
_MIRROR = _REPO_ROOT / "skills" / "roadmap-runtime" / "install_assets" / "openspec"

_MIRRORED = (
    "schemas/dispatch-request.schema.json",
    "schemas/dispatch-result.schema.json",
    "schemas/checkpoint.schema.json",
)


@pytest.mark.parametrize("rel", _MIRRORED)
def test_mirror_is_byte_identical(rel: str) -> None:
    source = _OPENSPEC / rel
    mirror = _MIRROR / rel
    assert source.is_file(), f"published schema missing: {rel}"
    assert mirror.is_file(), f"install_assets mirror missing: {rel}"
    assert source.read_bytes() == mirror.read_bytes(), (
        f"install_assets mirror differs from openspec/{rel}; copy the published "
        "file over the mirror"
    )
