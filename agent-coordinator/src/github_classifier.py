"""Compatibility export for the canonical portable GitHub classifier.

The implementation lives in ``skills/shared`` so installed skills do not
depend on coordinator source.  ``SKILLS_ROOT`` supports packaged coordinator
deployments; source checkouts use the repository's canonical skills directory.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType


def _load_classifier() -> ModuleType:
    default_skills_root = Path(__file__).resolve().parents[2] / "skills"
    skills_root = Path(os.environ.get("SKILLS_ROOT", default_skills_root))
    classifier_path = skills_root / "shared" / "github_classifier.py"
    if not classifier_path.is_file():
        raise ImportError(
            "Portable GitHub classifier is unavailable; set SKILLS_ROOT to the "
            f"installed skills directory (looked for {classifier_path})"
        )
    spec = importlib.util.spec_from_file_location(
        "_portable_github_classifier", classifier_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load portable GitHub classifier at {classifier_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_classifier = _load_classifier()
JULES_AUTHORS = _classifier.JULES_AUTHORS
JULES_PATTERNS = _classifier.JULES_PATTERNS
classify_pr = _classifier.classify_pr
from_rest_pr = _classifier.from_rest_pr
is_jules_author = _classifier.is_jules_author
safe_author = _classifier.safe_author
to_pr_card_origin = _classifier.to_pr_card_origin

__all__ = list(_classifier.__all__)
