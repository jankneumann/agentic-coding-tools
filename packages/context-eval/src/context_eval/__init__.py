"""``context-eval`` — the semantic-context evaluation harness (ri-13).

Measures whether ri-12's injected ``Semantic code context`` section is worth
more to a coding job than the exact-search baseline it would otherwise fall back
to, and produces a report whose verdict is exactly ``pass`` or ``fail``.

This phase ships the corpus and its loader. The producers, scorers, verdict
composer, and CLI arrive in later phases; nothing is re-exported here that does
not yet exist.
"""

from __future__ import annotations

from .loader import CorpusError, corpus_digest, load_corpus

__all__ = ["CorpusError", "corpus_digest", "load_corpus"]
