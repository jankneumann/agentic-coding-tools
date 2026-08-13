"""Deterministic scoring over rendered context sections.

Four modules, one measurement family each:

* :mod:`~context_eval.scoring.arms` — the rendered-section view every scorer
  consumes, and the adapter from ri-12's published section document.
* :mod:`~context_eval.scoring.relevance` — top-k hit rate, required-file
  coverage, and measured wins over the baseline (design D6).
* :mod:`~context_eval.scoring.scope` — zero-tolerance scope compliance (D8).
* :mod:`~context_eval.scoring.utility` — the three independent utility
  conditions and the absolute per-consumer do-no-harm clause (D7).

Nothing here reads a clock, imports ``random``, iterates a set, or contains a
threshold: every bound arrives as data from ``corpus/manifest.yaml`` (D6, D16).
"""

from __future__ import annotations
