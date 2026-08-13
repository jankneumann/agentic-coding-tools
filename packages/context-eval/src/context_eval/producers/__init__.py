"""Producers turn a case into a rendered section that a scorer can measure.

Two exist, and they are deliberately symmetric: the exact-search producer here
and the live semantic producer that loads ri-12's module. Both emit
:class:`~context_eval.scoring.arms.Arm`, both are rendered under the single
budget the corpus declares, and neither knows anything about the scorers.

Every path a producer uses is **injected**. No module in this package derives a
repository root, a corpus root, or a skill location from ``__file__``, and
``test_repo_root_resolution.py`` fails if one starts to — the archived
evaluation died of exactly that arithmetic (design D1, D10).
"""

from __future__ import annotations
