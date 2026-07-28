"""A ``semantic_adapter`` that is present and unimportable.

The shape ri-12 actually meets in the wild: the file exists, so a presence check
passes, and importing it fails because a dependency of its own is missing. That
is the state ``_normalize_read_scope`` handles by silently returning unnormalized
globs, and the state the harness must report as ``degraded``.
"""

raise ImportError("this fixture adapter is deliberately unimportable")
