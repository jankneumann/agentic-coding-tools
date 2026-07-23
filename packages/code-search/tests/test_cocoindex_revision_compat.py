"""Tripwires for the deliberately narrow CocoIndex compatibility window."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest


def test_dependency_contract_pins_cocoindex_code_and_cocoindex_v1() -> None:
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert project["project"]["optional-dependencies"]["index"] == [
        "cocoindex[sentence-transformers]>=1.0.13,<1.1.0",
        "cocoindex-code==0.2.37",
    ]
    assert "pathspec>=0.12,<2" in project["project"]["dependencies"]


@pytest.mark.requires_db
@pytest.mark.requires_embedder
def test_live_install_exposes_the_frozen_cocoindex_v1_surface() -> None:
    """Resource-gated evidence; the mandatory fake chooses the architecture.

    CocoIndex documents App lifecycle and stable ContextKey resources at:
    https://cocoindex.io/docs/programming_guide/app/
    https://cocoindex.io/docs/programming_guide/context/
    """
    import cocoindex as coco  # pyright: ignore[reportMissingImports]

    assert tuple(int(part) for part in version("cocoindex").split(".")[:2]) == (1, 0)
    assert version("cocoindex-code") == "0.2.37"
    assert callable(coco.App)
    assert callable(coco.ContextKey)
    assert callable(coco.fn)
    assert callable(coco.sources.localfs.walk_dir)
