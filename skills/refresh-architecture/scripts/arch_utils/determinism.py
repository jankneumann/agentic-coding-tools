"""Deterministic clock for committed architecture producer outputs (ri-04 D3).

Committed architecture metadata must be reproducible: two refreshes of the same
source revision and inputs MUST produce byte-identical artifacts (spec scenario
architecture-refresh.9). Wall-clock ``datetime.now()`` timestamps break that, so
every producer stamps ``generated_at`` through :func:`generated_at_iso`, which
honors ``SOURCE_DATE_EPOCH`` when the refresh runner sets it and only falls back
to the wall clock for ad-hoc, non-committed invocations.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def source_date_epoch() -> int | None:
    """Return the ``SOURCE_DATE_EPOCH`` override as an int, or ``None`` if unset.

    A malformed value is treated as unset rather than raising, so a stray
    environment value can never crash a producer mid-pipeline.
    """
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def generated_at_iso() -> str:
    """Return an ISO-8601 UTC timestamp, deterministic under ``SOURCE_DATE_EPOCH``.

    When the refresh runner exports ``SOURCE_DATE_EPOCH`` (derived from the
    analyzed commit), every producer in the pipeline stamps the same instant, so
    the committed artifacts are byte-identical across reruns of one revision.
    """
    epoch = source_date_epoch()
    if epoch is not None:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()
