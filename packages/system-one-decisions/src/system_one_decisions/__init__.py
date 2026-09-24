"""system_one_decisions — the shared seam for calibrated System One decisions.

Fallback-only in this release: every call degrades to the caller's existing
rule. See docs/proposals/jev-system-one-integration-assessment.md and
docs/proposals/jev-twelve-factor-decision-loops.md for the design this
package implements, and this change's design.md for the specific decisions
(D1-D4) that shaped this item.
"""

from __future__ import annotations

from ._core import Decision, decide, decide_intent

__all__ = ["Decision", "decide", "decide_intent"]
