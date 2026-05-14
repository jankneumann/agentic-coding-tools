"""Shared setup for cleanup-feature tests.

Several tests in this directory create real git repos in tmp_path and then
commit inside submodule checkouts. ``git submodule add`` clones the
submodule into ``parent/.git/modules/<name>/`` with its own config, which
does NOT inherit the parent repo's local ``user.email``/``user.name``.

On dev machines this is masked by a global git identity. CI runners have
no global identity, so ``git commit`` inside the submodule checkout fails
with exit 128 ("empty ident name not allowed").

Setting ``GIT_AUTHOR_*`` / ``GIT_COMMITTER_*`` at the process level takes
precedence over per-repo config and propagates to all ``subprocess.run``
git calls in these tests, regardless of which git directory they target.
"""

from __future__ import annotations

import os

_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
}
for _key, _val in _GIT_IDENTITY.items():
    os.environ.setdefault(_key, _val)
