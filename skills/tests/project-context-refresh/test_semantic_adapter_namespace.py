"""Namespace and read-scope threading in the semantic adapter (ri-09 tasks 2.1-2.2).

D4 — a checkpoint indexes into a ``work_package`` namespace keyed
``<change-id>--<package-id>``; the canonical refresh keeps ``main``/``main``, so
ri-07's behaviour is unchanged when the new parameters are omitted.

D5 — the package's resolved read scope reaches the indexer as ``--read-allow`` /
``--deny``, with deny winning over an overlapping read-allow glob.

Every assertion here is against the **built argv**. The enforcement itself lives
downstream in code-search (``cli.py`` declares the flags, ``indexing_policy.py``
rejects out-of-scope paths, and promotion is gated on ``main``/``main``) and is
already tested there; ri-09 supplies the values, it does not re-implement the
checks.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from semantic_adapter import (
    CANONICAL_NAMESPACE,
    IndexNamespace,
    ReadScope,
    build_subprocess_indexer,
    default_semantic_indexer,
)

FULL_SHA = "c" * 40

BASE_ENV = {
    "POSTGRES_DSN": "postgresql://u@localhost/db",
    "PROJECT_CONTEXT_EMBEDDING_MODEL": "bge-small",
    "PROJECT_CONTEXT_EMBEDDING_DIMENSION": "384",
}

_READY = json.dumps(
    {
        "status": "ready",
        "index_id": "11111111-2222-3333-4444-555555555555",
        "source_revision": FULL_SHA,
        "durable": True,
        "reused": False,
    }
)


def _values(argv: list[str], flag: str) -> list[str]:
    """Every value passed for ``flag`` in ``argv``, in order."""
    return [argv[i + 1] for i, token in enumerate(argv) if token == flag]


def _built_argv(monkeypatch, tmp_path, **kwargs) -> list[str]:
    """Run the subprocess indexer against a stub runner and return its argv."""
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: ["index_repo"])
    seen: dict[str, list[str]] = {}

    def runner(argv, **_kw):
        seen["argv"] = list(argv)
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=_READY, stderr=""
        )

    indexer = build_subprocess_indexer(BASE_ENV, runner=runner, **kwargs)
    indexer(tmp_path, FULL_SHA)
    return seen["argv"]


# --------------------------------------------------------------------------- #
# 2.1 Namespace threading (D4)
# --------------------------------------------------------------------------- #
def test_work_package_namespace_reaches_the_argv(monkeypatch, tmp_path):
    namespace = IndexNamespace.for_work_package(
        "add-branch-local-context-checkpoints", "wp-adapter"
    )
    argv = _built_argv(monkeypatch, tmp_path, namespace=namespace)

    assert _values(argv, "--namespace-kind") == ["work_package"]
    assert _values(argv, "--namespace-key") == [
        "add-branch-local-context-checkpoints--wp-adapter"
    ]


def test_namespace_key_uses_the_worktree_branch_separator():
    # `--` matches the worktree branch convention so the system has one rule.
    namespace = IndexNamespace.for_work_package("ri-09", "wp-checkpoint")
    assert namespace.key == "ri-09--wp-checkpoint"
    assert namespace.kind == "work_package"


def test_omitting_the_namespace_keeps_the_canonical_main_pair(monkeypatch, tmp_path):
    # ri-07 non-regression: the default path must be byte-identical to today's.
    argv = _built_argv(monkeypatch, tmp_path)

    assert _values(argv, "--namespace-kind") == ["main"]
    assert _values(argv, "--namespace-key") == ["main"]


def test_explicit_canonical_namespace_matches_the_default(monkeypatch, tmp_path):
    default_argv = _built_argv(monkeypatch, tmp_path)
    explicit_argv = _built_argv(monkeypatch, tmp_path, namespace=CANONICAL_NAMESPACE)

    assert _values(explicit_argv, "--namespace-kind") == _values(
        default_argv, "--namespace-kind"
    )
    assert _values(explicit_argv, "--namespace-key") == _values(
        default_argv, "--namespace-key"
    )


def test_for_work_package_cannot_produce_the_canonical_namespace():
    # A checkpoint constructs its namespace only through this classmethod, so it
    # structurally cannot reach the promotion gate (kind main AND key "main").
    namespace = IndexNamespace.for_work_package("main", "main")
    assert namespace.kind == "work_package"
    assert not namespace.is_canonical
    assert CANONICAL_NAMESPACE.is_canonical


def test_unknown_namespace_kind_is_rejected():
    with pytest.raises(ValueError):
        IndexNamespace(kind="canonical", key="main")


@pytest.mark.parametrize(
    "kind,key",
    [("main", "wp-adapter"), ("work_package", "main"), ("feature", "main")],
)
def test_the_canonical_pair_cannot_be_spelled_partially(kind, key):
    # "main" is a pair, not a kind and not a key: half of it is always a bug.
    with pytest.raises(ValueError):
        IndexNamespace(kind=kind, key=key)


@pytest.mark.parametrize("change_id,package_id", [("", "wp"), ("ri-09", "  ")])
def test_work_package_namespace_requires_both_identifiers(change_id, package_id):
    with pytest.raises(ValueError):
        IndexNamespace.for_work_package(change_id, package_id)


def test_default_semantic_indexer_accepts_a_namespace(monkeypatch, tmp_path):
    # wp-checkpoint builds its indexer through this entry point.
    monkeypatch.setattr("semantic_adapter._index_command", lambda env: ["index_repo"])
    seen: dict[str, list[str]] = {}

    def runner(argv, **_kw):
        seen["argv"] = list(argv)
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=_READY, stderr=""
        )

    monkeypatch.setattr(
        "semantic_adapter.subprocess.run", runner
    )  # default_semantic_indexer takes no runner
    indexer = default_semantic_indexer(
        BASE_ENV, namespace=IndexNamespace.for_work_package("ri-09", "wp-adapter")
    )
    assert indexer is not None
    indexer(tmp_path, FULL_SHA)

    assert _values(seen["argv"], "--namespace-kind") == ["work_package"]
    assert _values(seen["argv"], "--namespace-key") == ["ri-09--wp-adapter"]


# --------------------------------------------------------------------------- #
# 2.2 Read-scope threading (D5)
# --------------------------------------------------------------------------- #
def test_scope_reaches_the_argv_as_read_allow_and_deny(monkeypatch, tmp_path):
    scope = ReadScope(
        read_allow=("skills/**", "openspec/changes/**"),
        deny=("**/.venv/**",),
    )
    argv = _built_argv(monkeypatch, tmp_path, scope=scope)

    assert _values(argv, "--read-allow") == ["skills/**", "openspec/changes/**"]
    assert _values(argv, "--deny") == ["**/.venv/**"]


def test_deny_wins_over_an_overlapping_read_allow_glob(monkeypatch, tmp_path):
    scope = ReadScope(
        read_allow=("skills/**", "packages/code-search/**"),
        deny=("packages/code-search/**",),
    )
    argv = _built_argv(monkeypatch, tmp_path, scope=scope)

    # The denied glob is never offered as readable, and is still denied.
    assert _values(argv, "--read-allow") == ["skills/**"]
    assert _values(argv, "--deny") == ["packages/code-search/**"]


def test_deny_precedence_is_resolved_on_the_value_not_only_the_argv():
    scope = ReadScope(read_allow=("a/**", "b/**"), deny=("b/**",))
    assert scope.read_allow == ("a/**",)
    assert scope.deny == ("b/**",)


def test_a_scope_that_denies_everything_it_allows_is_rejected():
    # An empty read_allow means "no restriction" downstream, so silently
    # emptying one would widen the scope instead of narrowing it.
    with pytest.raises(ValueError):
        ReadScope(read_allow=("packages/**",), deny=("packages/**",))


def test_omitting_the_scope_emits_no_scope_flags(monkeypatch, tmp_path):
    argv = _built_argv(monkeypatch, tmp_path)
    assert "--read-allow" not in argv
    assert "--deny" not in argv


def test_an_empty_scope_emits_no_scope_flags(monkeypatch, tmp_path):
    argv = _built_argv(monkeypatch, tmp_path, scope=ReadScope())
    assert "--read-allow" not in argv
    assert "--deny" not in argv


def test_scope_duplicates_are_collapsed_deterministically():
    scope = ReadScope(read_allow=("a/**", "a/**", "b/**"), deny=("c/**", "c/**"))
    assert scope.read_allow == ("a/**", "b/**")
    assert scope.deny == ("c/**",)


def test_blank_scope_patterns_are_rejected():
    with pytest.raises(ValueError):
        ReadScope(read_allow=("  ",))


def test_scope_can_be_adopted_from_the_ri08_resolver():
    # ri-08's `index_scopes()` returns an IndexScopes with these two fields;
    # the adapter adopts it structurally rather than importing validate-packages.
    class _IndexScopes:
        read_allow = ("skills/**", "docs/**")
        deny = ("docs/**",)

    scope = ReadScope.from_index_scopes(_IndexScopes())
    assert scope.read_allow == ("skills/**",)
    assert scope.deny == ("docs/**",)


def test_namespace_and_scope_are_threaded_together(monkeypatch, tmp_path):
    argv = _built_argv(
        monkeypatch,
        tmp_path,
        namespace=IndexNamespace.for_work_package("ri-09", "wp-adapter"),
        scope=ReadScope(read_allow=("skills/**",), deny=("**/.venv/**",)),
    )

    assert _values(argv, "--namespace-kind") == ["work_package"]
    assert _values(argv, "--namespace-key") == ["ri-09--wp-adapter"]
    assert _values(argv, "--read-allow") == ["skills/**"]
    assert _values(argv, "--deny") == ["**/.venv/**"]
    # And the ri-07 argv it composes with is untouched.
    assert _values(argv, "--source-revision") == [FULL_SHA]
