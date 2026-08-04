"""Test fixtures for the merge-pull-requests suites.

`isolate_merge_metrics_log` is autouse: it stops emit_event's relative default
log path from writing into the working tree. See the shared module for why the
patch targets the function's bound default rather than the module attribute.
"""

from merge_events_isolation import isolate_merge_metrics_log  # noqa: F401
