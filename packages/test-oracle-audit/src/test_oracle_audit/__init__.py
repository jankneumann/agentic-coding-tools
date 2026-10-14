"""test_oracle_audit: read-only, multi-approach test-quality audit (pilot).

See openspec change ``pilot-test-quality-audit`` (design D1-D15). Stage modules
emit :class:`records.StageRecord` lines; ``analysis`` joins them on ``TestId``.
Nothing in this package gates anything: every output is advisory.
"""

from __future__ import annotations

__version__ = "0.1.0"
